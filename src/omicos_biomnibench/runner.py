"""Per-task `omicos serve` lifecycle manager.

Each cell of the (agent × task) matrix gets its own:
  * workspace dir (`environment/` copy + `instruction.md`)
  * per-run agents catalog (built from `OMICOS_BIOMNIBENCH_AGENTS_DIR`)
  * unique TCP port
  * fresh subprocess

omicos-core's `acquire_serve_lock` enforces one-daemon-per-workspace, so
running matrix cells in parallel against the SAME task means we have to
materialize the workspace once per cell — handled by the orchestrator.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import httpx


def _free_port() -> int:
    """Pick an ephemeral port. Tiny race window — acceptable for a research
    harness, not for production."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class OmicosProcess:
    proc: subprocess.Popen
    port: int
    workspace: Path
    data_dir: Path
    log_path: Path

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def _resolve_omicos_bin() -> str:
    explicit = os.environ.get("OMICOS_BIN")
    if explicit and Path(explicit).is_file():
        return explicit
    found = shutil.which("omicos")
    if found:
        return found
    raise RuntimeError(
        "Cannot locate the omicos binary. Build with "
        "`cargo build --release` inside omicos-core and either add the "
        "target/release dir to PATH or export OMICOS_BIN=<abs path>."
    )


def _resolve_agents_overlay() -> Path:
    """Return the admin agent catalog directory.

    Search order:
      1. `OMICOS_BIOMNIBENCH_AGENTS_DIR` env var (explicit, wins).
      2. `../omicos-admin/agents` relative to this repo (sibling-clone layout).

    No absolute fallback — if neither is present, fail fast at the
    boundary rather than silently spawning an empty-catalog omicos.
    """

    explicit = os.environ.get("OMICOS_BIOMNIBENCH_AGENTS_DIR")
    if explicit:
        p = Path(explicit)
        if p.is_dir():
            return p
        raise RuntimeError(
            f"OMICOS_BIOMNIBENCH_AGENTS_DIR points at {p} but it's not a directory."
        )
    # Repo-relative sibling fallback: omicos_dev/omicos-biomnibench → omicos_dev/omicos-admin/agents
    sibling = Path(__file__).resolve().parents[3] / "omicos-admin" / "agents"
    if sibling.is_dir():
        return sibling
    raise RuntimeError(
        "No agent catalog found. Set OMICOS_BIOMNIBENCH_AGENTS_DIR or clone "
        "omicos-admin next to this repo so `../omicos-admin/agents` resolves."
    )


def _resolve_runtime_overlay() -> Path | None:
    """Optional cloud-agents cache (lab-tier agents like omicverse_expert).
    Returns None if not present — harness tolerates a missing overlay."""

    explicit = os.environ.get("OMICOS_BIOMNIBENCH_RUNTIME_AGENTS_DIR")
    if explicit:
        p = Path(explicit)
        return p if p.is_dir() else None
    sibling = (
        Path(__file__).resolve().parents[3]
        / "omicos-runtime" / ".omicos" / "cloud-agents" / "agents"
    )
    return sibling if sibling.is_dir() else None


def _build_templates_dir(workspace: Path) -> Path:
    """Materialize `<workspace>/_agents_catalog/agents/` with the union of
    the admin catalog + optional runtime cache. Admin wins on filename
    collision.

    Important: omicos-core's `TemplateStore` joins `agents/` onto the
    templates dir, so `OMICOS_TEMPLATES_DIR` must name the *parent* of
    the agents subdir.
    """

    admin = _resolve_agents_overlay()
    runtime = _resolve_runtime_overlay()

    root = workspace / "_agents_catalog"
    agents_subdir = root / "agents"
    if root.exists():
        shutil.rmtree(root)
    agents_subdir.mkdir(parents=True)

    seen: set[str] = set()
    for src in [admin, runtime]:
        if src is None or not src.is_dir():
            continue
        for f in sorted(src.iterdir()):
            if not (f.is_file() and f.suffix == ".md"):
                continue
            if f.name in seen:
                continue
            shutil.copyfile(f, agents_subdir / f.name)
            seen.add(f.name)
    if not seen:
        raise RuntimeError(f"No agent .md files found under {admin}")
    return root


def _provider_env() -> dict[str, str]:
    """Supply the agent model's provider credentials to the omicos
    subprocess, and force-disable cloud sync for deterministic runs.

    custom_openai (CUSTOM_OPENAI_API_BASE/KEY) is honored when exported —
    this is the path for benchmarking a non-DeepSeek OpenAI-compatible
    model (e.g. MiMo). When unset it falls back to DEEPSEEK_* so a bare
    `deepseek` run needs no extra config. DEEPSEEK_* is always passed
    through unchanged for the judge (grader.py reads DEEPSEEK_* directly).

    GEMINI_API_KEY is left in the user environment as-is; the grader picks
    it up directly.
    """

    key = os.environ.get("DEEPSEEK_API_KEY")
    base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set. `source ~/.claude/secrets.env` first."
        )
    return {
        # Agent-model endpoint. An explicit CUSTOM_OPENAI_* export wins
        # (non-DeepSeek OpenAI-compatible model); else fall back to
        # DeepSeek so a bare `deepseek` run is unchanged.
        "CUSTOM_OPENAI_API_BASE": os.environ.get("CUSTOM_OPENAI_API_BASE") or base,
        "CUSTOM_OPENAI_API_KEY": os.environ.get("CUSTOM_OPENAI_API_KEY") or key,
        "DEEPSEEK_API_BASE": base,
        "DEEPSEEK_API_KEY": key,
        "OMICOS_AGENTS_OFFLINE": "1",
        "OMICOS_SKILLS_OFFLINE": "1",
        "OMICOS_MODELS_OFFLINE": "1",
        "OMICOS_MEMORY_OFFLINE": "1",
    }


