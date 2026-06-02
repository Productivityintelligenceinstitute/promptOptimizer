"""Document reader tool."""

from __future__ import annotations

from typing import Any, Optional

import httpx
import trafilatura

from context_jobs.tools.base import BaseTool


class DocReaderTool(BaseTool):
    id = "doc-reader"
    name = "Document Reader"
    description = "Read and extract text content from a URL."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to read"},
            "max_chars": {"type": "integer", "default": 5000},
        },
        "required": ["url"],
    }

    async def execute(self, arguments: dict[str, Any], api_key: Optional[str] = None) -> str:
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ValueError("url is required")
        max_chars = int(arguments.get("max_chars") or 5000)
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        text = trafilatura.extract(response.text) or ""
        if not text:
            text = response.text[:max_chars]
        return text[:max_chars]
