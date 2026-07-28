JOB_VERSION_SNAPSHOT_FIELDS = (    "name",
    "description",
    "status",
    "goal",
    "semantic_blueprint",
    "output_template",
    "workflow_type",
    "stable_instructions",
    "role_configuration",
    "retrieval_config",
    "retrieval_mode",
    "vector_connection_id",
    "memory_config",
    "tool_permissions",
    "validation_rules",
    "escalation_policy",
    "budget_settings",
    "glossary_terms",
    "relationships",
    "trusted_sources",
    "chain_config",
    "linked_child_job_id",
    "linked_asset_ids",
    "version",
    "owner",
    "approval_required",
    "policy_profile",
    "execution_provider",
    "execution_model",
    "llm_key_id",
    "max_agent_turns",
    "execution_mode",
    "workspace_id",
)

VALID_WORKFLOW_TYPES = frozenset({
    "standard",
    "research",
    "analysis",
    "generation",
    "decision",
    "extraction",
    "review",
    "monitoring",
    "procurement",
    "contract_review",
    "supplier_assessment",
})


def normalize_workflow_type(value: str | None, *, default_on_invalid: str | None = None) -> str:
    normalized = str(value or "standard").strip().lower()
    if normalized in VALID_WORKFLOW_TYPES:
        return normalized
    if default_on_invalid is not None:
        return default_on_invalid
    raise ValueError(
        f"Invalid workflowType '{value}'. "
        f"Must be one of: {', '.join(sorted(VALID_WORKFLOW_TYPES))}"
    )