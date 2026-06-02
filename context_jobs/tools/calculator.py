"""Safe calculator tool."""

from __future__ import annotations

import math
from typing import Any, Optional

from simpleeval import simple_eval

from context_jobs.tools.base import BaseTool


class CalculatorTool(BaseTool):
    id = "calculator"
    name = "Calculator"
    description = "Evaluate mathematical expressions safely."
    input_schema = {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Math expression"},
        },
        "required": ["expression"],
    }

    async def execute(self, arguments: dict[str, Any], api_key: Optional[str] = None) -> str:
        expr = str(arguments.get("expression", "")).strip()
        if not expr:
            raise ValueError("expression is required")
        result = simple_eval(
            expr,
            functions={
                "sqrt": math.sqrt,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "log": math.log,
                "log10": math.log10,
                "abs": abs,
                "round": round,
                "pow": pow,
            },
            names={"pi": math.pi, "e": math.e},
        )
        return str(result)
