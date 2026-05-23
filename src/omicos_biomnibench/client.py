"""SSE client for `POST /api/agent/chat/stream`.

Differs from omicos-bixbench's client in one place: BiomniBench's verifier
grades the **full analytical trajectory**, not just the final answer. We
therefore persist a structured `trajectory.jsonl` next to the raw SSE log,
with one record per assistant segment / tool call.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from httpx_sse import connect_sse

FINAL_ANSWER_RE = re.compile(
    r"FINAL\s*ANSWER\s*[:\-]\s*(.+?)\s*$",
    re.IGNORECASE | re.DOTALL | re.MULTILINE,
)


@dataclass
class TrajectoryStep:
    """One persisted reasoning / tool record from the SSE stream."""

    kind: str                # "assistant" | "tool_call" | "tool_result"
    content: Any             # text for assistant, dict for tools
    seq: int = 0


@dataclass
class TurnResult:
    final_text: str
    final_answer: str
    trajectory: list[TrajectoryStep] = field(default_factory=list)
    events: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    sse_log: Path | None = None
    trajectory_log: Path | None = None
    elapsed_s: float = 0.0


def _extract_final_answer(text: str) -> str:
    m = FINAL_ANSWER_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _assistant_text_from_step(step: Any) -> str:
    if not isinstance(step, dict):
        return ""
    role = step.get("role") or step.get("author") or ""
    if role and role not in ("assistant", "step"):
        return ""
    content = step.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    if isinstance(step.get("text"), str):
        return step["text"]
    return ""


def _summarize_tool_call(content: dict) -> dict | None:
    """Pull out just the (name, args, output) tuple from a `step` payload's
    `tool_calls` array. Truncate any single field to 4 KB so the trajectory
    log stays bounded — the rubric judge cares about the *shape* of the
    trajectory, not the verbatim 200 MB dataframe a tool printed."""

    tcs = content.get("tool_calls") or []
    if not tcs:
        return None
    rendered = []
    for tc in tcs:
        if not isinstance(tc, dict):
            continue
        name = tc.get("name") or tc.get("function", {}).get("name") or "<unknown>"
        args = tc.get("arguments") or tc.get("function", {}).get("arguments") or ""
        out = tc.get("output") or tc.get("result") or ""
        rendered.append({
            "name": str(name),
            "arguments": _truncate(str(args), 4096),
            "output": _truncate(str(out), 4096),
        })
    if not rendered:
        return None
    return {"tool_calls": rendered}


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 20] + f"…[truncated {len(s)-n+20} chars]"


def run_turn(
    *,
    base_url: str,
    agent_id: str,
    user_message: str,
    model_cfg: dict,
    sse_log: Path | None = None,
    trajectory_log: Path | None = None,
    timeout_s: float = 1800.0,
) -> TurnResult:
    """Open one streamed chat turn, persist trajectory, return final answer."""

    session_id = str(uuid.uuid4())

    # `team_members` is the candidate roster the active agent can see.
    # Two regimes:
    #   * `vertical_agent_selector` (omicos-core PR #178) needs the FULL
    #     worker roster visible so its `agent_select` tool can rank
    #     them against the task instruction. We read the list from
    #     `model_cfg["team_members"]` (configured in models.yaml).
    #   * Any other agent — collapse to `[agent_id]` so the system
    #     prompt doesn't carry sibling-agent summaries that drown out
    #     the active agent's own rules. (See omicos-bixbench client.py
    #     for the rationale — non-selector agents tend to regress when
    #     the team summary takes up >25% of system prompt depth.)
    configured_team = model_cfg.get("team_members") or []
    if agent_id == "vertical_agent_selector":
        if not configured_team:
            raise RuntimeError(
                "vertical_agent_selector requires team_members in "
                "models.yaml — it has nothing to route to."
            )
        team_members = list(configured_team)
        if agent_id not in team_members:
            team_members.insert(0, agent_id)
    else:
        team_members = [agent_id]

    config = {
        "provider": model_cfg.get("provider", "custom_openai"),
        "model": model_cfg.get("model", "deepseek-v4-pro"),
        "agent": agent_id,
        "team_members": team_members,
        "permission_mode": model_cfg.get("permission_mode", "full"),
        "allow_shell": bool(model_cfg.get("allow_shell", True)),
        "allow_file_write": bool(model_cfg.get("allow_file_write", True)),
        "max_tool_iterations": int(model_cfg.get("max_tool_iterations", 150)),
        "model_context_window": int(model_cfg.get("model_context_window", 1_000_000)),
    }
    if "temperature" in model_cfg:
        config["temperature"] = float(model_cfg["temperature"])

    body = {"message": user_message, "config": config}
    headers = {
        "content-type": "application/json",
        "accept": "text/event-stream",
        "x-agent-session-id": session_id,
    }

    result = TurnResult(
        final_text="",
        final_answer="",
        sse_log=sse_log,
        trajectory_log=trajectory_log,
    )
    sse_fh = sse_log.open("w", encoding="utf-8") if sse_log else None
    traj_fh = trajectory_log.open("w", encoding="utf-8") if trajectory_log else None
    seq = 0
    started = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_s, read=timeout_s)) as client:
            with connect_sse(
                client,
                "POST",
                f"{base_url}/api/agent/chat/stream",
                json=body,
                headers=headers,
            ) as event_source:
                chunk_buf: list[str] = []
                for ev in event_source.iter_sse():
                    if not ev.data:
                        continue
                    if sse_fh:
                        sse_fh.write(ev.data + "\n")
                    try:
                        payload = json.loads(ev.data)
                    except json.JSONDecodeError:
                        continue
                    result.events += 1
                    et = payload.get("type")
                    if et == "llm_chunk":
                        c = payload.get("content")
                        if isinstance(c, str):
                            chunk_buf.append(c)
                    elif et == "step":
                        content = payload.get("content") or {}
                        if isinstance(content, dict) and content.get("role") == "step":
                            tcs = content.get("tool_calls") or []
                            if isinstance(tcs, list):
                                result.tool_calls += len(tcs)
                            tool_record = _summarize_tool_call(content)
                            if tool_record:
                                seq += 1
                                step = TrajectoryStep("tool_call", tool_record, seq)
                                result.trajectory.append(step)
                                if traj_fh:
                                    traj_fh.write(json.dumps(
                                        {"seq": seq, "kind": "tool_call", "content": tool_record},
                                        ensure_ascii=False,
                                    ) + "\n")
                        text = _assistant_text_from_step(content)
                        if text:
                            seq += 1
                            step = TrajectoryStep("assistant", text, seq)
                            result.trajectory.append(step)
                            if traj_fh:
                                traj_fh.write(json.dumps(
                                    {"seq": seq, "kind": "assistant", "content": _truncate(text, 16384)},
                                    ensure_ascii=False,
                                ) + "\n")
                            chunk_buf = []
                    elif et == "usage":
                        u = payload.get("content") or {}
                        result.input_tokens += int(u.get("input_tokens") or 0)
                        result.output_tokens += int(u.get("output_tokens") or 0)
                    elif et == "error":
                        result.error = str(payload.get("content") or "unknown error")
                        break
                    elif et == "done":
                        if chunk_buf:
                            text = "".join(chunk_buf)
                            seq += 1
                            step = TrajectoryStep("assistant", text, seq)
                            result.trajectory.append(step)
                            if traj_fh:
                                traj_fh.write(json.dumps(
                                    {"seq": seq, "kind": "assistant", "content": _truncate(text, 16384)},
                                    ensure_ascii=False,
                                ) + "\n")
                        break
    finally:
        result.elapsed_s = time.monotonic() - started
        if sse_fh:
            sse_fh.close()
        if traj_fh:
            traj_fh.close()

    final_text = ""
    for step in reversed(result.trajectory):
        if step.kind == "assistant" and isinstance(step.content, str) and step.content.strip():
            final_text = step.content.strip()
            break
    result.final_text = final_text
    result.final_answer = _extract_final_answer(final_text)
    return result
