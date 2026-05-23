#!/usr/bin/env python3
"""Radar chart of per-dimension capability for BiomniBench-DA model runs.

  python3 scripts/bench_radar.py [<label> ...]
      -> reports/omicos_radar.png
      -> reports/omicos_dim_map.csv  (auditable per-criterion -> dimension)

The dataset's rubrics don't carry a per-criterion dimension tag, so we
classify every criterion into one of six published BiomniBench-DA
evaluation dimensions via a keyword-priority heuristic on the criterion
title + description:

  data handling, method selection, statistical rigor,
  biological interpretation, scientific reasoning, source reliability

Each dimension's score for a model = sum of earned points / sum of
A-level (max) points across every (cell, criterion) pair that maps to
that dimension. Failure-case tasks and infra-failure cells are excluded.

Inspect / edit the heuristic in `classify_dim()` and re-run; the
generated `omicos_dim_map.csv` lists what each task's criteria were
classified as.
"""
import csv
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
INFRA = {"no_output", "error", "serve_failed", "judge_unavailable"}
FAIL_CASES = {"da-12-4", "da-18-7", "da-20-1", "da-6-2"}

DIMS = ["data handling", "method selection", "statistical rigor",
        "biological interpretation", "scientific reasoning", "source reliability"]

# Keyword markers per dimension (matched against title + description, lowercased).
# Priority order: most specific first. First-match wins.
DIM_KEYWORDS = [
    ("source reliability", [
        "source reliability", "source-reliability", "citation", "reference",
        "retraction", "source-grounding"]),
    ("biological interpretation", [
        "biological interpretation", "biological meaning", "biological annotation",
        "biological rationale", "mechanistic interpretation", "biology",
        "biological insight", "mechanism of action", "immunological interpretation",
        "biological hypothesis", "phenotype interpret"]),
    ("scientific reasoning", [
        "translational implication", "translational", "preclinical-validation",
        "assumptions", "limitations", "validation criteria", "reasoning",
        "prioritisation", "prioritization", "discussion", "argument",
        "candidate reporting", "candidate prioriti", "rationale and ",
        "scientific reasoning", "interpretation of"]),
    ("statistical rigor", [
        "statistical", "significance", "p-value", "fdr", "q-value",
        "quantification", "computation", "ranking", "frequency", "association",
        "correlation", "metric computation", "metric reporting",
        "reporting accuracy", "quantitative reporting", "differential",
        "enrichment computation", "co-occurrence", "test"]),
    ("method selection", [
        "method", "methodology", "definition", "construction", "processing",
        "normalization", "batch effect", "qc", "wgcna", "network",
        "design matrix", "model selection", "approach", "filtering logic",
        "filter methodology"]),
    ("data handling", [
        "data loading", "data structure", "data selection", "data quality",
        "ingest", "load", "loading", "subset", "identification", "structure and annotation",
        "annotation limits", "compartment", "baseline filtering",
        "table construction", "data preparation", "preprocess"]),
]


def classify_dim(title, description=""):
    """Map a criterion to one of the six dimensions via keyword priority."""
    text = (title + " " + description).lower()
    for dim, kws in DIM_KEYWORDS:
        for kw in kws:
            if kw in text:
                return dim
    # fallback: title-based guess by position-ish content
    if "interpret" in text:
        return "biological interpretation"
    if "report" in text:
        return "scientific reasoning"
    if any(k in text for k in ("compute", "filter", "rank", "frequen")):
        return "statistical rigor"
    return "data handling"


_RUBRIC_CACHE = {}


def parse_rubric(task_id):
    """Return [(idx, title, description, A_pts)] for the task's criteria."""
    if task_id in _RUBRIC_CACHE:
        return _RUBRIC_CACHE[task_id]
    p = PROJECT / "data/biomnibench-da" / task_id / "tests/rubric.txt"
    if not p.exists():
        _RUBRIC_CACHE[task_id] = []
        return []
    text = p.read_text(encoding="utf-8", errors="ignore")
    parts = re.split(r"^Criterion\s+(\d+)\s*:\s*", text, flags=re.MULTILINE)
    crit = []
    for i in range(1, len(parts), 2):
        idx = int(parts[i])
        body = parts[i + 1] if i + 1 < len(parts) else ""
        title = body.split("\n", 1)[0].strip()
        m = re.search(r"Description:\s*(.+?)(?:\n\s*Levels:|\n\s*\[[A-Z]\]|$)",
                      body, re.S)
        desc = m.group(1).strip() if m else ""
        m_lv = re.search(r"Levels:\s*A=(\d+)", body)
        a_pts = int(m_lv.group(1)) if m_lv else 0
        crit.append((idx, title, desc, a_pts))
    _RUBRIC_CACHE[task_id] = crit
    return crit


def aggregate(label):
    """-> {dim: (earned, max)} for the model."""
    earned = defaultdict(float)
    mx = defaultdict(float)
    for gj in glob.glob(str(
            PROJECT / f"results/{label}/vertical_agent_selector/da-*/grade.json")):
        d = json.load(open(gj))
        if d.get("grade_mode") in INFRA:
            continue
        task = gj.split("/")[-2]
        if task in FAIL_CASES:
            continue
        crit = parse_rubric(task)
        if not crit:
            continue
        cmap = {f"criterion_{i}": (t, desc, a) for i, t, desc, a in crit}
        for k, v in (d.get("criteria") or {}).items():
            tup = cmap.get(k)
            if tup is None:
                continue
            title, desc, a_pts = tup
            if a_pts <= 0:
                continue
            dim = classify_dim(title, desc)
            sc = float(v.get("score") or 0)
            earned[dim] += sc
            mx[dim] += a_pts
    return {dim: (earned[dim], mx[dim]) for dim in DIMS}


