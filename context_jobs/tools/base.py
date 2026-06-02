"""Base tool interface for Context Jobs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseTool(ABC):
    id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    requires_external_key: bool = False

    @abstractmethod
    async def execute(self, arguments: dict[str, Any], api_key: Optional[str] = None) -> str:
        ...
