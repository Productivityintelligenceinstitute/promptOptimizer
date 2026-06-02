"""Build system prompt from Context Job fields."""

from __future__ import annotations

from schemas.context_jobs_model import ContextJobModel


def build_system_prompt(job: ContextJobModel) -> str:
    sections: list[str] = []

    if job.role_configuration:
        sections.append(f"## Your Role\n{job.role_configuration}")
    if job.goal:
        sections.append(f"## Objective\n{job.goal}")
    if job.stable_instructions:
        sections.append(f"## Instructions\n{job.stable_instructions}")
    if job.semantic_blueprint:
        sections.append(f"## Expected Output Format\n{job.semantic_blueprint}")

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
    return "\n\n".join(sections)


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
