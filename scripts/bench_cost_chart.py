#!/usr/bin/env python3
"""Cost-vs-score scatter for BiomniBench-DA: omicos vs other agent harnesses.

  python3 scripts/bench_cost_chart.py [<label> ...]
        -> reports/omicos_cost_vs_score.png

X = cache-adjusted cost per task (scripts/bench_cost.py).
Y = mean rubric score x100 over all 50 tasks, infra-failure cells excluded
    (failure-case tasks ARE included, for parity with external harnesses).
A Pareto front (min cost, max score) is drawn over every plotted point.

REFERENCE_HARNESSES is read off a published BiomniBench-DA harness
comparison chart — edit it to match your reference, or set it to {} to
plot only omicos. Needs matplotlib (use the omicdev env interpreter).
"""
import glob
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator, FuncFormatter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_cost import cost_per_task, PRICING, INFRA  # noqa: E402

PROJECT = Path(__file__).resolve().parents[1]

# External reference points: harness -> [(label, cost_usd, score), ...].
# Transcribed from a published BiomniBench-DA cost/score chart; their cost
# basis is assumed cache-adjusted real cost. Edit to your own source.
REFERENCE_HARNESSES = {
    "Claude Code": [("Opus 4.7 (max)", 2.5, 73.3), ("Opus 4.6 (max)", 1.35, 69.5),
                    ("Sonnet 4.6 (max)", 0.93, 66.5)],
    "Codex CLI":   [("GPT-5.4 (xhigh)", 2.3, 68.7), ("GPT-5.5 (xhigh)", 4.3, 67.6)],
    "Terminus-2":  [("Opus 4.7 (max)", 0.85, 64.1), ("Sonnet 4.6 (max)", 0.93, 62.5),
                    ("Opus 4.6 (max)", 1.9, 63.2), ("GPT-5.5", 2.0, 63.8),
                    ("GLM-5.1", 0.6, 60.4), ("Qwen 3.6", 1.0, 59.6),
                    ("Kimi K2.6", 0.85, 59.3), ("GPT-5.4", 1.05, 55.3)],
}
REF_STYLE = {"Claude Code": ("#4FB99F", "o", 95),
             "Codex CLI": ("#E8894C", "D", 95),
             "Terminus-2": ("#E07EBE", "v", 95)}


def omicos_score(label):
    """Mean rubric score x100 over all 50 tasks, infra-failure cells excluded."""
    sc = []
    for gj in glob.glob(str(
            PROJECT / f"results/{label}/vertical_agent_selector/da-*/grade.json")):
        d = json.load(open(gj))
        s = d.get("score")
        if s is None or d.get("grade_mode") in INFRA:
            continue
        sc.append(float(s))
    return sum(sc) / len(sc) * 100 if sc else None


def main(labels):
    omicos = []
    for L in labels:
        c, s = cost_per_task(L), omicos_score(L)
        if c and s is not None:
            omicos.append((L, c["cached_usd"], s))
        else:
            print(f"skip {L}: no cost/score data", file=sys.stderr)

    fig, ax = plt.subplots(figsize=(12.5, 7.8))
    series = [(n, REFERENCE_HARNESSES[n], *REF_STYLE[n])
              for n in REFERENCE_HARNESSES]
    series.append(("omicos", omicos, "#3E63C8", "s", 130))

    for name, pts, color, marker, size in series:
        if not pts:
            continue
        ax.scatter([c for _, c, _ in pts], [s for _, _, s in pts], c=color,
                   marker=marker, s=size, label=name, edgecolors="white",
                   linewidths=0.8, zorder=3)
        for lab, c, s in pts:
            ax.annotate(lab, (c, s), textcoords="offset points",
                        xytext=(7, 4), fontsize=7.5, color="#333333")

    allpts = sorted((c, s) for _, pts, *_ in series for _, c, s in pts)
    front, best = [], -1e9
    for c, s in allpts:
        if s > best:
            front.append((c, s)); best = s
    if front:
        ax.plot([c for c, _ in front], [s for _, s in front], "--",
                color="#999999", zorder=2, label="Pareto front (all)")

    ax.set_xscale("log", base=10)
    ax.set_xlim(0.013, 6.0)
    ax.xaxis.set_major_locator(LogLocator(base=10))
    ax.xaxis.set_minor_locator(LogLocator(base=10, subs=tuple(range(2, 10))))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(FuncFormatter(
        lambda v, _: f"{v:g}" if v in (0.02, 0.05, 0.2, 0.5, 2, 5) else ""))
    ax.set_xlabel("Cost per task (USD, log scale)  —  omicos = cache-adjusted "
                  "(~95% prompt-cache hit)", fontsize=11)
    ax.set_ylabel("Mean rubric score (all 50 tasks, infra-fails excluded)",
                  fontsize=11)
    ax.set_title("BiomniBench-DA: cost vs. score by agent harness", fontsize=12)
    ax.grid(True, which="both", ls=":", alpha=0.45)
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    out = PROJECT / "reports" / "omicos_cost_vs_score.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight")
    print(f"saved {out}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(PRICING))
