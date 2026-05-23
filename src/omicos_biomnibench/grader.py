"""Rubric-based judge for BiomniBench-DA — host-side reimplementation.

The dataset ships `tests/llm_judge.py` but that script is hardcoded for
Harbor's container paths (`/tests/`, `/logs/verifier/`, `/app/`) and
won't run from our orchestrator. We mirror its scoring logic here so the
verdict is computed by the *same arithmetic* as the dataset's reference
run, just driven from the host:

  1. Read agent outputs from `<workspace>/trace.md` and
     `<workspace>/answer.txt`.
  2. Read `tests/rubric.txt` from the task's snapshot dir.
  3. Parse rubric into per-criterion `{A: pts, B: pts, C: pts}` maps —
     same regex as the dataset's `parse_rubric_levels`.
  4. Prompt the judge LLM with the same instruction the bundled script
     uses; parse out `{criteria: {criterion_n: {level, reason}}, overall_reasoning}`.
  5. Score = sum of `level→points` lookups (rubric totals to 100); we
     scale to `[0,1]` for consistency with the rest of the harness.
  6. `correct = score >= PASS_THRESHOLD`.

Judge provider order:
  1. Anthropic Claude (`ANTHROPIC_API_KEY`) — matches the dataset's
     bundled `llm_judge.py` exactly. Use this for apples-to-apples vs
     published BiomniBench numbers.
  2. Gemini (`GEMINI_API_KEY`) — the dataset README's named default.
  3. DeepSeek v4-pro — always-available fallback.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# Score >= this threshold counts as "correct" in the binary view. The
# BiomniBench paper doesn't pin a single pass/fail cutoff; 0.7 mirrors
# the rubric-pass convention used in similar process-level benchmarks
# and matches omicos-bixbench's leaderboard cutoff.
PASS_THRESHOLD = 0.7

# Hard cap for how much text we ship into the judge prompt per file.
# trace.md is intended to be markdown-paragraph length; we still cap to
# stay well under provider context windows when the agent overgenerates.
TRACE_CHAR_BUDGET = 80_000
ANSWER_CHAR_BUDGET = 8_000


@dataclass
class GradeResult:
    correct: bool
    score: float                  # 0.0 - 1.0 (rubric_total / 100)
    raw_total: int = 0            # 0 - 100, the rubric-defined point sum
    mode: str = ""                # "anthropic_claude" | "gemini" | "deepseek"
    notes: str = ""
    criteria: dict = field(default_factory=dict)
    judge_raw: str | None = None


# --- rubric parsing (mirrors the dataset's own logic) ----------------------


def parse_rubric_levels(rubric_text: str) -> dict[str, dict[str, int]]:
    """{criterion_n: {"A": pts, "B": pts, "C": pts}}.

    Verbatim port of `tests/llm_judge.py::parse_rubric_levels` so our
    arithmetic matches the dataset's reference behavior.
    """

    out: dict[str, dict[str, int]] = {}
    parts = re.split(r"^Criterion\s+(\d+)\s*:", rubric_text, flags=re.MULTILINE)
    for i in range(1, len(parts), 2):
        n = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        levels: dict[str, int] = {}
        m = re.search(r"Levels:\s*((?:[A-Z]=\d+\s*)+)", body)
        if m:
            for lm in re.finditer(r"([A-Z])=(\d+)", m.group(1)):
                levels[lm.group(1).upper()] = int(lm.group(2))
        if not levels:
            for lm in re.finditer(r"\[([A-Z])\]\s*\(\s*(\d+)\s*points?\s*\)", body):
                levels[lm.group(1).upper()] = int(lm.group(2))
        if levels:
            out[f"criterion_{n}"] = levels
    return out


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    head = s[: n // 2]
    tail = s[-n // 2 :]
    return head + f"\n\n…[truncated {len(s) - n} chars]…\n\n" + tail


def _build_judge_prompt(rubric: str, trace: str, answer: str) -> str:
    """Same shape as the bundled `tests/llm_judge.py` prompt."""

    trace_text = trace if trace else "[No trace file provided]"
    answer_text = answer if answer else "[No answer file provided]"
    return (
        "You are an expert evaluator for a data analysis task.\n\n"
        "Evaluate the agent's work using the following rubric:\n\n"
        f"{rubric}\n\n"
        "Here is the agent's analysis trace:\n\n"
        f"<trace>\n{trace_text}\n</trace>\n\n"
        "Here is the agent's final answer:\n\n"
        f"<answer>\n{answer_text}\n</answer>\n\n"
        "For each criterion in the rubric, choose ONE level: A, B, or C — "
        "based purely on which level description best describes the agent's "
        "work. Do not output numerical points; the score for each level is "
        "computed automatically from the rubric.\n\n"
        "You MUST respond with a JSON object in exactly this format:\n"
        "{\n"
        '  "criteria": {\n'
        '    "criterion_1": {"level": "A", "reason": "<one-sentence explanation>"},\n'
        '    "criterion_2": {"level": "B", "reason": "<one-sentence explanation>"},\n'
        "    ...\n"
        "  },\n"
        '  "overall_reasoning": "<short summary>"\n'
        "}\n\n"
        'Each "level" value must be exactly the single character "A", "B", '
        'or "C". Only output the JSON object, nothing else.'
    )


# --- provider shims --------------------------------------------------------


def _call_anthropic(prompt: str, model: str) -> str:
    """Call Anthropic Messages API via raw HTTPS — we don't add the SDK as
    a hard dependency since the bundled judge uses it under uv-run."""

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    base = os.environ.get(
        "ANTHROPIC_API_BASE", "https://api.anthropic.com/v1",
    ).rstrip("/")
    headers = {
        "x-api-key": key,
        "anthropic-version": os.environ.get("ANTHROPIC_VERSION", "2023-06-01"),
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = httpx.post(f"{base}/messages", headers=headers, json=body, timeout=180.0)
    r.raise_for_status()
    payload = r.json()
    blocks = payload.get("content") or []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            return b.get("text", "")
    raise RuntimeError(f"Anthropic returned no text block: {payload}")


def _call_gemini(prompt: str, model: str) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    base = os.environ.get(
        "GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta",
    ).rstrip("/")
    url = f"{base}/models/{model}:generateContent?key={key}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    r = httpx.post(url, json=body, timeout=180.0)
    r.raise_for_status()
    payload = r.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {payload}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if not text:
        raise RuntimeError(f"Gemini returned empty text: {payload}")
    return text


def _call_deepseek(prompt: str, model: str) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    base = os.environ.get(
        "DEEPSEEK_API_BASE", "https://api.deepseek.com/v1",
    ).rstrip("/")
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    r = httpx.post(
        f"{base}/chat/completions",
        headers={
            "authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
        json=body,
        timeout=180.0,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# --- response parser -------------------------------------------------------


def _parse_last_json_object(s: str) -> dict | None:
    """Find and parse the LAST `{...}` JSON object in a string.

    Mirrors the brace-matching walk in the bundled judge so judges that
    print rationale text before the JSON still work.
    """

    s = s.strip()
    if not s:
        return None
    start_idx = s.find("{")
    if start_idx < 0:
        return None
    brace_count = 0
    end_idx = start_idx
    for i in range(start_idx, len(s)):
        c = s[i]
        if c == "{":
            brace_count += 1
        elif c == "}":
            brace_count -= 1
            if brace_count == 0:
                end_idx = i + 1
                break
    try:
        return json.loads(s[start_idx:end_idx])
    except json.JSONDecodeError:
        # Fall back to the last balanced object in the string.
        end = s.rfind("}")
        if end < 0:
            return None
        depth = 0
        for i in range(end, -1, -1):
            ch = s[i]
            if ch == "}":
                depth += 1
            elif ch == "{":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[i : end + 1])
                    except json.JSONDecodeError:
                        return None
        return None


def _score_from_criteria(
    criteria: dict,
    rubric_levels: dict[str, dict[str, int]],
) -> tuple[int, dict]:
    """Sum per-criterion points by mapping each `{level: "A|B|C"}` to its
    rubric-defined value. Returns (total_0_to_100, enriched_criteria_dict).

    Mirrors the loop in `tests/llm_judge.py` so flips here match flips
    the dataset's reference judge would produce."""

    total = 0
    enriched: dict = {}
    for key, value in criteria.items():
        if not isinstance(value, dict):
            continue
        allowed = rubric_levels.get(key) or {}
        level = (value.get("level") or "").strip().upper()
        if level in allowed:
            pts = allowed[level]
        elif "score" in value:
            # Legacy fallback: judge returned a numeric score; snap to nearest
            # allowed level. Matches the bundled judge's behavior.
            try:
                stated = int(value.get("score", 0))
            except (TypeError, ValueError):
                stated = 0
            pts = (
                min(allowed.values(), key=lambda v: abs(v - stated))
                if allowed else 0
            )
        else:
            pts = 0
        total += int(pts)
        enriched[key] = {
            "level": level,
            "score": int(pts),
            "reason": value.get("reason", ""),
        }
    return max(0, min(100, total)), enriched


