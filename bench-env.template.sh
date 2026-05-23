#!/usr/bin/env bash
# Template for OmicOS-BiomniBench. Copy to bench-env.sh and fill in the
# secrets, then `source bench-env.sh` before running any sweep.

# === omicos binary path ===
# Point to your locally-installed `omicos` executable. After `pip install omicos`
# (or building from github.com/omicverse/omicos), this should be on PATH.
# Optionally pin a specific build:
# export OMICOS_BIN="$HOME/.local/bin/omicos"

# === Hugging Face — required to download BiomniBench-DA ===
# BiomniBench-DA is gated; accept the dataset terms on
# https://huggingface.co/datasets/phylobio/BiomniBench-DA first.
export HF_TOKEN="<your_hf_token_here>"

# Where the dataset snapshot lives. Default: $(pwd)/data/biomnibench-da
# export OMICOS_BIOMNIBENCH_DATA_ROOT="$(pwd)/data/biomnibench-da"

# === LLM provider API keys — set whichever you'll use ===
# Drives BOTH the omicos agent AND the rubric judge (default DeepSeek-v4-pro).
export DEEPSEEK_API_KEY="<your_deepseek_key_here>"
# export DEEPSEEK_API_BASE="https://api.deepseek.com/v1"

# Optional: Anthropic (matches BiomniBench dataset's bundled judge)
# export ANTHROPIC_API_KEY="<your_anthropic_key>"

# Optional: Gemini (BiomniBench README's named default judge)
# export GEMINI_API_KEY="<your_gemini_key>"

# Optional: any OpenAI-compatible endpoint (MiMo, OpenRouter, etc.)
# export CUSTOM_OPENAI_API_KEY="<key>"
# export CUSTOM_OPENAI_API_BASE="<base_url>"

# Optional: ChatGPT subscription via Codex CLI OAuth (for gpt-5.4 / gpt-5.5)
# Log in once with `codex login`; auth lands at ~/.codex/auth.json.

# === Agent + skill catalog (omicos-admin) ===
# Path to the omicos-admin checkout's agents/ directory. Required.
# export OMICOS_BIOMNIBENCH_AGENTS_DIR="$HOME/omicverse/omicos-admin/agents"

# === Optional: override the rubric judge ===
# export OMICOS_BENCH_JUDGE_MODEL="deepseek-v4-pro"

echo "[bench-env] sourced — omicos binary at: $(command -v omicos || echo 'NOT FOUND, see https://github.com/omicverse/omicos')"
