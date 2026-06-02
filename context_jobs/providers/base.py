"""Provider adapter types and base interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class ToolDefinition:
    id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    is_read_only: bool = True


@dataclass
class ExecutionEnvelope:
    system_prompt: str
    user_message: str
    tools: list[ToolDefinition]
    max_tokens: int
    max_turns: int
    temperature: float
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    id: str
    tool_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class ProviderResponse:
    content: Optional[str]
    input_tokens: int
    output_tokens: int
    model: str
    stop_reason: str
    agent_turns: int = 0


ToolExecutor = Callable[[ToolCall], Awaitable[ToolResult]]


class ProviderAdapter(ABC):
    @abstractmethod
    async def execute(
        self,
        envelope: ExecutionEnvelope,
        api_key: str,
        tool_executor: ToolExecutor,
    ) -> ProviderResponse:
        ...

    @abstractmethod
    def translate_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        ...
