"""HTTP API caller tool with SSRF protections."""

from __future__ import annotations

import urllib.parse
from typing import Any, Optional

import httpx

from context_jobs.tools.base import BaseTool


class ApiCallerTool(BaseTool):
    id = "api-caller"
    name = "API Caller"
    description = "Make HTTP requests to external APIs."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "API endpoint URL"},
            "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
            "headers": {"type": "object", "description": "Request headers"},
            "body": {"type": "object", "description": "Request body for POST"},
            "timeout_seconds": {"type": "integer", "default": 10},
        },
        "required": ["url"],
    }

    async def execute(self, arguments: dict[str, Any], api_key: Optional[str] = None) -> str:
        url = str(arguments.get("url", "")).strip()
        if not url:
            raise ValueError("url is required")
        parsed = urllib.parse.urlparse(url)
        if parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
            raise ValueError("localhost requests are not allowed")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("only http/https URLs are allowed")

        method = str(arguments.get("method") or "GET").upper()
        headers = arguments.get("headers") or {}
        body = arguments.get("body")
        timeout = min(int(arguments.get("timeout_seconds") or 10), 30)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method == "POST":
                response = await client.post(url, headers=headers, json=body)
            else:
                response = await client.get(url, headers=headers)
        return f"Status: {response.status_code}\n\n{response.text[:3000]}"
