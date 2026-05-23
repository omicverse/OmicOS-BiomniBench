#!/usr/bin/env python3
"""Cost per task for BiomniBench-DA model runs.

  python3 scripts/bench_cost.py [<label> ...]

For each run label (a run-id under runs/, one per model) reports per-task
tokens, NAIVE cost (no prompt caching) and CACHE-ADJUSTED cost.

Why two numbers — a BiomniBench task is a long agent loop; every LLM call
resends the growing conversation, so cumulative `input_tokens` reaches
1-2M per task. But ~95% of that is an unchanged prefix that prompt
caching bills at a steep discount. The usage log records only the total
`input_tokens` (cached + uncached combined), with no breakdown, so the
cache-adjusted figure is ESTIMATED: per cell, sort the per-call
input-token counts by time and treat only the positive increments as
fresh (uncached) input; the rest is a cache hit. This assumes the cache
stays warm between calls, so the cache-adjusted number is a best-case
(lower-bound) cost; the truth sits between naive and cache-adjusted.

Keep PRICING current from each provider's public pricing page.
"""
import glob
import json
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]

# (input, cached_input, output) USD per 1M tokens — keyed by run label.
# Public list prices as of 2026-05. cached_input: OpenAI/codex = 10% of
# input (90%-off cache reads); DeepSeek cache-hit is near-zero; MiMo does
# not publish a cache price (10% assumed — flag when it matters).
PRICING = {
    "gpt-5.5":       (5.00, 0.5000, 30.00),
    "gpt-5.4":       (2.50, 0.2500, 15.00),
    "gpt-5.4-mini":  (0.75, 0.0750, 4.50),
    "ds4-flash":     (0.14, 0.0028, 0.28),
    "ds4-pro":       (1.74, 0.0174, 3.48),   # list price; a 75%-off promo ran to 2026-05-31
    "mimo-v2.5":     (0.40, 0.0400, 2.00),
    "mimo-v2.5-pro": (1.00, 0.1000, 3.00),
}

INFRA = {"no_output", "error", "serve_failed", "judge_unavailable"}


def _cell_tokens(cell_dir):
    """(total_input, fresh_input, output) for one cell from its usage log.

    fresh_input = sum of positive per-call input-token increments (the
    genuinely-new / uncached part). total - fresh = cache hits.
    """
    uf = glob.glob(f"{cell_dir}/workspace/.omicos/usage/*.jsonl")
    if not uf:
        return None
    calls = []
    for line in open(uf[0]):
        try:
            o = json.loads(line)
        except Exception:
            continue
        calls.append((o.get("timestamp_ms", 0),
                      o.get("input_tokens") or 0,
                      o.get("output_tokens") or 0))
    if not calls:
        return None
    calls.sort()
    seq = [c[1] for c in calls]
    out = sum(c[2] for c in calls)
    fresh = seq[0] + sum(max(0, seq[i] - seq[i - 1]) for i in range(1, len(seq)))
    return sum(seq), fresh, out


def cost_per_task(label, pricing=PRICING):
    """Per-task token + cost stats for a run label, or None if unavailable."""
    p = pricing.get(label)
    if p is None:
        return None
    pin, pcache, pout = p
    tot_in = tot_fresh = tot_out = 0
    n = 0
    for gj in glob.glob(str(
            PROJECT / f"runs/{label}/vertical_agent_selector/da-*/grade.json")):
        if json.load(open(gj)).get("grade_mode") in INFRA:
            continue
        tk = _cell_tokens(os.path.dirname(gj))
        if tk is None:
            continue
        ti, tf, to = tk
        tot_in += ti; tot_fresh += tf; tot_out += to; n += 1
    if n == 0:
        return None
    cached = tot_in - tot_fresh
    naive = (tot_in * pin + tot_out * pout) / 1e6 / n
    adj = (tot_fresh * pin + cached * pcache + tot_out * pout) / 1e6 / n
    return {"label": label, "n": n,
            "in_tok": tot_in / n, "out_tok": tot_out / n,
            "fresh_tok": tot_fresh / n, "cache_hit": cached / tot_in,
            "naive_usd": naive, "cached_usd": adj}


if __name__ == "__main__":
    labels = sys.argv[1:] or list(PRICING)
    print("%-14s %5s %12s %12s %8s %11s %12s" % (
        "model", "n", "in_tok/task", "out_tok/task", "cache%",
        "naive $/tk", "cached $/tk"))
    print("-" * 78)
    for L in labels:
        r = cost_per_task(L)
        if r is None:
            print("%-14s  (no pricing entry or no run data)" % L)
            continue
        print("%-14s %5d %12d %12d %7.1f%% %11.2f %12.2f" % (
            r["label"], r["n"], r["in_tok"], r["out_tok"],
            100 * r["cache_hit"], r["naive_usd"], r["cached_usd"]))
