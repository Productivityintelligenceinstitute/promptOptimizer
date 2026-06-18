"""Build system prompt from Context Job fields."""

from __future__ import annotations

from context_jobs.agents.catalog import is_multi_agent_mode
from schemas.context_jobs_model import ContextJobModel


def build_system_prompt(job: ContextJobModel, user_request: str = "") -> str:
    sections: list[str] = []

    if job.role_configuration:
        sections.append(f"## Your Role\n{job.role_configuration}")
    if job.goal:
        sections.append(f"## Objective\n{job.goal}")
    if job.stable_instructions:
        sections.append(f"## Instructions\n{job.stable_instructions}")
    output_template = (job.output_template or "").strip()
    if output_template:
        template = output_template.replace("{topic}", user_request[:100])
        sections.append(
            "## Required Output Format\n"
            "You MUST return your response strictly in this format. "
            "Fill in the values, keep the structure exactly as shown:\n\n"
            f"{template}"
        )
    elif job.semantic_blueprint:
        blueprint = job.semantic_blueprint.replace("{topic}", user_request[:100])
        sections.append(f"## Expected Output Format\n{blueprint}")

    if job.glossary_terms:
        lines = []
        for term in job.glossary_terms:
            if not isinstance(term, dict):
                continue
            line = f"- **{term.get('term', '')}**: {term.get('definition', '')}"
            synonyms = term.get("synonyms") or []
            if synonyms:
                line += f" (synonyms: {', '.join(synonyms)})"
            if term.get("required"):
                line += " [REQUIRED]"
            lines.append(line)
        if lines:
            sections.append("## Domain Glossary\n" + "\n".join(lines))

    if job.relationships:
        rel_lines = [
            f"- {r.get('fromTerm', '')} {r.get('relation', '')} {r.get('toTerm', '')}"
            for r in job.relationships
            if isinstance(r, dict)
        ]
        if rel_lines:
            sections.append("## Entity Relationships\n" + "\n".join(rel_lines))

    if job.escalation_policy:
        sections.append(f"## Escalation Policy\n{job.escalation_policy}")

    budget = job.budget_settings or {}
    if isinstance(budget, dict):
        sections.append(
            "## Constraints\n"
            f"- Max output tokens: {budget.get('maxTokens', 4096)}\n"
            f"- Target latency: {budget.get('maxLatencyMs', 30000)}ms\n"
            f"- Cost limit: ${budget.get('maxCostUsd', 0.50)}"
        )

    sections.append(
        "Citation format: when citing retrieved context, use [source:{name}] where possible."
    )
    if is_multi_agent_mode(job):
        sections.append(_multi_agent_orchestration_guidance())
    return "\n\n".join(sections)


def _multi_agent_orchestration_guidance() -> str:
    return (
        "## Execution Options\n"
        "You have direct tools and optional specialist agents via delegate-to-agent.\n"
        "Choose the simplest approach that fits the task:\n"
        "- Use direct tool calls when a single or few tool invocations are sufficient.\n"
        "- Delegate to a specialist only when isolated context, parallel depth, or role focus "
        "would materially improve the result.\n"
        "There is no requirement to delegate; efficiency and correctness come first."
    )


def assemble_user_message(user_request: str, rag_context: str, memory_context: str) -> str:
    parts = [f"User Request:\n{user_request.strip()}"]
    if memory_context.strip():
        parts.append(memory_context.strip())
    if rag_context.strip():
        parts.append(f"Retrieved Context:\n{rag_context.strip()}")
    parts.append(
        "Use retrieved context and memory when relevant. "
        "If evidence is insufficient, say so explicitly."
    )
    return "\n\n".join(parts)
