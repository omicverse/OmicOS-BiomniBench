# Grading deviations from the BiomniBench-DA reference verifier

Every place where this harness's verdict could systematically differ from
the dataset's own `tests/llm_judge.py` is recorded here. Reports under
`reports/<run_id>/summary.md` are **not** directly comparable to the
BiomniBench paper's leaderboard numbers once any deviation is in effect;
this doc is the source of truth for what "passed" means here.

The numbering matches the bixbench convention so cross-benchmark deviation
entries can be referenced symmetrically.

---

## DEV-1 — Judge LLM swap (Anthropic Claude → DeepSeek v4-pro)

**Where**: `src/omicos_biomnibench/grader.py::grade`, default provider in
`configs/models.yaml::judge_model`.

**What the dataset does**: `tests/llm_judge.py` imports the Anthropic
SDK and invokes `client.messages.create(model=os.getenv("MODEL_NAME"))`.
Harbor injects `MODEL_NAME` at runtime; the dataset's published reference
runs use a Claude model.

**What we do**: Default judge is **DeepSeek v4-pro** through DeepSeek's
OpenAI-compatible Chat Completions endpoint. The grader honors a
configured `provider` and auto-falls-back along
`(anthropic → gemini → deepseek)` for whichever API key is exported, so
setting `ANTHROPIC_API_KEY` switches to a Claude-driven judge with no
code change.

**Why**: Same judge across `omicos-bixbench` (DeepSeek v4-pro) and
`omicos-biomnibench` means cross-benchmark score deltas are attributable
to the benchmark, not to judge drift.

**What stays identical to reference**:
- The prompt template (verbatim copy of the bundled judge's user prompt).
- The rubric A/B/C → points parser (verbatim port of
  `parse_rubric_levels`).
- The per-criterion → total summation (verbatim port).
- The pass/fail boundary on the 100-point scale.

So the **arithmetic** matches; only the **judge model** differs. To
reproduce the dataset's reference setup exactly, export
`ANTHROPIC_API_KEY` and set the judge model in `configs/models.yaml`
to a Claude id.

**How to revert**: set `provider: anthropic` and `model: claude-opus-4-7`
(or whichever Claude id matches the dataset's run) in
`configs/models.yaml::judge_model`, and export `ANTHROPIC_API_KEY`.

---

## DEV-2 — `task.toml [verifier.env]` discrepancy

**Where**: Every task ships `task.toml` with:

```toml
[verifier.env]
GEMINI_API_KEY = "${GEMINI_API_KEY}"
MODEL_NAME = "gemini-3.1-pro"
```

…but the bundled `tests/llm_judge.py` imports the Anthropic SDK and
expects `ANTHROPIC_API_KEY`. Passing a Gemini model id to the Anthropic
SDK would fail.

**What we do**: We treat the `task.toml [verifier.env]` block as
informational only and use our own `judge_model` config. The dataset's
README explicitly cites Gemini 3.1 Pro as the default verifier, so the
toml block likely represents the intended-but-not-yet-shipped state; our
auto-fallback chain accommodates either provider.

**No revert needed** — this is a passive note, not a code-level change.

---

## DEV-3 — Output-path remapping (`/app/...` → workspace-relative)

**Where**: `src/omicos_biomnibench/matrix.py::_user_prompt`.

**What the dataset specifies**: Agents must write `/app/trace.md` and
`/app/answer.txt`. Harbor runs the agent inside a container where `/app/`
is the bind-mounted workspace.

**What we do**: We instruct the agent to write `./trace.md` and
`./answer.txt` (workspace-relative). `omicos serve` runs the agent's
tool calls with `cwd = workspace`, so this maps one-to-one to the
container path. The grader looks for `<workspace>/trace.md` and
`<workspace>/answer.txt`.

**Why**: There is no `/app/` on the host. Re-mapping to CWD preserves
the contract semantically.

**How to revert**: not applicable — `/app/` is a container-only path.
