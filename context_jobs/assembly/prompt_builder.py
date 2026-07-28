"""Build system prompt from Context Job fields."""

from __future__ import annotations

from context_jobs.agents.catalog import is_multi_agent_mode
from context_jobs.assembly.output_format import build_output_format_prompt, clean_model_output
from context_jobs.assembly.prompt_safety import (
    append_prompt_injection_policy,
    sanitize_topic_snippet,
    wrap_untrusted_content,
)
from schemas.context_jobs_model import ContextJobModel


def _enabled_tool_ids(job: ContextJobModel) -> set[str]:
    enabled: set[str] = set()
    for perm in job.tool_permissions or []:
        if not isinstance(perm, dict) or not perm.get("enabled"):
            continue
        tool_id = perm.get("toolId") or perm.get("tool_id")
        if tool_id:
            enabled.add(str(tool_id))
    return enabled


def _workflow_tool_guidance(job: ContextJobModel) -> str | None:
    tools = _enabled_tool_ids(job)
    workflow = (job.workflow_type or "standard").lower()

    if workflow == "contract_review" and "contract-analyzer" in tools:
        return (
            "## Contract Analysis Tools\n"
            "You MUST call contract-analyzer before writing the final review — do not skip it "
            "even when Retrieved Context already looks complete. Validation requires its "
            "structured output.\n"
            "When calling contract-analyzer with source=text, pass the COMPLETE contract text "
            "from every Retrieved Context block — do not omit sections such as RENEWAL NOTICE. "
            "The gateway will merge full retrieved context automatically, but include all sections "
            "when pasting inline.\n"
            "For contract URLs use source=url. Base your clause assessment on the tool's "
            "structured output plus retrieved evidence.\n"
            "Use vector database retrieved contract text as the source of truth. If a requested "
            "contract fact, clause, price, date, or notice period is not present in Retrieved "
            "Context, write 'Not available in retrieved vector context' instead of guessing or "
            "substituting web/doc-reader content.\n"
            "Decision discipline (Full and Executive packs): state an explicit renew / "
            "renegotiate / exit recommendation early (Executive Summary or Decision section). "
            "Calendar reminders alone are not a decision."
        )

    if workflow == "supplier_assessment":
        return (
            "## Supplier Capability Grounding\n"
            "Use Retrieved Context (vendor profiles / RFP materials) and the User request as the "
            "source of truth for every material claim in the matrix.\n"
            "Web search is not available for this workflow — do not rely on public web pages to "
            "fill capability cells.\n"
            "Do NOT invent uptime percentages, SLA breach history, data breaches, certifications, "
            "pricing models, or risk incidents that are not present in retrieved evidence.\n"
            "If a comparison cell cannot be filled from evidence, write "
            "'Not available in retrieved vector context' and list it under Evidence Gaps.\n"
            "Citations must support the exact claim — do not cite a profile and then add "
            "unsupported details. Prefer documented risk tiers and category tags from profiles "
            "over narrative guesses.\n"
            "Evidence Gaps discipline: do NOT list a gap for any field that already appears in "
            "Retrieved Context body text OR [meta:...] lines (riskTier / spendTier, "
            "capability/category tags, named certifications, MSA/contract status, annual spend "
            "figures, renewal complexity, residency or compliance packaging). Gaps are only for "
            "truly absent facts (for example missing rate card/SOW, missing SLA metrics, or "
            "certifications when none are stated).\n"
            "If a profile states certifications are available, that is evidence — do not list "
            "those certifications as an evidence gap for that supplier.\n"
            "When [meta:riskTier=...] or 'Risk tier:' appears for a supplier, use that value in "
            "the matrix / risk posture cells — never write N/A or list risk tier as an evidence gap.\n"
            "riskPosture scoring: quality score where HIGHER is better (safer). When tiers are "
            "present, low must outscore medium, and medium must outscore high "
            "(example map: low→4-5, medium→2-3, high→1). Never treat riskPosture as severity.\n"
            "Ranking and technical scores must weigh fit to the requested category/use case in "
            "the User request; incumbent spend or a linked MSA alone does not justify ranking a "
            "weaker category fit above a stronger one.\n"
            "Me-too flags must not erase documented differentiators present in Retrieved Context."
        )

    if workflow == "procurement":
        return (
            "## Supplier Onboarding Grounding\n"
            "Use Retrieved Context supplier packets / vendor profiles and the User request as "
            "the source of truth for capability, risk tier, and commercial posture.\n"
            "Prefer supplier-packet / vendor_profile evidence over unrelated contract chunks when "
            "both appear in retrieval.\n"
            "Cite material capability, commercial, and risk claims with [source:…] from retrieved "
            "supplier evidence — at least several citations are required for Full packs.\n"
            "Preserve documented risk tiers from profiles / [meta:riskTier=...]. If a fact is "
            "missing, write 'Not available in retrieved vector context' instead of inventing "
            "certifications, rate cards, or SLA metrics.\n"
            "Include named approval owners from the User request in the checklist when provided."
        )

    if workflow == "analysis" and "spend-analyzer" in tools:
        staging_ban = (
            "Do NOT use doc-reader or file-write before spend-analyzer — ingested KB content "
            "is already in Retrieved Context.\n"
            if "doc-reader" not in tools and "file-write" not in tools
            else "Do NOT use file-write to stage data before spend-analyzer; pass CSV directly.\n"
        )
        code_exec_ban = (
            "Do NOT use code-exec for normalization.\n"
            if "code-exec" not in tools
            else "Do NOT call code-exec for normalization when spend-analyzer can handle the data.\n"
        )
        context_hint = (
            "Use rate card data from EVERY Retrieved Context block (all vendors, all roles). "
            if "doc-reader" not in tools
            else ""
        )
        return (
            "## Spend Analysis Tools\n"
            f"{context_hint}"
            "Build a CSV with columns vendor, title, level, rate — every row must include a numeric rate.\n"
            "Call spend-analyzer EXACTLY ONCE with the full consolidated CSV. "
            "Do NOT call spend-analyzer more than once or separately per vendor.\n"
            f"{staging_ban}"
            f"{code_exec_ban}"
            "Each taxonomy entry must include role, level, and explicit title strings (titles field), e.g. "
            '{"role":"Engineering","level":"Senior","titles":["Senior Cloud Engineer"]}. '
            "Copy the tool's full normalizedRows, unmappedTitles, varianceFlags, and spendConcentration "
            "into your final output without dropping rows.\n"
            "After spend-analyzer returns, write the final answer immediately without additional tool calls."
        )

    return None


