"""HuggingFace loader + per-task staging for BiomniBench-DA.

The dataset ships as 50 task directories under `phylobio/BiomniBench-DA`:

    da-{paper}-{task}/
    ├── instruction.md          # research question + file manifest + output format
    ├── task.toml               # Harbor task config (verifier, agent, budgets)
    ├── environment/            # public dataset files (per-task bundle)
    └── tests/
        ├── rubric.txt          # expert-authored grading rubric
        ├── llm_judge.py        # Harbor-format judge harness
        └── test.sh             # entry script

`fetch_all(...)` downloads ALL 50 task dirs into `<data>/biomnibench-da/`
via a single `snapshot_download` call. `stage_task(...)` copies one task's
`environment/` into a fresh per-cell workspace so the agent can safely
modify files without affecting the cached source.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from huggingface_hub import login, snapshot_download

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — tomli is in pyproject for <3.11 users
    import tomli as tomllib  # type: ignore[no-redef]

DATASET_REPO_ID = "phylobio/BiomniBench-DA"
LOCAL_SNAPSHOT_DIRNAME = "biomnibench-da"


@dataclass
class Task:
    """One BiomniBench-DA task. Materialized from a downloaded snapshot dir."""

    task_id: str                    # e.g. "da-1-3"
    task_dir: Path                  # absolute path to the local snapshot dir
    instruction: str                # contents of instruction.md
    env_dir: Path                   # <task_dir>/environment
    tests_dir: Path                 # <task_dir>/tests
    rubric: str                     # contents of tests/rubric.txt (may be "")
    task_toml: dict = field(default_factory=dict)
    # Convenience accessors derived from task_toml. Schemas vary across
    # Harbor versions; we expose only the keys we actually depend on
    # and fall back to `None` for everything else.
    paper: str = ""                 # e.g. "{paper_id}" from task_id

    @property
    def has_judge(self) -> bool:
        return (self.tests_dir / "llm_judge.py").is_file()

    @property
    def has_test_sh(self) -> bool:
        return (self.tests_dir / "test.sh").is_file()


def _data_dir() -> Path:
    base = os.environ.get(
        "OMICOS_BIOMNIBENCH_DATA_DIR",
        str(Path(__file__).resolve().parents[2] / "data"),
    )
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _login_if_token() -> None:
    """The dataset is gated. Fail loud at the boundary if no token."""

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise RuntimeError(
            "BiomniBench-DA is a gated HF dataset. "
            "Export HF_TOKEN (e.g. `source ~/.claude/secrets.env`) and "
            "request access at https://huggingface.co/datasets/phylobio/BiomniBench-DA."
        )
    login(token=token, add_to_git_credential=False)


def fetch_all(
    *,
    metadata_only: bool = False,
    task_ids: list[str] | None = None,
) -> Path:
    """Download the dataset snapshot into `<data>/biomnibench-da/`.

    `metadata_only=True` pulls only `instruction.md`, `task.toml`, and
    `tests/*` for every task — useful when you want to inspect the schema
    or pick a subset before paying for the full `environment/` bytes.

    `task_ids` further restricts the download to a subset of the 50 tasks.
    """

    _login_if_token()
    snapshot_dir = _data_dir() / LOCAL_SNAPSHOT_DIRNAME
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    if task_ids:
        prefix = [f"{tid}/*" for tid in task_ids]
    else:
        prefix = ["*"]

    if metadata_only:
        allow = ["README*"]
        for p in prefix:
            allow += [
                f"{p[:-2]}/task.toml" if p.endswith("/*") else f"{p}/task.toml",
                f"{p[:-2]}/instruction.md" if p.endswith("/*") else f"{p}/instruction.md",
                f"{p[:-2]}/tests/*" if p.endswith("/*") else f"{p}/tests/*",
            ]
    else:
        allow = ["README*", *prefix]

    snapshot_download(
        repo_id=DATASET_REPO_ID,
        repo_type="dataset",
        local_dir=str(snapshot_dir),
        allow_patterns=allow,
    )
    return snapshot_dir


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _read_toml(p: Path) -> dict:
    if not p.is_file():
        return {}
    with p.open("rb") as f:
        return tomllib.load(f)


def load_tasks(*, task_ids: list[str] | None = None) -> list[Task]:
    """Load every task that's present locally under `<data>/biomnibench-da/`.

    Does NOT trigger a download — call `fetch_all(...)` first. We split
    the network step out so re-grading and offline analysis don't hit HF.
    """

    snapshot = _data_dir() / LOCAL_SNAPSHOT_DIRNAME
    if not snapshot.is_dir():
        raise RuntimeError(
            f"No local snapshot at {snapshot}. Run `omicos-biomnibench fetch` first."
        )

    out: list[Task] = []
    wanted = set(task_ids) if task_ids else None
    for child in sorted(snapshot.iterdir()):
        if not child.is_dir() or not child.name.startswith("da-"):
            continue
        if wanted is not None and child.name not in wanted:
            continue
        instr_path = child / "instruction.md"
        if not instr_path.is_file():
            # Half-fetched task (e.g. metadata-only run that hit 403 on
            # this specific file). Skip rather than blow up.
            continue
        toml_dict = _read_toml(child / "task.toml")
        # task_id encodes paper id as the middle segment of `da-X-Y`.
        paper = ""
        parts = child.name.split("-")
        if len(parts) >= 3:
            paper = parts[1]
        out.append(Task(
            task_id=child.name,
            task_dir=child,
            instruction=_read_text(instr_path),
            env_dir=child / "environment",
            tests_dir=child / "tests",
            rubric=_read_text(child / "tests" / "rubric.txt"),
            task_toml=toml_dict,
            paper=paper,
        ))
    return out


def stage_task(t: Task, cell_dir: Path) -> Path:
    """Copy the task's `environment/` into `<cell_dir>/workspace/`.

    The agent reads/writes here freely; the source `environment/` under
    `<data>/biomnibench-da/<task_id>/` is left untouched so subsequent
    cells (or re-runs) start from clean inputs.

    Also stages `instruction.md` at the workspace root for the agent to
    discover via file_manager — many BiomniBench instructions reference
    a data-file manifest that the agent needs to re-read mid-task.
    """

    workspace = cell_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    if t.env_dir.is_dir():
        for item in t.env_dir.iterdir():
            dest = workspace / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
    # Surface the instruction inside the workspace so the agent's
    # file_manager.list_dir sees it immediately. We also pass the
    # instruction text through the user prompt, but a workspace-local
    # copy lets the agent re-read sections without us re-sending them.
    (workspace / "instruction.md").write_text(t.instruction, encoding="utf-8")
    return workspace


def iter_tasks_filtered(
    tasks: list[Task],
    only_ids: list[str] | None = None,
) -> Iterator[Task]:
    if not only_ids:
        yield from tasks
        return
    wanted = set(only_ids)
    for t in tasks:
        if t.task_id in wanted:
            yield t
