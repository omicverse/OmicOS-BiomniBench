# Benchmarking a model on BiomniBench-DA

How to run the full 50-task BiomniBench-DA suite under any agent model,
get a comparable score, and **not disturb results that already exist**.

Two scripts do everything:

| Script | Purpose |
|---|---|
| `scripts/bench_model.sh` | Run all 50 tasks under one model, into a labelled result namespace |
| `scripts/bench_compare.py` | Aggregate / compare runs; find & fix infra-failure cells |

## Quick start

```bash
# Benchmark one model (provider, model-id, label):
bash scripts/bench_model.sh deepseek deepseek-v4-pro  ds4-pro
bash scripts/bench_model.sh codex    gpt-5.5          gpt-5.5
bash scripts/bench_model.sh custom_openai  qwen3-max  qwen3-max

# Compare any set of finished runs:
python3 scripts/bench_compare.py gpt-5.5 ds4-flash ds4-pro
```

Each run takes ~1-2 h (50 tasks, `-j 4`). Results land in `runs/<label>/`.

## How a new run cannot disturb existing results

This is the core safety property. Four independent guarantees:

1. **Result namespacing by `--run-id`.** Every model writes to its own
   `runs/<label>/` tree. `bench_model.sh` **refuses to start** if
   `runs/<label>/` already exists (unless you pass `--tids` to re-run
   specific cells). Pick a fresh label per model → no run can overwrite
   another.
2. **`configs/models.yaml` is backed up and auto-restored.** The script
   patches only `agent_model.provider` / `agent_model.model`, line-based,
   so every comment and the other blocks are preserved. A `trap` restores
   the file on *any* exit — success, error, or Ctrl-C.
3. **Already-finished runs are immutable.** Grading is per-cell
   (`runs/<label>/.../grade.json`) and written once. Nothing re-touches a
   prior run's files. (`omicos-biomnibench regrade` is the *only* command
   that rewrites grades, and it is never called by these scripts.)
4. **The agent/skill source tree is not touched.** The scripts only edit
   `models.yaml`. Agent + skill definitions live in `../omicos-admin/` and
   stay fixed.

## Hold these constant for a fair comparison

The benchmark measures the *model*. Everything else must be identical
across the models you compare:

- **`judge_model`** in `models.yaml` — the grader. Never change it mid-
  campaign (a different judge shifts every score).
- **`team_members`** in `models.yaml` — the agent roster `agent_select`
  routes against.
- **`../omicos-admin/agents/*` and `skills/*`** — the agent and skill
  definitions. If you edit an agent/skill, every prior run becomes
  non-comparable; re-run all models.
- **The omicos-core binary** (`OMICOS_BIN`). Rebuilding it is fine
  *between* campaigns, not *within* one.

`bench_model.sh` changes none of these — it only swaps `agent_model`.

## Adding a model

`provider` selects the wire protocol and which API key is read:

| provider | model examples | API key env (in `~/.claude/secrets.env`) |
|---|---|---|
| `codex` | `gpt-5.5` | Codex OAuth (`~/.omicos` auth) |
| `deepseek` | `deepseek-v4-pro`, `deepseek-v4-flash` | `DEEPSEEK_API_KEY` (+ `DEEPSEEK_API_BASE`) |
| `custom_openai` | any OpenAI-compatible model | `CUSTOM_OPENAI_API_KEY` + `CUSTOM_OPENAI_API_BASE` |
| `gemini` | Gemini models | Gemini auth |

To test a new OpenAI-compatible endpoint: export `CUSTOM_OPENAI_API_BASE`
and `CUSTOM_OPENAI_API_KEY`, then
`bash scripts/bench_model.sh custom_openai <model-id> <label>`.

## Infra failures — a 0.00 that is NOT the model's fault

Some cells fail for environment reasons, not model capability. They show
up in `grade.json` as `grade_mode`:

| `grade_mode` | meaning | fix |
|---|---|---|
| `no_output` / `error` | agent produced no `trace.md`/`answer.txt` | **re-run** the cell |
| `judge_unavailable` | output exists, the grader API was down | **re-grade** only (cheap) |

`bench_compare.py` excludes these from the mean and flags them. To fix:

```bash
python3 scripts/bench_compare.py --infra <label>     # lists cells + the exact fix command

# output missing -> re-run those cells under the same model:
bash scripts/bench_model.sh <provider> <model> <label> --tids da-x-y,da-z-w

# output exists, judge was down -> re-grade in place (no re-run):
uv run python scripts/bench_compare.py --regrade-stale <label>
```

Always clear infra failures before trusting a model's mean.

## Comparing

```bash
python3 scripts/bench_compare.py <labelA> <labelB> ...
```

Prints, per model, `capability mean` (excludes the 4 documented
failure-case tasks in `docs/failure-cases/` **and** any infra-failure
cells), plus a side-by-side per-task table.

**best-of-N vs single-run.** A score that is the max over many historical
runs is *not* comparable to a fresh single run — best-of-N is unbeatable
by construction. For a fair comparison, run **every** model once, fresh,
with the current code, and compare those single runs.

## Cost per task

```bash
python3 scripts/bench_cost.py gpt-5.5 ds4-flash ds4-pro      # cost table
python3 \
    scripts/bench_cost_chart.py gpt-5.5 ds4-flash ds4-pro    # cost-vs-score scatter
```

`bench_cost.py` reports two numbers per model:

- **naive** — `input_tokens x price`, ignoring prompt caching. A BiomniBench
  task is a long agent loop that resends the growing conversation every
  call, so cumulative input is 1-2M tokens/task — naive cost massively
  overstates the bill.
- **cache-adjusted** — the usage log records only total `input_tokens`
  (cached + uncached merged), so this is ESTIMATED: per cell, sort the
  per-call input counts by time and treat only the positive increments
  as fresh (uncached); the rest is a cache hit (~95% in practice). It
  assumes a warm cache, so it is a best-case lower bound; the true cost
  sits between the two.

Keep the `PRICING` table in `bench_cost.py` current from each provider's
public pricing page. `bench_cost_chart.py` plots cache-adjusted cost vs.
rubric score; edit its `REFERENCE_HARNESSES` block to compare against an
external chart, or empty it to plot only omicos.

## Concurrency & rate limits

`-j` is the number of parallel cells (default 4). Each cell is one
`omicos serve` + Python kernel (~1-3 GB RAM). The real limit is the
provider's API rate limit, not local resources:

- One provider, `-j 4-6` is usually safe; higher risks throttling.
- Two models on **different** API platforms (e.g. `codex` + `deepseek`)
  do **not** share a rate limit — they can run in parallel. To do so,
  start the first run, wait for its `[matrix] N cell(s) to run` line
  (`agent_model` is read once, at that point), then start the second.
- A provider that stalls a streaming response is bounded by the
  omicos-core client `read_timeout` + retry (4 attempts); a cell can
  still fail, but it will not hang the matrix forever.
