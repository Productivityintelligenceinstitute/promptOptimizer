"""Budget tracking during run execution."""

from __future__ import annotations

import time


class BudgetTracker:
    def __init__(self, budget_settings: dict | None):
        budget_settings = budget_settings or {}
        self.per_request_max_tokens = int(budget_settings.get("maxTokens") or 4096)
        self.max_tokens = int(
            budget_settings.get("maxTotalTokens")
            or budget_settings.get("maxRunTokens")
            or 32000
        )
        self.max_latency_ms = int(budget_settings.get("maxLatencyMs") or 300000)
        self.max_cost_usd = float(budget_settings.get("maxCostUsd") or 0.50)
        self.max_tool_calls = int(budget_settings.get("maxToolCalls") or 20)

        self.tokens_used = 0
        self.cost_usd = 0.0
        self.tool_calls = 0
        self.start_time = time.time()
        self._paused_at: float | None = None
        self._paused_total_sec = 0.0

    def pause(self) -> None:
        """Exclude wall time (e.g. human approval waits) from latency budget."""
        if self._paused_at is None:
            self._paused_at = time.time()

    def resume(self) -> None:
        if self._paused_at is not None:
            self._paused_total_sec += time.time() - self._paused_at
            self._paused_at = None

    def _elapsed_ms(self) -> float:
        now = time.time()
        paused = self._paused_total_sec
        if self._paused_at is not None:
            paused += now - self._paused_at
        return (now - self.start_time - paused) * 1000

    def is_exceeded(self) -> bool:
        if self.tool_calls >= self.max_tool_calls:
            return True
        if self.tokens_used >= self.max_tokens:
            return True
        if self.cost_usd >= self.max_cost_usd:
            return True
        return self._elapsed_ms() >= self.max_latency_ms

    def reason(self) -> str:
        if self.tool_calls >= self.max_tool_calls:
            return "max tool calls exceeded"
        if self.tokens_used >= self.max_tokens:
            return "max tokens exceeded"
        if self.cost_usd >= self.max_cost_usd:
            return "max cost exceeded"
        return "max latency exceeded"

    def record_tool_call(self) -> None:
        self.tool_calls += 1

    def record_tokens(self, input_tokens: int, output_tokens: int, model: str) -> None:
        self.tokens_used += (input_tokens or 0) + (output_tokens or 0)
        self.cost_usd += estimate_cost(input_tokens or 0, output_tokens or 0, model)


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    model = (model or "").lower()
    if "claude" in model:
        return (input_tokens * 0.000003) + (output_tokens * 0.000015)
    if "gemini" in model:
        return (input_tokens * 0.000001) + (output_tokens * 0.000004)
    return (input_tokens * 0.000002) + (output_tokens * 0.000008)