def _resolve_skill_roots() -> str:
    """Point omicos-core's skill discovery at the admin source of truth.

    Search order parallels the agent overlay:
      1. `OMICOS_BIOMNIBENCH_SKILLS_DIR` env var.
      2. sibling `omicos-admin/skills` relative to this repo.

    Returns empty string if neither resolves; omicos then has no skills,
    which is a valid (if degraded) run.
    """

    explicit = os.environ.get("OMICOS_BIOMNIBENCH_SKILLS_DIR")
    if explicit:
        return explicit
    sibling = Path(__file__).resolve().parents[3] / "omicos-admin" / "skills"
    return str(sibling) if sibling.is_dir() else ""


def _wait_for_health(base_url: str, timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=2.0)
            if r.status_code == 200:
                return
        except Exception as e:
            last_err = e
        time.sleep(0.5)
    raise RuntimeError(
        f"omicos serve did not become healthy at {base_url} "
        f"within {timeout_s:.0f}s (last error: {last_err})"
    )


def _seed_omicos_local_home(local_home: Path) -> None:
    """Seed a per-run ``OMICOS_LOCAL_HOME`` with the user's auth material.

    omicos serialises access to its ``~/.omicos`` directory (cloud_login,
    oauth tokens, caches); two concurrent ``omicos serve`` processes that
    share one ``~/.omicos`` intermittently deadlock at start-up. Each run
    therefore gets its own ``OMICOS_LOCAL_HOME`` — but it still needs the
    auth files copied in so the isolated omicos can authenticate.
    """
    src = Path(os.environ.get("HOME", "")) / ".omicos"
    for name in ("cloud_login.json", "auth.json"):
        s = src / name
        if s.is_file():
            shutil.copy2(s, local_home / name)
    oauth_src = src / "oauth"
    if oauth_src.is_dir():
        dst = local_home / "oauth"
        if not dst.exists():
            shutil.copytree(oauth_src, dst)


@contextmanager
def serve(
    workspace: Path,
    *,
    log_path: Path | None = None,
    extra_env: dict[str, str] | None = None,
    health_timeout_s: float = 60.0,
) -> Iterator[OmicosProcess]:
    """Spawn `omicos serve` against `workspace`, yield the live process,
    tear it down on exit. SIGTERM → 5s grace → SIGKILL."""

    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"workspace does not exist: {workspace}")
    templates_dir = _build_templates_dir(workspace)

    port = _free_port()
    data_dir = workspace / ".omicos"
    data_dir.mkdir(exist_ok=True)
    log_path = log_path or (workspace / "omicos.log")

    # Per-run isolated omicos home — prevents the start-up deadlock that
    # hits concurrent runs sharing one ~/.omicos (see _seed_omicos_local_home).
    local_home = workspace / ".omicos_home"
    local_home.mkdir(exist_ok=True)
    _seed_omicos_local_home(local_home)

    # Pin the omicos Python kernel to the omicdev conda env: it carries the
    # editable omicverse dev tree plus the ov.genetics backends (pycoloc,
    # pysusie, pymatrixeqtl, …) that the released wheels do not ship yet.
    # The bundled omicos-env/.venv lacks them, so agents cannot run
    # colocalization / fine-mapping there. An explicit OMICOS_KERNEL_PYTHON
    # already in the environment still wins.
    kernel_python = os.environ.get(
        "OMICOS_KERNEL_PYTHON", "python3"
    )

    env = {
        **os.environ,
        **_provider_env(),
        "OMICOS_TEMPLATES_DIR": str(templates_dir),
        "OMICOS_LOCAL_HOME": str(local_home),
        "OMICOS_KERNEL_PYTHON": kernel_python,
        **(extra_env or {}),
    }
    skill_roots = _resolve_skill_roots()
    if skill_roots:
        env["OMICOS_SKILL_ROOTS"] = skill_roots

    cmd = [
        _resolve_omicos_bin(),
        "serve",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--data-dir", str(data_dir),
        "--no-browser",
    ]
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(workspace),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_health(f"http://127.0.0.1:{port}", timeout_s=health_timeout_s)
        yield OmicosProcess(
            proc=proc,
            port=port,
            workspace=workspace,
            data_dir=data_dir,
            log_path=log_path,
        )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        log_fh.close()