def build_system_prompt(job: ContextJobModel, user_request: str = "") -> str:
    sections: list[str] = []

    if job.role_configuration:
        sections.append(f"## Your Role\n{job.role_configuration}")
    if job.goal:
        sections.append(f"## Objective\n{job.goal}")
    if job.stable_instructions:
        sections.append(f"## Instructions\n{job.stable_instructions}")
    format_section = build_output_format_prompt(job, user_request)
    if format_section:
        sections.append(format_section)
    elif job.semantic_blueprint:
        topic = sanitize_topic_snippet(user_request)
        blueprint = job.semantic_blueprint.replace("{topic}", topic)
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
            f"- Max output tokens per request: {budget.get('maxTokens', 4096)}\n"
            f"- Target latency: {budget.get('maxLatencyMs', 300000)}ms\n"
            f"- Cost limit: ${budget.get('maxCostUsd', 0.50)}\n"
            f"- Max tool calls: {budget.get('maxToolCalls', 20)}"
        )

    sections.append(
        "Citation format: when citing retrieved context, use [source:{name}] where possible."
    )
    workflow_guidance = _workflow_tool_guidance(job)
    if workflow_guidance:
        sections.append(workflow_guidance)
    if is_multi_agent_mode(job):
        sections.append(_multi_agent_orchestration_guidance())
    return append_prompt_injection_policy("\n\n".join(sections))


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


def assemble_user_message(
    user_request: str,
    rag_context: str,
    memory_context: str,
    *,
    trusted_suffix: str | None = None,
) -> str:
    parts: list[str] = []
    wrapped_user = wrap_untrusted_content("untrusted_user_request", user_request)
    if wrapped_user:
        parts.append(wrapped_user)
    if memory_context.strip():
        parts.append(wrap_untrusted_content("untrusted_memory", memory_context))
    if rag_context.strip():
        parts.append(wrap_untrusted_content("untrusted_retrieved_context", rag_context))
    parts.append(
        "Analyze the untrusted blocks above. Use retrieved context and memory when relevant. "
        "If evidence is insufficient or a requested fact is not present in retrieved vector "
        "context, say it is not available in retrieved vector context; do not infer or invent it."
    )
    if trusted_suffix:
        parts.append(trusted_suffix.strip())
    return "\n\n".join(parts)
