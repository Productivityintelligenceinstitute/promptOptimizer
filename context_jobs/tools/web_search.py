"""Web search tool using Tavily (BYOK)."""

from __future__ import annotations

from typing import Any, Optional

from context_jobs.tools.base import BaseTool


class WebSearchTool(BaseTool):
    id = "web-search"
    name = "Web Search"
    description = "Search the web for current information on a topic."
    requires_external_key = True
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "default": 5, "maximum": 10},
        },
        "required": ["query"],
    }

    async def execute(self, arguments: dict[str, Any], api_key: Optional[str] = None) -> str:
        if not api_key:
            raise ValueError("web-search requires a Tavily BYOK key")
        from tavily import TavilyClient

        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        num = int(arguments.get("num_results") or 5)
        num = max(1, min(10, num))
        client = TavilyClient(api_key=api_key)
        results = client.search(query, max_results=num)
        chunks = []
        for item in results.get("results", []):
            chunks.append(
                f"**{item.get('title', 'Result')}**\n"
                f"URL: {item.get('url', '')}\n"
                f"{(item.get('content') or '')[:500]}"
            )
        return "\n\n---\n\n".join(chunks) if chunks else "No results found."
