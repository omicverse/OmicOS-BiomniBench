#!/usr/bin/env bash
# Benchmark ONE agent model on the full BiomniBench-DA task set.
#
# Usage:
#   bash scripts/bench_model.sh <provider> <model> <label> [-j N] [--tids csv]
#
#   provider   codex | deepseek | custom_openai | gemini   (see docs/model-benchmarking.md)
#   model      provider's model id, e.g. deepseek-v4-pro, gpt-5.5
#   label      run-id == result namespace. One per model. Lands in results/<label>/.
#   -j N       parallel cells (default 4). API-bound; 4-6 is sane.
#   --tids csv re-run only these task ids into an EXISTING label (infra-failure fix).
#
# Each model's results live under results/<label>/ — distinct labels never
# collide, so a new model run cannot overwrite an existing one. configs/
# models.yaml is patched in place for the run and ALWAYS restored on exit.
#
# What is NOT changed (and must stay constant for a fair comparison):
#   - judge_model in models.yaml          (the grader)
#   - team_members in models.yaml         (the agent roster)
#   - everything under ../omicos-admin/   (agent + skill definitions)
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT="$(pwd)"

PROVIDER="${1:?provider (codex|deepseek|custom_openai|gemini)}"
MODEL="${2:?model id, e.g. deepseek-v4-pro}"
LABEL="${3:?run label / run-id, e.g. ds4-pro}"
shift 3 || true
J=4
TIDS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -j) J="${2:?}"; shift 2;;
    --tids) TIDS="${2:?}"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

# Secrets (HF token + provider API keys) and the omicos-core binary.
if [[ -f "$HOME/.claude/secrets.env" ]]; then set -a; source "$HOME/.claude/secrets.env"; set +a; fi
export OMICOS_BIN="${OMICOS_BIN:-$PROJECT/../omicos-core/target/release/omicos}"
[[ -x "$OMICOS_BIN" ]] || { echo "ERROR: OMICOS_BIN not found/executable: $OMICOS_BIN" >&2; exit 4; }
[[ -d .venv ]] || uv sync

MODELS_YAML="$PROJECT/configs/models.yaml"
RUN_DIR="$PROJECT/results/$LABEL"

# Protect prior models' results: refuse to clobber an existing label
# unless --tids is given (the targeted infra-failure re-run path).
if [[ -e "$RUN_DIR" && -z "$TIDS" ]]; then
  echo "ERROR: results/$LABEL already exists. Use a fresh label, or pass --tids to re-run cells." >&2
  exit 3
fi

# Back up models.yaml; restore on ANY exit (success / error / Ctrl-C).
BAK="$(mktemp "${MODELS_YAML}.bench-bak.XXXX")"
cp "$MODELS_YAML" "$BAK"
trap 'cp "$BAK" "$MODELS_YAML"; rm -f "$BAK"; echo "[bench] restored configs/models.yaml"' EXIT

# Patch ONLY agent_model.provider / agent_model.model — line-based so
# every comment and the judge_model / team_members blocks are preserved.
python3 - "$MODELS_YAML" "$PROVIDER" "$MODEL" <<'PY'
import sys
path, prov, model = sys.argv[1:4]
lines = open(path).read().splitlines(keepends=True)
out, in_am, dp, dm = [], False, False, False
for ln in lines:
    s = ln.rstrip("\n")
    if s.startswith("agent_model:"):
        in_am = True; out.append(ln); continue
    if in_am and s and not s[0].isspace() and not s.lstrip().startswith("#"):
        in_am = False
    if in_am and s.lstrip().startswith("provider:") and not dp:
        ind = ln[:len(ln) - len(ln.lstrip())]
        out.append(f"{ind}provider: {prov}\n"); dp = True; continue
    if in_am and s.lstrip().startswith("model:") and not dm:
        ind = ln[:len(ln) - len(ln.lstrip())]
        out.append(f"{ind}model: {model}\n"); dm = True; continue
    out.append(ln)
assert dp and dm, "could not locate agent_model.provider / agent_model.model"
open(path, "w").writelines(out)
PY
echo "[bench] agent_model -> provider=$PROVIDER  model=$MODEL   label=$LABEL  -j=$J"

ARGS=(run --agents vertical_agent_selector --run-id "$LABEL" -j "$J")
[[ -n "$TIDS" ]] && ARGS+=(--tids "$TIDS")
uv run omicos-biomnibench "${ARGS[@]}"

echo
echo "[bench] done -> results/$LABEL"
python3 scripts/bench_compare.py "$LABEL" || true
