"""Helpers to read structured tool output from run tool executions and events."""

from __future__ import annotations

import json
import re
from typing import Any

_UNTRUSTED_TOOL_RESULT_RE = re.compile(
    r"<untrusted_tool_result>\s*(.*?)\s*</untrusted_tool_result>",
    re.DOTALL | re.IGNORECASE,
)

_TOOL_MATCHERS: dict[str, tuple[str, ...]] = {
    "contract-analyzer": ("contract-analyzer", "contract analyzer"),
    "spend-analyzer": ("spend-analyzer", "spend analyzer"),
}


def _unwrap_tool_result(text: str) -> str:
    body = (text or "").strip()
    match = _UNTRUSTED_TOOL_RESULT_RE.search(body)
    if match:
        return match.group(1).strip()
    return body


def _matches_tool_id(candidate: str, tool_id: str) -> bool:
    normalized = (candidate or "").strip().lower()
    aliases = _TOOL_MATCHERS.get(tool_id, (tool_id,))
    return any(alias in normalized or normalized in alias for alias in aliases)


def _row_matches_tool(row: dict[str, Any], tool_id: str) -> bool:
    for key in ("toolId", "tool_id", "toolName", "tool_name"):
        value = row.get(key)
        if value and _matches_tool_id(str(value), tool_id):
            return True
    return False


def _parse_json_payload(text: str) -> dict[str, Any] | None:
    body = _unwrap_tool_result(text)
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if parsed.get("error"):
        return None
    return parsed


def merge_tool_execution_sources(
    db_executions: list[dict[str, Any]] | None,
    memory_executions: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Combine DB audit rows with in-memory gateway outputs.

    Memory rows are appended last so find_tool_output (reverse scan) prefers
    full JSON from the live executor over truncated or missing DB rows.
    """
    return list(db_executions or []) + list(memory_executions or [])


def find_tool_output(
    tool_id: str,
    *,
    tool_executions: list[dict[str, Any]] | None = None,
    tool_events: list[dict[str, Any]] | None = None,
    memory_executions: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return the latest successful parsed JSON payload for a tool id."""
    rows = merge_tool_execution_sources(tool_executions, memory_executions)
    for row in reversed(rows):
        if not _row_matches_tool(row, tool_id):
            continue
        if (row.get("status") or "").lower() not in {"success", "completed"}:
            continue
        for key in ("resultSummary", "result_summary", "result", "content", "output"):
            payload = row.get(key)
            if not payload:
                continue
            parsed = _parse_json_payload(str(payload))
            if parsed is not None:
                return parsed

    for row in reversed(tool_events or []):
        if not _row_matches_tool(row, tool_id):
            continue
        if (row.get("status") or "").lower() not in {"success", "completed"}:
            continue
        for key in ("resultSummary", "result_summary", "result", "content", "output"):
            payload = row.get(key)
            if not payload:
                continue
            parsed = _parse_json_payload(str(payload))
            if parsed is not None:
                return parsed
    return None
