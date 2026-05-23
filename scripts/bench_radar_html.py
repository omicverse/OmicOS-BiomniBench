#!/usr/bin/env python3
"""Interactive HTML version of bench_radar.py.

Single polar plot, 7 model polygons overlaid on the BiomniBench-DA
six-dimension framework. Hover any vertex for the exact percentage;
click a model in the legend to toggle it on/off.

  python3 scripts/bench_radar_html.py [<label> ...]
  # -> analysis/omicos_radar.html

The dimension classifier and the per-criterion mapping come from
`analysis/omicos_dim_map.csv` (the audit CSV bench_radar.py writes).
If that file is missing, run `python3 scripts/bench_radar.py` first
to regenerate it (it requires the BiomniBench-DA dataset on disk).
"""
import argparse
import csv
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import plotly.graph_objects as go

PROJECT = Path(__file__).resolve().parents[1]
ANALYSIS = PROJECT / "analysis"
INFRA = {"no_output", "error", "serve_failed", "judge_unavailable"}
FAIL_CASES = {"da-12-4", "da-18-7", "da-19-1", "da-20-1", "da-6-2", "da-8-3"}

DIMS = ["data handling", "method selection", "statistical rigor",
        "biological interpretation", "scientific reasoning", "source reliability"]

PALETTE = {
    "gpt-5.5":       "#1F4FBF",
    "gpt-5.4":       "#4FB99F",
    "gpt-5.4-mini":  "#9DD0C5",
    "ds4-pro":       "#E8894C",
    "ds4-flash":     "#F2BB94",
    "mimo-v2.5-pro": "#A04EBF",
    "mimo-v2.5":     "#C9A5DA",
}


def load_dim_map(path):
    """{(task, criterion_idx): (dim, A_points)}"""
    m = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            m[(r["task"], int(r["criterion"]))] = (r["dimension"],
                                                   int(r["A_points"]))
    return m


def aggregate(label, dim_map):
    """{dim: (earned, max_A)} for one model label."""
    earned = defaultdict(float)
    mx = defaultdict(float)
    for gj in glob.glob(str(
            PROJECT / f"results/{label}/vertical_agent_selector/da-*/grade.json")):
        d = json.load(open(gj))
        if d.get("grade_mode") in INFRA:
            continue
        task = Path(gj).parent.name
        if task in FAIL_CASES:
            continue
        for ck, v in (d.get("criteria") or {}).items():
            # criteria keys come as "criterion_<idx>"
            try:
                idx = int(ck.split("_")[-1])
            except ValueError:
                continue
            key = (task, idx)
            if key not in dim_map:
                continue
            dim, a_pts = dim_map[key]
            if a_pts <= 0:
                continue
            sc = float(v.get("score") or 0)
            earned[dim] += sc
            mx[dim] += a_pts
    return {d: (earned[d], mx[d]) for d in DIMS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="*", default=list(PALETTE),
                    help="Model labels under results/ to plot")
    ap.add_argument("--dim-map", default=str(ANALYSIS / "omicos_dim_map.csv"))
    ap.add_argument("--inline-plotly", action="store_true")
    ap.add_argument("--out", default=str(ANALYSIS / "omicos_radar.html"))
    args = ap.parse_args()

    dim_map_path = Path(args.dim_map)
    if not dim_map_path.exists():
        print(f"dim_map missing: {dim_map_path}\n"
              f"Run `python3 scripts/bench_radar.py` first to regenerate.",
              file=sys.stderr)
        sys.exit(1)
    dim_map = load_dim_map(dim_map_path)

    aggs = {L: aggregate(L, dim_map) for L in args.labels}
    means = {L: sum(100 * e / m if m > 0 else 0 for e, m in agg.values()) / len(DIMS)
             for L, agg in aggs.items()}
    ordered = sorted(args.labels, key=lambda L: -means[L])

    def hex_to_rgba(hx, alpha):
        h = hx.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    fig = go.Figure()
    theta = DIMS + [DIMS[0]]
    for L in ordered:
        agg = aggs[L]
        vals = [100 * agg[d][0] / agg[d][1] if agg[d][1] > 0 else 0 for d in DIMS]
        vals_c = vals + [vals[0]]
        color = PALETTE.get(L, "#777777")
        fig.add_trace(go.Scatterpolar(
            r=vals_c, theta=theta,
            mode="lines+markers",
            line=dict(color=color, width=2.2),
            marker=dict(size=6, color=color),
            fill="toself",
            fillcolor=hex_to_rgba(color, 0.10),
            name=f"{L} ({means[L]:.1f}%)",
            hovertemplate=(
                f"<b>{L}</b><br>"
                "%{theta}: %{r:.1f}%<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=dict(
            text=("<b>BiomniBench-DA capability profile by dimension</b>"
                  "<br><span style='font-size:13px;color:#777'>"
                  "% of A-level rubric points earned per dimension; "
                  "6 failure-case tasks + infra-failure cells excluded"
                  "</span>"),
            x=0.5, xanchor="center", y=0.97,
        ),
        polar=dict(
            radialaxis=dict(range=[0, 100], tickvals=[20, 40, 60, 80, 100],
                            tickfont=dict(size=9, color="#666"),
                            gridcolor="#dadada", angle=90),
            angularaxis=dict(tickfont=dict(size=11, color="#222"),
                             direction="clockwise",
                             gridcolor="#dadada", linecolor="#bbb"),
            bgcolor="white",
        ),
        template="simple_white",
        font=dict(family="IBM Plex Sans, Inter, Helvetica, Arial, sans-serif",
                  size=13, color="#222"),
        width=900, height=720,
        margin=dict(l=40, r=40, t=130, b=40),
        legend=dict(
            x=1.02, y=1.0, xanchor="left", yanchor="top",
            bgcolor="rgba(255,255,255,0.95)", bordercolor="#ccc", borderwidth=1,
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
                                         "filename": "omicos_radar",
                                         "width": 1100, "height": 800, "scale": 2}},
    )
    size_kb = out.stat().st_size / 1024
    print(f"saved {out}  ({size_kb:.0f} KB)")

    # Console summary
    print(f"\n{'model':16s} overall  " + "  ".join(f"{d[:9]:>9s}" for d in DIMS))
    for L in ordered:
        agg = aggs[L]
        vals = [100 * agg[d][0] / agg[d][1] if agg[d][1] > 0 else 0 for d in DIMS]
        print(f"{L:16s} {means[L]:5.1f}%   " + "  ".join(f"{v:7.1f}% " for v in vals))


if __name__ == "__main__":
    main()
