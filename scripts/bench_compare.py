#!/usr/bin/env python3
"""Aggregate / compare BiomniBench-DA model runs; surface & fix infra failures.

  python3 scripts/bench_compare.py <label> [<label> ...]
        Per-model score summary; side-by-side per-task table for 2+ labels.

  python3 scripts/bench_compare.py --infra <label>
        List the run's infra-failure cells and the command to fix each kind.

  uv run python scripts/bench_compare.py --regrade-stale <label>
        Re-judge only the `judge_unavailable` cells in place (output already
        exists — just the grader call is redone). Needs `uv run` for the
        omicos_biomnibench package.

A "label" is a run-id under runs/ — one per model (see bench_model.sh).
Means EXCLUDE the documented failure-case tasks (docs/failure-cases/) and
EXCLUDE infra-failure cells, so the number reflects model capability only.

Infra-failure modes (a 0.00 that is NOT the model's fault):
  no_output / error / serve_failed  -> the cell produced no usable output
                       (agent crashed, or `omicos serve` failed to start); re-RUN it
  judge_unavailable  -> output exists but the grader was down; just re-GRADE
"""
import glob
import json
import os
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
INFRA_MODES = {"no_output", "error", "serve_failed", "judge_unavailable"}


def failure_cases():
    """Task ids documented as failure-cases — excluded from capability means."""
    out = set()
    for f in glob.glob(str(PROJECT / "docs/failure-cases/da-*.md")):
        m = re.match(r"(da-\d+-\d+)", os.path.basename(f))
        if m:
            out.add(m.group(1))
    return out


def load(label):
    """label -> {task: (score, grade_mode)}"""
    rows = {}
    for g in glob.glob(str(PROJECT / f"runs/{label}/vertical_agent_selector/da-*/grade.json")):
        t = os.path.basename(os.path.dirname(g))
        try:
            d = json.load(open(g))
        except Exception:
            continue
        rows[t] = (d.get("score"), d.get("grade_mode", ""))
    return rows


def tnum(t):
    p = t.split("-")
    return (int(p[1]), int(p[2]))


def split(rows, fails):
    """-> (infra-failure tasks, capability scores excl. failure-cases)"""
    infra = [t for t, (s, gm) in rows.items() if gm in INFRA_MODES or s is None]
    inc = [s for t, (s, gm) in rows.items()
           if s is not None and gm not in INFRA_MODES and t not in fails]
    return infra, inc


def cmd_summary(labels):
    fails = failure_cases()
    data = {L: load(L) for L in labels}
    for L in labels:
        rows = data[L]
        infra, inc = split(rows, fails)
        mean = sum(inc) / len(inc) if inc else float("nan")
        med = sorted(inc)[len(inc) // 2] if inc else float("nan")
        print(f"{L}: {len(rows)}/50 graded | capability n={len(inc)} "
              f"mean={mean:.3f} median={med:.3f}")
        if infra:
            print(f"  WARNING {len(infra)} infra-failure cell(s): "
                  f"{sorted(infra, key=tnum)}")
            print(f"          fix with:  python3 scripts/bench_compare.py --infra {L}")
    if len(labels) >= 2:
        tasks = sorted({t for L in labels for t in data[L]}, key=tnum)
        print("\ntask      " + "".join(f"{L[:12]:>13}" for L in labels))
        for t in tasks:
            cells = []
            for L in labels:
                if t not in data[L]:
                    cells.append("-")          # not run yet
                    continue
                s, gm = data[L][t]
                cells.append("infra" if (gm in INFRA_MODES or s is None) else f"{s:.2f}")
            tag = "  <- failure-case" if t in fails else ""
            print(f"{t:<10}" + "".join(f"{c:>13}" for c in cells) + tag)


def cmd_infra(label):
    rows = load(label)
    fails = failure_cases()
    infra, _ = split(rows, fails)
    if not infra:
        print(f"{label}: no infra-failure cells.")
        return
    rerun = sorted([t for t in infra if rows[t][1] in ("no_output", "error", "serve_failed")
                    or rows[t][0] is None], key=tnum)
    stale = sorted([t for t in infra if rows[t][1] == "judge_unavailable"], key=tnum)
    print(f"{label}: {len(infra)} infra-failure cell(s)")
    for t in sorted(infra, key=tnum):
        print(f"  {t}  grade_mode={rows[t][1]!r}")
    if rerun:
        print("\n  output missing -> re-run with the SAME model/provider:")
        print(f"    bash scripts/bench_model.sh <provider> <model> {label} "
              f"--tids {','.join(rerun)}")
    if stale:
        print("\n  output exists, grader was down -> re-grade only:")
        print(f"    uv run python scripts/bench_compare.py --regrade-stale {label}")


def cmd_regrade(label):
    import yaml
    from omicos_biomnibench import dataset as ob_dataset
    from omicos_biomnibench import grader as ob_grader

    judge = (yaml.safe_load((PROJECT / "configs/models.yaml").read_text()) or {}).get(
        "judge_model", {})
    tasks = {t.task_id: t for t in ob_dataset.load_tasks()}
    rows = load(label)
    stale = [t for t, (s, gm) in rows.items() if gm == "judge_unavailable"]
    if not stale:
        print(f"{label}: no judge_unavailable cells.")
        return
    for t in sorted(stale, key=tnum):
        cell = PROJECT / f"runs/{label}/vertical_agent_selector/{t}"
        gp = cell / "grade.json"
        prior = json.loads(gp.read_text())
        ng = ob_grader.grade(rubric=tasks[t].rubric,
                             workspace=cell / "workspace", judge_cfg=judge)
        merged = dict(prior)
        merged.update(correct=bool(ng.correct), score=ng.score,
                      grade_mode=ng.mode, grader_notes=ng.notes, criteria=ng.criteria)
        gp.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
        print(f"  {t}: {prior.get('grade_mode')} -> {ng.mode}  "
              f"score {prior.get('score')} -> {ng.score}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    if args[0] == "--infra":
        cmd_infra(args[1])
    elif args[0] == "--regrade-stale":
        cmd_regrade(args[1])
    else:
        cmd_summary(args)