# --- public entry point ----------------------------------------------------


def grade(
    *,
    rubric: str,
    workspace: Path,
    judge_cfg: dict,
) -> GradeResult:
    """Grade one cell.

    Reads `<workspace>/trace.md` + `<workspace>/answer.txt`, applies the
    rubric via the configured judge LLM, returns a 0–1 score plus the
    raw 0–100 rubric total and per-criterion verdicts.
    """

    trace_path = workspace / "trace.md"
    answer_path = workspace / "answer.txt"
    trace = trace_path.read_text(encoding="utf-8") if trace_path.is_file() else ""
    answer = answer_path.read_text(encoding="utf-8") if answer_path.is_file() else ""

    if not trace and not answer:
        return GradeResult(
            correct=False,
            score=0.0,
            raw_total=0,
            mode="no_output",
            notes="agent produced neither trace.md nor answer.txt",
        )

    rubric_levels = parse_rubric_levels(rubric)
    prompt = _build_judge_prompt(
        rubric=rubric,
        trace=_truncate(trace, TRACE_CHAR_BUDGET),
        answer=_truncate(answer, ANSWER_CHAR_BUDGET),
    )

    # Provider order: Anthropic (matches bundled judge) → Gemini (README
    # default) → DeepSeek (always-available fallback). Honors explicit
    # override from configs/models.yaml.
    provider = (judge_cfg.get("provider") or "").lower()
    model = judge_cfg.get("model", "")
    raw = ""
    used_mode = ""
    last_error: Exception | None = None

    chain: list[tuple[str, str]] = []
    if provider == "anthropic":
        chain.append(("anthropic", model or "claude-opus-4-7"))
    elif provider == "gemini":
        chain.append(("gemini", model or "gemini-3.1-pro"))
    elif provider == "deepseek" or provider == "custom_openai":
        chain.append(("deepseek", model or "deepseek-v4-pro"))
    # Auto-fallbacks (only added if not already at head of chain).
    for default in [
        ("anthropic", "claude-opus-4-7"),
        ("gemini", "gemini-3.1-pro"),
        ("deepseek", "deepseek-v4-pro"),
    ]:
        if not chain or chain[0][0] != default[0]:
            chain.append(default)

    for mode, mdl in chain:
        try:
            if mode == "anthropic":
                raw = _call_anthropic(prompt, mdl)
            elif mode == "gemini":
                raw = _call_gemini(prompt, mdl)
            else:
                raw = _call_deepseek(prompt, mdl)
            used_mode = mode
            break
        except Exception as e:
            last_error = e
            continue

    if not used_mode:
        return GradeResult(
            False, 0.0, 0, "judge_unavailable",
            notes=f"all judge providers failed: {last_error}",
        )

    parsed = _parse_last_json_object(raw)
    if parsed is None:
        return GradeResult(
            False, 0.0, 0, used_mode,
            notes="judge did not emit parseable JSON",
            judge_raw=raw,
        )
    criteria = parsed.get("criteria") or {}
    reasoning = parsed.get("overall_reasoning") or parsed.get("reasoning") or ""
    raw_total, enriched = _score_from_criteria(criteria, rubric_levels)
    score = raw_total / 100.0

    return GradeResult(
        correct=score >= PASS_THRESHOLD,
        score=score,
        raw_total=raw_total,
        mode=used_mode,
        notes=str(reasoning)[:2048],
        criteria=enriched,
        judge_raw=raw,
    )
