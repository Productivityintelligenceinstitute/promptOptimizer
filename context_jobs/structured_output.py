"""Parse structured output from run text."""

from __future__ import annotations

import json
import re
from typing import Any, Optional


def extract_structured_output(text: str, output_template: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Try to extract JSON structured output from model text."""
    if not text:
        return None
    stripped = text.strip()

    # Fenced JSON block
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
    if fence:
        try:
            parsed = json.loads(fence.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Whole body is JSON
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, (dict, list)):
                return parsed if isinstance(parsed, dict) else {"items": parsed}
        except json.JSONDecodeError:
            pass

    # Template-driven key extraction (## Section headers)
    if output_template and "##" in output_template:
        sections = {}
        template_sections = re.findall(r"##\s*([^\n]+)", output_template)
        for section in template_sections:
            pattern = rf"##\s*{re.escape(section.strip())}\s*\n([\s\S]*?)(?=##|\Z)"
            match = re.search(pattern, stripped, re.IGNORECASE)
            if match:
                sections[section.strip()] = match.group(1).strip()
        if sections:
            return sections

    return None
