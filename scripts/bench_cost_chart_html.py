#!/usr/bin/env python3
"""Interactive HTML version of bench_cost_chart.py.

Cost-vs-score scatter on a log x-axis: every omicos model run +
optional external-harness comparison points + a Pareto front. Hover
any marker for the exact numbers.

  python3 scripts/bench_cost_chart_html.py [<label> ...]
  # -> analysis/omicos_cost_vs_score.html
"""
import argparse
import glob
import json
import sys
from pathlib import Path

import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_cost import cost_per_task, PRICING, INFRA   # noqa: E402

PROJECT = Path(__file__).resolve().parents[1]
ANALYSIS = PROJECT / "analysis"

# External reference points, mirrored from bench_cost_chart.py.
REFERENCE_HARNESSES = {
    "Claude Code": [("Opus 4.7 (max)", 2.5, 73.3), ("Opus 4.6 (max)", 1.35, 69.5),
                    ("Sonnet 4.6 (max)", 0.93, 66.5)],
    "Codex CLI":   [("GPT-5.4 (xhigh)", 2.3, 68.7), ("GPT-5.5 (xhigh)", 4.3, 67.6)],
    "Terminus-2":  [("Opus 4.7 (max)", 0.85, 64.1), ("Sonnet 4.6 (max)", 0.93, 62.5),
                    ("Opus 4.6 (max)", 1.9, 63.2), ("GPT-5.5", 2.0, 63.8),
                    ("GLM-5.1", 0.6, 60.4), ("Qwen 3.6", 1.0, 59.6),
                    ("Kimi K2.6", 0.85, 59.3), ("GPT-5.4", 1.05, 55.3)],
}
HARNESS_STYLE = {
    "Claude Code": dict(color="#4FB99F", symbol="circle"),
    "Codex CLI":   dict(color="#E8894C", symbol="diamond"),
    "Terminus-2":  dict(color="#E07EBE", symbol="triangle-down"),
    "omicos":      dict(color="#3E63C8", symbol="square"),
}


def omicos_score(label):
    sc = []
    for gj in glob.glob(str(
            PROJECT / f"results/{label}/vertical_agent_selector/da-*/grade.json")):
        d = json.load(open(gj))
        s = d.get("score")
        if s is None or d.get("grade_mode") in INFRA:
            continue
        sc.append(float(s))
    return sum(sc) / len(sc) * 100 if sc else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="*", default=list(PRICING))
    ap.add_argument("--inline-plotly", action="store_true")
    ap.add_argument("--out", default=str(ANALYSIS / "omicos_cost_vs_score.html"))
    args = ap.parse_args()

    omicos_pts = []
    for L in args.labels:
        c = cost_per_task(L)
        s = omicos_score(L)
        if c and s is not None:
            omicos_pts.append((L, c["cached_usd"], s, c["n"],
                               c["cache_hit"], c["in_tok"]))

    fig = go.Figure()
    all_pts = []

    # External harnesses
    for name, pts in REFERENCE_HARNESSES.items():
        if not pts:
            continue
        style = HARNESS_STYLE[name]
        xs = [c for _, c, _ in pts]
        ys = [s for _, _, s in pts]
        labels = [lab for lab, _, _ in pts]
        hovers = [(f"<b>{name}</b><br>{lab}<br>"
                   f"cost: ${c:.2f}<br>score: {s:.1f}<extra></extra>")
                  for lab, c, s in pts]
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers+text",
            marker=dict(size=12, color=style["color"], symbol=style["symbol"],
                        line=dict(color="white", width=1.2)),
            text=labels, textposition="top center",
            textfont=dict(size=9, color="#444"),
            name=name,
            hovertemplate=hovers,
        ))
        all_pts.extend((c, s) for _, c, s in pts)

    # omicos points
    if omicos_pts:
        style = HARNESS_STYLE["omicos"]
        xs = [c for _, c, _, *_ in omicos_pts]
        ys = [s for _, _, s, *_ in omicos_pts]
        labels = [L for L, *_ in omicos_pts]
        hovers = [(f"<b>omicos / {L}</b><br>"
                   f"cost: ${c:.3f}<br>score: {s:.1f}<br>cells: {n}<br>"
                   f"cache hit (est): {100*ch:.1f}%<br>"
                   f"in_tok mean: {in_tok:,.0f}<extra></extra>")
                  for L, c, s, n, ch, in_tok in omicos_pts]
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="markers+text",
            marker=dict(size=16, color=style["color"], symbol=style["symbol"],
                        line=dict(color="white", width=1.5)),
            text=labels, textposition="top center",
            textfont=dict(size=10, color="#222", family="IBM Plex Sans, Inter"),
            name="omicos",
            hovertemplate=hovers,
        ))
        all_pts.extend((c, s) for _, c, s, *_ in omicos_pts)

    # Pareto front
    all_pts.sort()
    front, best = [], -1e9
    for c, s in all_pts:
        if s > best:
            front.append((c, s)); best = s
    if front:
        fig.add_trace(go.Scatter(
            x=[c for c, _ in front], y=[s for _, s in front],
            mode="lines",
            line=dict(color="#999", width=1.2, dash="dash"),
            name="Pareto front (all harnesses)", hoverinfo="skip",
        ))

    fig.update_xaxes(
        type="log", title="Cost per task (USD, log scale, cache-adjusted)",
        gridcolor="#e0e0e0", showline=True, linecolor="#888", mirror=True,
    )
    fig.update_yaxes(
        title="Mean rubric score (BiomniBench-DA, all 50 tasks, infra excluded)",
        gridcolor="#e0e0e0", showline=True, linecolor="#888", mirror=True,
    )
    fig.update_layout(
        title=dict(
            text=("<b>BiomniBench-DA — cost vs score by agent harness</b>"
                  "<br><span style='font-size:13px;color:#777'>"
                  "omicos = cache-adjusted; external harnesses transcribed "
                  "from a published comparison chart"
                  "</span>"),
            x=0.5, xanchor="center", y=0.97,
        ),
        template="simple_white",
        font=dict(family="IBM Plex Sans, Inter, Helvetica, Arial, sans-serif",
                  size=13, color="#222"),
        width=1100, height=720,
        margin=dict(l=70, r=40, t=110, b=70),
        legend=dict(
            x=0.99, y=0.02, xanchor="right", yanchor="bottom",
            bgcolor="rgba(255,255,255,0.92)", bordercolor="#ccc", borderwidth=1,
            font=dict(size=11),
        ),
        hoverlabel=dict(bgcolor="white", font=dict(size=12), bordercolor="#888"),
    )

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    fig.write_html(
        str(out),
        include_plotlyjs=("inline" if args.inline_plotly else "cdn"),
        full_html=True,
        config={"displaylogo": False, "responsive": True,
                "toImageButtonOptions": {"format": "png",
                                         "filename": "omicos_cost_vs_score",
                                         "width": 1400, "height": 900, "scale": 2}},
    )
    size_kb = out.stat().st_size / 1024
    print(f"saved {out}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