def write_dim_map():
    """Audit file: per task, per criterion → assigned dimension + points."""
    out = PROJECT / "reports" / "omicos_dim_map.csv"
    out.parent.mkdir(exist_ok=True)
    rows = []
    for p in sorted((PROJECT / "data/biomnibench-da").glob("da-*/tests/rubric.txt")):
        task = p.parent.parent.name
        for idx, title, desc, a in parse_rubric(task):
            rows.append([task, idx, classify_dim(title, desc), a, title[:100]])
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["task", "criterion", "dimension", "A_points", "title"])
        w.writerows(rows)
    return out


def main(labels):
    map_csv = write_dim_map()
    print(f"wrote dim audit: {map_csv}  ({sum(1 for _ in open(map_csv))-1} criteria)")
    rows = {}
    for L in labels:
        rows[L] = aggregate(L)

    # Radar plot — sort by overall mean so strongest models draw last (on top).
    means = {L: np.mean([100 * agg[d][0] / agg[d][1] if agg[d][1] > 0 else 0
                         for d in DIMS]) for L, agg in rows.items()}
    ordered = sorted(rows.items(), key=lambda kv: means[kv[0]])
    palette = {
        "gpt-5.5":       "#1F4FBF",
        "gpt-5.4":       "#4FB99F",
        "gpt-5.4-mini":  "#9DD0C5",
        "ds4-pro":       "#E8894C",
        "ds4-flash":     "#F2BB94",
        "mimo-v2.5-pro": "#A04EBF",
        "mimo-v2.5":     "#C9A5DA",
    }

    angles = np.linspace(0, 2 * np.pi, len(DIMS), endpoint=False).tolist()
    angles += [angles[0]]
    fig = plt.figure(figsize=(13.5, 8.8))
    ax = fig.add_subplot(1, 2, 1, polar=True)
    legend_handles = []
    for label, agg in ordered:
        color = palette.get(label, "#777777")
        vals = [100 * agg[d][0] / agg[d][1] if agg[d][1] > 0 else 0 for d in DIMS]
        vals_closed = vals + [vals[0]]
        ax.fill(angles, vals_closed, color=color, alpha=0.12, zorder=2)
        h, = ax.plot(angles, vals_closed, "-", lw=2.0, color=color,
                     marker="o", ms=4, label=f"{label}  ({means[label]:.1f}%)",
                     zorder=4)
        legend_handles.append(h)
    # rotate axis labels outward for readability
    for ang, lab in zip(angles[:-1], DIMS):
        ax.text(ang, 116, lab, ha="center", va="center", fontsize=10.5,
                color="#222222")
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([""] * len(DIMS))
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=8, color="#666")
    ax.set_ylim(0, 100)
    ax.set_rlabel_position(90)
    ax.grid(True, ls=":", alpha=0.55, color="#888")
    ax.spines["polar"].set_color("#cccccc")
    fig.suptitle("BiomniBench-DA capability profile by dimension",
                 fontsize=13, y=0.97, fontweight="bold")
    ax.set_title("% of A-level rubric points earned per dimension\n"
                 "(4 failure-case tasks + infra-failure cells excluded)",
                 fontsize=10, pad=24, color="#555")

    # Side legend with a tidy data table
    ax2 = fig.add_subplot(1, 2, 2)
    ax2.axis("off")
    by_rank = sorted(rows.items(), key=lambda kv: -means[kv[0]])
    cell_text = []
    col_lbls = ["model", "overall"] + [d.replace(" ", "\n", 1) for d in DIMS]
    for label, agg in by_rank:
        row = [label, f"{means[label]:.1f}"]
        for d in DIMS:
            e, m = agg[d]
            row.append(f"{100*e/m:.0f}" if m > 0 else "-")
        cell_text.append(row)
    tbl = ax2.table(cellText=cell_text, colLabels=col_lbls,
                    cellLoc="center", loc="center",
                    colWidths=[0.14, 0.10] + [0.115] * len(DIMS))
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8.5)
    tbl.scale(1, 1.6)
    # color the model name cell to match the polygon
    for r, (label, _) in enumerate(by_rank, start=1):
        c = tbl[r, 0]
        c.set_facecolor(palette.get(label, "#777777"))
        c.set_text_props(color="white", weight="bold")
    for c in range(len(col_lbls)):
        tbl[0, c].set_facecolor("#eeeeee")
        tbl[0, c].set_text_props(weight="bold")
    ax2.set_title("Per-dimension %  (sorted by overall mean)",
                  fontsize=10.5, color="#333", pad=10)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = PROJECT / "reports" / "omicos_radar.png"
    fig.savefig(out, dpi=170, bbox_inches="tight")
    print(f"saved {out}")

    # Also print the numbers
    print("\n%-15s " % "model" + "  ".join(f"{d[:8]:>8s}" for d in DIMS))
    for L, agg in rows.items():
        cells = []
        for d in DIMS:
            e, m = agg[d]
            cells.append(f"{100*e/m:7.1f}%" if m > 0 else "    -   ")
        print("%-15s " % L + "  ".join(cells))


if __name__ == "__main__":
    labels = sys.argv[1:] or [
        "gpt-5.5", "gpt-5.4", "gpt-5.4-mini",
        "ds4-pro", "ds4-flash", "mimo-v2.5-pro", "mimo-v2.5"]
    main(labels)
