"""Shared types for CLM provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from context_jobs.clm.url_parser import ClmReference


@dataclass
class ClmDocument:
    """Downloaded contract file from a CLM system."""

    content: bytes
    filename: str
    content_type: Optional[str] = None
    provider: str = ""
    resource_type: str = ""
    resource_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ClmAdapter(Protocol):
    provider: str

    def test_connection(self, config: dict[str, Any]) -> tuple[bool, str]:
        """Validate credentials against the provider API."""

    def fetch_document(
        self,
        config: dict[str, Any],
        reference: ClmReference,
    ) -> ClmDocument:
        """Download the legal agreement / signed copy for the reference."""
