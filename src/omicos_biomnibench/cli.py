"""`omicos-biomnibench` CLI.

Subcommands:

    fetch [--metadata-only]   Download the dataset snapshot into ./data/
    smoke                     Run ONE (task, agent) cell as a sanity check
    run [opts]                Run the full agent × task matrix
    regrade <run_id>          Re-grade an existing run with the current judge
    report <run_id>           Re-emit matrix.csv + summary.md from grade.json
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from dataclasses import asdict
from pathlib import Path

import click
import yaml

from . import dataset as ob_dataset
from . import matrix as ob_matrix


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _new_run_id() -> str:
    return _dt.datetime.now().strftime("run-%Y%m%d-%H%M%S")


@click.group()
def main() -> None:
    """Evaluate omicos-core agents on BiomniBench-DA."""


@main.command()
@click.option("--metadata-only", is_flag=True, default=False,
              help="Pull only task.toml + instruction.md + tests/ for each task. "
                   "Useful for inspecting schema without paying the environment/ bytes.")
@click.option("--task-ids", default=None,
              help="Comma-separated subset of task ids to fetch.")
def fetch(metadata_only: bool, task_ids: str | None) -> None:
    """Download the dataset snapshot via huggingface_hub.snapshot_download."""

    ids = [t.strip() for t in (task_ids or "").split(",") if t.strip()] or None
    path = ob_dataset.fetch_all(metadata_only=metadata_only, task_ids=ids)
    click.echo(f"snapshot: {path}")
    tasks = ob_dataset.load_tasks(task_ids=ids)
    click.echo(f"loaded {len(tasks)} task(s) locally")


@main.command()
@click.option("--agent", default="omicverse_omni", show_default=True,
              help="Agent id to smoke-test.")
@click.option("--tid", default=None,
              help="Specific task_id (e.g. da-1-3); defaults to the first task.")
def smoke(agent: str, tid: str | None) -> None:
    """Run ONE cell end-to-end. Validates omicos binary, env, SSE drain, judge."""

    project = _project_root()
    models_yaml = project / "configs" / "models.yaml"
    all_tasks = ob_dataset.load_tasks()
    if tid:
        tasks = [t for t in all_tasks if t.task_id == tid]
        if not tasks:
            click.echo(f"no task with id {tid!r}", err=True)
            sys.exit(2)
    else:
        tasks = all_tasks[:1]

    one_agent_yaml = project / "runs" / "_smoke_agents.yaml"
    one_agent_yaml.parent.mkdir(parents=True, exist_ok=True)
    one_agent_yaml.write_text(
        yaml.safe_dump({"agents": [{"id": agent, "tier": "any"}]}),
        encoding="utf-8",
    )

    run_id = "smoke-" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    results = ob_matrix.run_matrix(
        project_root=project,
        run_id=run_id,
        agents_yaml=one_agent_yaml,
        models_yaml=models_yaml,
        tasks=tasks,
    )
    rep_dir = ob_matrix.write_report(project, run_id, results)
    for r in results:
        click.echo(json.dumps(asdict(r), indent=2, ensure_ascii=False))
    click.echo(f"\nreport: {rep_dir}")


@main.command()
@click.option("--agents", default=None,
              help="Comma-separated agent ids; overrides configs/agents.yaml ids.")
@click.option("--limit", type=int, default=None,
              help="Cap the number of tasks (top-N alphabetical).")
@click.option("--tids", default=None,
              help="Comma-separated explicit task_ids to run.")
@click.option("--run-id", default=None,
              help="Override the generated run id.")
@click.option("--concurrency", "-j", type=int, default=1, show_default=True,
              help="Number of cells to run in parallel. Each cell spawns its own "
                   "omicos serve + Python kernel, so RAM budget is ~1-3 GB per "
                   "concurrent worker once data is loaded.")
def run(agents: str | None,
        limit: int | None,
        tids: str | None,
        run_id: str | None,
        concurrency: int) -> None:
    """Run the full agent × task matrix."""

    project = _project_root()
    models_yaml = project / "configs" / "models.yaml"
    agents_yaml = project / "configs" / "agents.yaml"

    if agents:
        ids = [a.strip() for a in agents.split(",") if a.strip()]
        override = project / "runs" / "_cli_agents.yaml"
        override.parent.mkdir(parents=True, exist_ok=True)
        override.write_text(
            yaml.safe_dump({
                "agents": [{"id": a, "tier": "any"} for a in ids],
            }),
            encoding="utf-8",
        )
        agents_yaml = override

    all_tasks = ob_dataset.load_tasks()
    only_ids = [t.strip() for t in (tids or "").split(",") if t.strip()] or None
    tasks = list(ob_dataset.iter_tasks_filtered(all_tasks, only_ids=only_ids))
    if limit is not None:
        tasks = tasks[:limit]
    if not tasks:
        click.echo("no tasks match the filters", err=True)
        sys.exit(2)

    rid = run_id or _new_run_id()
    click.echo(f"run_id={rid}  tasks={len(tasks)}")
    results = ob_matrix.run_matrix(
        project_root=project,
        run_id=rid,
        agents_yaml=agents_yaml,
        models_yaml=models_yaml,
        tasks=tasks,
        concurrency=concurrency,
    )
    rep_dir = ob_matrix.write_report(project, rid, results)
    passed = sum(1 for r in results if r.correct)
    click.echo(f"\n{len(results)} cells  |  {passed} passed  |  report: {rep_dir}")


@main.command()
@click.argument("run_id")
def regrade(run_id: str) -> None:
    """Re-grade an existing run with the current `grader.py` logic.

    Reads each cell's `<workspace>/trace.md` + `<workspace>/answer.txt`,
    re-invokes the judge, overwrites `grade.json`. The expensive
    omicos-serve step is NOT repeated — only the judge call.
    """

    import yaml as _yaml

    from . import grader as ob_grader

    project = _project_root()
    run_root = project / "runs" / run_id
    if not run_root.is_dir():
        click.echo(f"no run dir at {run_root}", err=True)
        sys.exit(2)

    models_cfg = _yaml.safe_load((project / "configs" / "models.yaml").read_text()) or {}
    judge_model = models_cfg.get("judge_model", {})
    tasks = {t.task_id: t for t in ob_dataset.load_tasks()}

    flipped = 0
    total = 0
    for answer_path in sorted(run_root.glob("*/*/answer.json")):
        data = json.loads(answer_path.read_text(encoding="utf-8"))
        tid = data.get("task_id")
        t = tasks.get(tid)
        if t is None:
            continue
        cell_dir = answer_path.parent
        workspace = cell_dir / "workspace"
        grade_path = answer_path.with_name("grade.json")
        prior = json.loads(grade_path.read_text(encoding="utf-8")) if grade_path.exists() else {}
        new_grade = ob_grader.grade(
            rubric=t.rubric,
            workspace=workspace,
            judge_cfg=judge_model,
        )
        total += 1
        was = bool(prior.get("correct", False))
        now = bool(new_grade.correct)
        if was != now:
            flipped += 1
        merged = dict(prior)
        merged["correct"] = now
        merged["score"] = new_grade.score
        merged["grade_mode"] = new_grade.mode
        merged["grader_notes"] = new_grade.notes
        merged["criteria"] = new_grade.criteria
        grade_path.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        if was != now:
            click.echo(
                f"  FLIP {data.get('agent_id')}/{tid}  "
                f"{was} -> {now}  score={new_grade.score:.2f}"
            )
    click.echo(f"\nregraded {total} cells, {flipped} verdict flips")

    results: list[ob_matrix.CellResult] = []
    for grade_path in run_root.glob("*/*/grade.json"):
        data = json.loads(grade_path.read_text(encoding="utf-8"))
        data.setdefault("criteria", {})
        results.append(ob_matrix.CellResult(**data))
    rep_dir = ob_matrix.write_report(project, run_id, results)
    click.echo(f"report: {rep_dir}")


@main.command()
@click.argument("run_id")
def report(run_id: str) -> None:
    """Regenerate matrix.csv + summary.md from existing grade.json files."""

    project = _project_root()
    run_root = project / "runs" / run_id
    if not run_root.is_dir():
        click.echo(f"no run dir at {run_root}", err=True)
        sys.exit(2)
    results: list[ob_matrix.CellResult] = []
    for grade_path in run_root.glob("*/*/grade.json"):
        data = json.loads(grade_path.read_text(encoding="utf-8"))
        data.setdefault("criteria", {})
        results.append(ob_matrix.CellResult(**data))
    rep_dir = ob_matrix.write_report(project, run_id, results)
    click.echo(f"report: {rep_dir}  ({len(results)} cells)")


if __name__ == "__main__":  # pragma: no cover
    main()
