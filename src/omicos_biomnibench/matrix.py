"""(agent × task) orchestrator for BiomniBench-DA.

Each (agent_id, task_id) is one cell. Per cell we:

  1. Stage a fresh per-cell workspace at
     `runs/<run_id>/<agent_id>/<task_id>/workspace/` (copy of `environment/`
     plus a workspace-local `instruction.md`).
  2. Launch `omicos serve` against that workspace via `runner.serve`.
  3. Send the task's instruction through `client.run_turn` with `config.agent`.
  4. Run the task's bundled judge (or the built-in LLM judge) over the
     trajectory + final answer.
  5. Persist `answer.json`, `grade.json`, `trajectory.jsonl`, `sse.log`.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from . import client as ob_client
from . import dataset as ob_dataset
from . import grader as ob_grader
from . import runner as ob_runner


def _user_prompt(t: ob_dataset.Task) -> str:
    """The user message we send to the agent.

    BiomniBench's judge reads two files the agent must create:
      * `trace.md`   — structured analytical trace
      * `answer.txt` — plain-text final answer

    We pass the dataset's instruction verbatim (it already specifies the
    required `trace.md` sections in detail) and add a thin wrapper for
    workspace path + plan-mode suppression.
    """

    return (
        "You are completing ONE task from the BiomniBench-DA benchmark. "
        "The data files for this task are already present in your current "
        "working directory; the task brief is also in this directory as "
        "`instruction.md`. Use your tools to inspect the data, run any "
        "code or notebooks you need, and complete every part of the task.\n\n"
        "TASK INSTRUCTION (verbatim from the dataset):\n"
        "----------\n"
        f"{t.instruction}\n"
        "----------\n\n"
        "OUTPUT CONTRACT (load-bearing — the judge reads these files):\n"
        "- Write your structured analytical trace to `trace.md` in this "
        "working directory. The instruction above specifies the required "
        "sections (Objective, Data Sources, Approach with code, Results, "
        "References) and the expected level of detail; follow them.\n"
        "- Write your plain-text final answer to `answer.txt` in this "
        "working directory.\n"
        "- The dataset's instruction mentions paths like `/app/trace.md`; "
        "ignore the `/app/` prefix — write to the current working "
        "directory instead. The grader looks for `./trace.md` and "
        "`./answer.txt`.\n\n"
        "Operating constraints:\n"
        "- All evidence must come from files in this workspace; do not "
        "guess from prior knowledge alone. Do NOT search for the source "
        "paper, figures, or supplementary materials (see instruction).\n"
        "- This is a non-interactive benchmark run. Do NOT use plan mode "
        "(`plan__enter` / `plan__write` / `plan__request_approval`) — "
        "there is no human reviewer to approve a plan. Execute directly.\n"
        "- After writing `trace.md` and `answer.txt`, verify both files "
        "exist (e.g. via `file_manager__list_dir`) before ending your "
        "turn. A missing file scores 0.\n\n"
        "Multi-specialist orchestration:\n"
        "BiomniBench tasks span multiple phases — data wrangling, "
        "statistical analysis, biological interpretation, translational "
        "implications, polished narrative. Your `## Available agents` "
        "roster lists sibling specialists; you can `call_agent` to "
        "delegate phases that fall outside your own specialty. Two "
        "natural handoffs the BiomniBench rubric rewards:\n\n"
        "  * `clinical_translator_pro` — for the 'biological / clinical "
        "interpretation' and 'translational implications' content the "
        "rubric expects. Hand it your concrete findings (gene lists, "
        "enriched populations, statistics) and ask for the mechanistic / "
        "translational paragraph.\n"
        "  * `scientific_writer` — for figure-quality narrative on the "
        "Results / Discussion sections.\n\n"
        "Use delegation when it strictly improves the deliverable; don't "
        "delegate steps you can complete competently yourself. After the "
        "sub-agent returns its text, merge it into `trace.md` under the "
        "appropriate section (the file you write is what the judge sees, "
        "not the sub-agent's reply text). The runtime caps delegation "
        "depth at 6 and refuses cycles — you can chain handoffs safely."
    )


@dataclass
class CellResult:
    run_id: str
    agent_id: str
    task_id: str
    paper: str
    correct: bool
    score: float
    grade_mode: str
    final_answer: str
    final_text: str
    grader_notes: str
    criteria: dict = field(default_factory=dict)
    error: str | None = None
    elapsed_s: float = 0.0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _select_agent(t: ob_dataset.Task, agents_cfg: list[dict]) -> dict | None:
    """First-match-wins. Honors per-agent `task_ids` allowlist; catch-all
    has neither filter. Mirrors omicos-bixbench's `_select_agent` logic."""

    for agent in agents_cfg:
        ids = agent.get("task_ids") or []
        if ids:
            if t.task_id in set(ids):
                return agent
            continue
        # No filter on this agent — catch-all.
        return agent
    return None


