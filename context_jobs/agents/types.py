"""Multi-agent type definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubAgentDefinition:
    name: str
    description: str
    system_prompt: str
    tool_ids: tuple[str, ...] = field(default_factory=tuple)
    max_turns: int = 6
