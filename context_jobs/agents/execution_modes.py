"""Execution mode constants and validation."""

from __future__ import annotations

EXECUTION_MODE_SINGLE = "single_agent"
EXECUTION_MODE_MULTI = "provider_multi_agent"

VALID_EXECUTION_MODES = {EXECUTION_MODE_SINGLE, EXECUTION_MODE_MULTI}


def normalize_execution_mode(mode: str | None) -> str:
    value = (mode or EXECUTION_MODE_SINGLE).strip().lower()
    if value not in VALID_EXECUTION_MODES:
        allowed = ", ".join(sorted(VALID_EXECUTION_MODES))
        raise ValueError(f"executionMode must be one of: {allowed}")
    return value