_log_lock = threading.Lock()


def _emit(msg: str) -> None:
    with _log_lock:
        print(msg, flush=True)


def run_matrix(
    *,
    project_root: Path,
    run_id: str,
    agents_yaml: Path,
    models_yaml: Path,
    tasks: Iterable[ob_dataset.Task],
    concurrency: int = 1,
) -> list[CellResult]:
    agents_cfg = _load_yaml(agents_yaml).get("agents", [])
    models_cfg = _load_yaml(models_yaml)
    agent_model = models_cfg.get("agent_model", {})
    judge_model = models_cfg.get("judge_model", {})

    run_root = project_root / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    tasks_list = list(tasks)
    assignments: list[tuple[dict, ob_dataset.Task]] = []
    unassigned: list[str] = []
    for t in tasks_list:
        agent = _select_agent(t, agents_cfg)
        if agent is None:
            unassigned.append(t.task_id)
            continue
        assignments.append((agent, t))

    if unassigned:
        _emit(
            f"[matrix] WARNING: {len(unassigned)} task(s) had no matching agent "
            f"and were skipped: {unassigned}"
        )

    _emit(
        f"[matrix] {len(assignments)} cell(s) to run "
        f"({len(tasks_list)} tasks, concurrency={concurrency})"
    )

    results: list[CellResult] = [None] * len(assignments)  # type: ignore[list-item]
    if concurrency <= 1:
        for i, (agent, t) in enumerate(assignments):
            results[i] = _run_cell(
                run_id=run_id,
                run_root=run_root,
                agent_id=agent["id"],
                task=t,
                agent_model=agent_model,
                judge_model=judge_model,
            )
            _emit(
                f"[matrix] {i+1}/{len(assignments)} done: "
                f"{agent['id']}/{t.task_id} score={results[i].score:.2f} "
                f"correct={results[i].correct} "
                f"elapsed={results[i].elapsed_s:.1f}s"
            )
        return results

    done_count = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        future_to_idx = {}
        for i, (agent, t) in enumerate(assignments):
            fut = pool.submit(
                _run_cell,
                run_id=run_id,
                run_root=run_root,
                agent_id=agent["id"],
                task=t,
                agent_model=agent_model,
                judge_model=judge_model,
            )
            future_to_idx[fut] = (i, agent["id"], t.task_id)
        for fut in as_completed(future_to_idx):
            i, aid, tid = future_to_idx[fut]
            try:
                results[i] = fut.result()
            except Exception as e:  # pragma: no cover — defensive
                _emit(f"[matrix] ERROR {aid}/{tid}: {e!r}")
                continue
            done_count += 1
            _emit(
                f"[matrix] {done_count}/{len(assignments)} done: "
                f"{aid}/{tid} score={results[i].score:.2f} "
                f"correct={results[i].correct} "
                f"elapsed={results[i].elapsed_s:.1f}s"
            )
    return [r for r in results if r is not None]


