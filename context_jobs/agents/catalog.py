"""Compile bounded specialist agents from a Context Job definition."""

from __future__ import annotations

from context_jobs.agents.execution_modes import EXECUTION_MODE_MULTI, normalize_execution_mode
from context_jobs.agents.types import SubAgentDefinition
from schemas.context_jobs_model import ContextJobModel

DELEGATE_TOOL_ID = "delegate-to-agent"

SPECIALIST_BLUEPRINTS: dict[str, dict] = {
    "researcher": {
        "description": (
            "Use for deep multi-source investigation that benefits from an isolated research context: "
            "several web searches, document reads, evidence synthesis, or conflicting sources."
        ),
        "tool_ids": ("web-search", "doc-reader"),
        "prompt": (
            "You are a research specialist. Gather evidence, cite sources, and return a concise "
            "structured summary for the orchestrator. Do not produce the final deliverable unless asked."
        ),
    },
    "analyst": {
        "description": (
            "Use for calculation-heavy, data transformation, or Python analysis tasks that need "
            "focused iterative code execution."
        ),
        "tool_ids": ("calculator", "code-exec"),
        "prompt": (
            "You are an analysis specialist. Use calculator and Python execution as needed. "
            "Return clear results, assumptions, and any code outputs relevant to the task."
        ),
    },
    "producer": {
        "description": (
            "Use when drafting long-form deliverables or file artifacts (markdown, text, code files, DOCX) "
            "that benefit from a dedicated writing context."
        ),
        "tool_ids": ("file-write", "docx-generate", "doc-reader"),
        "prompt": (
            "You are a production specialist. Create polished deliverables and file artifacts using "
            "the correct file extensions. Follow the job's semantic blueprint and instructions."
        ),
    },
    "integrator": {
        "description": (
            "Use when the task requires calling approved external HTTP APIs to fetch or submit data."
        ),
        "tool_ids": ("api-caller",),
        "prompt": (
            "You are an integration specialist. Call approved external APIs only. "
            "Return structured results and note any errors clearly."
        ),
    },
    "validator": {
        "description": (
            "Use for read-only verification: fact-checking, policy review, or quality checks "
            "against sources without modifying artifacts."
        ),
        "tool_ids": ("doc-reader", "web-search"),
        "prompt": (
            "You are a validation specialist. Review content read-only, identify issues, "
            "and return a concise pass/fail style assessment with evidence."
        ),
    },
}


def is_multi_agent_mode(job: ContextJobModel) -> bool:
    mode = normalize_execution_mode(getattr(job, "execution_mode", None))
    return mode == EXECUTION_MODE_MULTI


def _enabled_tool_ids(job: ContextJobModel) -> set[str]:
    enabled: set[str] = set()
    for perm in job.tool_permissions or []:
        if not isinstance(perm, dict):
            continue
        if not perm.get("enabled"):
            continue
        tool_id = perm.get("toolId") or perm.get("tool_id")
        if tool_id:
            enabled.add(str(tool_id))
    return enabled


def compile_agent_catalog(job: ContextJobModel) -> dict[str, SubAgentDefinition]:
    if not is_multi_agent_mode(job):
        return {}

    enabled = _enabled_tool_ids(job)
    catalog: dict[str, SubAgentDefinition] = {}

    for name, blueprint in SPECIALIST_BLUEPRINTS.items():
        specialist_tools = tuple(tid for tid in blueprint["tool_ids"] if tid in enabled)
        if not specialist_tools:
            continue
        catalog[name] = SubAgentDefinition(
            name=name,
            description=blueprint["description"],
            system_prompt=_build_specialist_prompt(job, blueprint["prompt"]),
            tool_ids=specialist_tools,
            max_turns=min(int(job.max_agent_turns or 10), 8),
        )
    return catalog


def _build_specialist_prompt(job: ContextJobModel, role_prompt: str) -> str:
    parts = [role_prompt]
    if job.goal:
        parts.append(f"Job objective:\n{job.goal}")
    if job.semantic_blueprint:
        parts.append(f"Expected output format:\n{job.semantic_blueprint}")
    if job.stable_instructions:
        parts.append(f"Stable instructions:\n{job.stable_instructions}")
    return "\n\n".join(parts)


def build_delegate_tool_schema(catalog: dict[str, SubAgentDefinition]) -> dict:
    names = sorted(catalog.keys())
    return {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "enum": names,
                "description": "Specialist agent to delegate to",
            },
            "task": {
                "type": "string",
                "description": "Focused task for the specialist; include only what it needs",
            },
        },
        "required": ["agent_name", "task"],
    }


def list_specialist_catalog(job: ContextJobModel) -> list[dict]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "toolIds": list(spec.tool_ids),
            "maxTurns": spec.max_turns,
        }
        for spec in compile_agent_catalog(job).values()
    ]


def build_delegate_tool_definition(catalog: dict[str, SubAgentDefinition]):
    from context_jobs.providers.base import ToolDefinition

    if not catalog:
        return None
    descriptions = "; ".join(f"{name}: {spec.description}" for name, spec in catalog.items())
    return ToolDefinition(
        id=DELEGATE_TOOL_ID,
        name="Delegate to Agent",
        description=(
            "Delegate a focused subtask to a specialist agent with its own context. "
            "Use when isolated specialist work would help; use direct tools when a single call is enough. "
            f"Available specialists — {descriptions}"
        ),
        input_schema=build_delegate_tool_schema(catalog),
        is_read_only=False,
    )
