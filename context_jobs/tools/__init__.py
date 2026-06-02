"""Tool implementation registry."""

from __future__ import annotations

from context_jobs.tools.api_caller import ApiCallerTool
from context_jobs.tools.base import BaseTool
from context_jobs.tools.calculator import CalculatorTool
from context_jobs.tools.code_executor import CodeExecutorTool
from context_jobs.tools.doc_reader import DocReaderTool
from context_jobs.tools.web_search import WebSearchTool

TOOL_IMPLEMENTATIONS: dict[str, BaseTool] = {
    "web-search": WebSearchTool(),
    "doc-reader": DocReaderTool(),
    "calculator": CalculatorTool(),
    "code-exec": CodeExecutorTool(),
    "api-caller": ApiCallerTool(),
}


def get_tool_implementation(tool_id: str) -> BaseTool:
    impl = TOOL_IMPLEMENTATIONS.get(tool_id)
    if not impl:
        raise ValueError(f"No implementation for tool: {tool_id}")
    return impl
