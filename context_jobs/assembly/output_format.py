"""Output template helpers — prompt formatting and echoed-instruction cleanup."""

from __future__ import annotations

import re

from context_jobs.assembly.prompt_safety import sanitize_topic_snippet
from schemas.context_jobs_model import ContextJobModel

EXECUTIVE_BRIEF_MAX_WORDS = 400

# Legacy and common LLM echoes of format instructions (stripped from final output).
_ECHOED_PREAMBLE_PATTERNS = (
    re.compile(
        r"^Produce a concise executive brief \(400 words or fewer\) "
        r"with exactly these sections:\s*\n+",
        re.IGNORECASE,
    ),
    re.compile(
        r"^You MUST return your response strictly in this format\.[^\n]*\n+",
        re.IGNORECASE,
    ),
    re.compile(r"^Required Output Format\s*\n+", re.IGNORECASE),
)

_JSON_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n(.*?)```\s*$", re.DOTALL | re.IGNORECASE)


def is_executive_persona(job: ContextJobModel) -> bool:
    name = (job.name or "").lower()
    if "(executive)" in name:
        return True
    template = (job.output_template or job.semantic_blueprint or "").strip().lower()
    return "executive brief" in template or "400 words" in template


def is_scorecard_persona(job: ContextJobModel) -> bool:
    name = (job.name or "").lower()
    if "(scorecard)" in name:
        return True
    template = (job.output_template or job.semantic_blueprint or "").strip()
    return template.startswith("{") or template.startswith("[")


def executive_structure_skeleton(template: str) -> str:
    """Normalize stored template to markdown section headings only."""
    text = (template or "").strip()
    if not text:
        return text

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("produce a concise executive"):
            continue
        if line.startswith("##"):
            lines.append(line if line.endswith(":") else f"{line}:")
            continue
        if line.endswith(":") and not line.startswith("#"):
            heading = line[:-1].strip()
            lines.append(f"## {heading}:")
            continue
    return "\n".join(lines) if lines else text


def build_output_format_prompt(job: ContextJobModel, user_request: str = "") -> str | None:
    template = (job.output_template or "").strip()
    if not template:
        return None

    skeleton = template.replace("{topic}", sanitize_topic_snippet(user_request))
    no_echo = (
        "Do NOT repeat these format instructions, constraints, or the phrase "
        "'sections' in your response. Start directly with the required content "
        "(first section heading for markdown, or `{` for JSON)."
    )

    if is_executive_persona(job):
        structure = executive_structure_skeleton(skeleton)
        return (
            "## Required Output Format\n"
            f"Write a concise executive brief ({EXECUTIVE_BRIEF_MAX_WORDS} words or fewer).\n"
            f"Use exactly these markdown section headings. {no_echo}\n\n"
            f"{structure}"
        )

    if is_scorecard_persona(job):
        return (
            "## Required Output Format\n"
            "Return valid JSON matching this schema (values filled in, structure unchanged).\n"
            f"{no_echo}\n\n"
            f"{skeleton}"
        )

    return (
        "## Required Output Format\n"
        "Fill in the values below; keep the structure exactly as shown.\n"
        f"{no_echo}\n\n"
        f"{skeleton}"
    )


def strip_echoed_format_instructions(output_text: str) -> str:
    """Remove common LLM echoes of output-format instructions."""
    text = (output_text or "").strip()
    if not text:
        return text

    changed = True
    while changed:
        changed = False
        for pattern in _ECHOED_PREAMBLE_PATTERNS:
            updated = pattern.sub("", text).lstrip()
            if updated != text:
                text = updated
                changed = True

    fence_match = _JSON_FENCE_PATTERN.match(text)
    if fence_match and is_likely_json_template_output(text):
        text = fence_match.group(1).strip()

    return text


def is_likely_json_template_output(text: str) -> bool:
    stripped = (text or "").strip()
    return stripped.startswith("```") or stripped.startswith("{") or stripped.startswith("[")


def clean_model_output(output_text: str, job: ContextJobModel) -> str:
    """Normalize provider output before validation and persistence."""
    return strip_echoed_format_instructions(output_text)