def _run_cell(
    *,
    run_id: str,
    run_root: Path,
    agent_id: str,
    task: ob_dataset.Task,
    agent_model: dict,
    judge_model: dict,
) -> CellResult:
    cell_dir = run_root / agent_id / task.task_id
    cell_dir.mkdir(parents=True, exist_ok=True)
    workspace = ob_dataset.stage_task(task, cell_dir)
    sse_log = cell_dir / "sse.log"
    trajectory_log = cell_dir / "trajectory.jsonl"
    started = time.monotonic()
    error: str | None = None
    turn: ob_client.TurnResult | None = None

    try:
        with ob_runner.serve(workspace, log_path=cell_dir / "omicos.log") as proc:
            turn = ob_client.run_turn(
                base_url=proc.base_url,
                agent_id=agent_id,
                user_message=_user_prompt(task),
                model_cfg=agent_model,
                sse_log=sse_log,
                trajectory_log=trajectory_log,
            )
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    # Whether the agent produced the contracted output files. Captured
    # even on serve failure so the report distinguishes "agent crashed"
    # from "agent ran but didn't write the files".
    trace_path = workspace / "trace.md"
    answer_path = workspace / "answer.txt"
    has_trace = trace_path.is_file()
    has_answer = answer_path.is_file()
    final_answer = answer_path.read_text(encoding="utf-8").strip() if has_answer else ""

    if turn is None:
        cell = CellResult(
            run_id=run_id,
            agent_id=agent_id,
            task_id=task.task_id,
            paper=task.paper,
            correct=False,
            score=0.0,
            grade_mode="serve_failed",
            final_answer=final_answer,
            final_text="",
            grader_notes="serve/turn failed",
            error=error or "unknown",
            elapsed_s=time.monotonic() - started,
        )
    else:
        grade = ob_grader.grade(
            rubric=task.rubric,
            workspace=workspace,
            judge_cfg=judge_model,
        )
        cell = CellResult(
            run_id=run_id,
            agent_id=agent_id,
            task_id=task.task_id,
            paper=task.paper,
            correct=grade.correct,
            score=grade.score,
            grade_mode=grade.mode,
            final_answer=final_answer or turn.final_answer,
            final_text=turn.final_text,
            grader_notes=grade.notes,
            criteria=grade.criteria,
            error=turn.error,
            elapsed_s=turn.elapsed_s,
            tool_calls=turn.tool_calls,
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
        )

    (cell_dir / "answer.json").write_text(
        json.dumps(
            {
                "task_id": task.task_id,
                "agent_id": agent_id,
                "final_answer": cell.final_answer,
                "final_text": cell.final_text,
                "has_trace_md": has_trace,
                "has_answer_txt": has_answer,
                "trace_path": str(trace_path) if has_trace else None,
                "answer_path": str(answer_path) if has_answer else None,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (cell_dir / "grade.json").write_text(
        json.dumps(asdict(cell), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return cell


def write_report(project_root: Path, run_id: str, results: list[CellResult]) -> Path:
    """Dump matrix.csv + summary.md under `reports/<run_id>/`."""

    import csv

    rep_dir = project_root / "reports" / run_id
    rep_dir.mkdir(parents=True, exist_ok=True)
    csv_path = rep_dir / "matrix.csv"
    fields = [k for k in CellResult.__dataclass_fields__.keys() if k != "criteria"]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            row = {k: getattr(r, k) for k in fields}
            w.writerow(row)

    by_agent: dict[str, list[CellResult]] = {}
    for r in results:
        by_agent.setdefault(r.agent_id, []).append(r)
    lines = [f"# omicos-biomnibench run `{run_id}`\n"]
    lines.append("| agent | answered | passed | accuracy | mean score |")
    lines.append("|---|---:|---:|---:|---:|")
    for agent_id, rs in sorted(by_agent.items()):
        n = len(rs)
        c = sum(1 for r in rs if r.correct)
        acc = c / n if n else 0.0
        mean_score = sum(r.score for r in rs) / n if n else 0.0
        lines.append(
            f"| `{agent_id}` | {n} | {c} | {acc:.1%} | {mean_score:.3f} |"
        )
    (rep_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rep_dir
