import os
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs import schemas as cj_schemas
from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.managed_jet_kb import ensure_managed_namespace
from context_jobs.plan_entitlements import normalize_execution_for_plan
from context_jobs.providers.registry import PROVIDER_REGISTRY
from context_jobs.vector_connection_services import get_active_connection_for_owner
from schemas.context_jobs_model import ContextJobModel
from schemas.llm_provider_key_model import LlmProviderKeyModel


def _provider_fallback_models(provider: Optional[str]) -> list[str]:
    """Ordered fallback model ids for a provider (default model first)."""
    entry = PROVIDER_REGISTRY.get((provider or "").lower().strip())
    if not entry:
        return []
    default = entry.get("default_model")
    models = list(entry.get("models") or [])
    ordered = ([default] if default else []) + [m for m in models if m != default]
    return ordered


def validate_job_vector_connection(db: Session, data: cj_schemas.ContextJobBase, owner: str) -> None:
    mode = (getattr(data, "retrieval_mode", None) or "jet_kb").lower()
    conn_id = getattr(data, "vector_connection_id", None)
    if mode == "external":
        if not conn_id:
            raise ValueError(
                "retrievalMode external requires vectorConnectionId (pick a saved connection)."
            )
        get_active_connection_for_owner(db, conn_id, owner)
    elif conn_id:
        raise ValueError("vectorConnectionId is only used when retrievalMode is external.")


def validate_llm_key(
    db: Session,
    owner: str,
    llm_key_id: Optional[UUID],
    *,
    package_name: Optional[str] = None,
) -> None:
    if package_name == "trial":
        if llm_key_id is not None:
            raise ValueError("BYOK keys are not available during trial.")
        provider_env_keys = {
            "openai": os.environ.get("OPENAI_API_KEY"),
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "google": os.environ.get("GEMINI_API_KEY"),
        }
        if not any(provider_env_keys.values()):
            raise ValueError("Platform LLM keys are not configured. Contact support.")
        return

    if package_name == "pro":
        if not llm_key_id:
            raise ValueError(
                "Pro plan requires a BYOK LLM key for this provider. "
                "Add a key via POST /context-jobs/llm-keys or set llmKeyId on this job."
            )

    if not llm_key_id:
        provider_env_keys = {
            "openai": os.environ.get("OPENAI_API_KEY"),
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "google": os.environ.get("GEMINI_API_KEY"),
        }
        if any(provider_env_keys.values()):
            return
        raise ValueError("llmKeyId is required. Add a BYOK LLM key and assign it to this job.")
    row = (
        db.query(LlmProviderKeyModel)
        .filter(
            LlmProviderKeyModel.id == llm_key_id,
            LlmProviderKeyModel.owner == owner,
            LlmProviderKeyModel.status == "active",
        )
        .first()
    )
    if not row:
        raise ContextJobsNotFoundError("LLM key not found")


def validate_execution_model_for_key(
    db: Session,
    owner: str,
    llm_key_id: UUID,
    execution_model: Optional[str],
    *,
    allow_fallback: bool = False,
) -> str:
    """
    Resolve executionModel against the live BYOK key model list.

    When execution_model is omitted, use the first model returned by the provider.
    When allow_fallback is True (auto-generated previews such as prompt-to-job or
    template instantiate), an unavailable model is replaced by the first available
    provider fallback model, and if none of the fallbacks are available the model is
    left empty so the user can pick one — instead of raising.
    """
    from context_jobs.provider_key_services import list_models_for_llm_key

    result = list_models_for_llm_key(db, owner, llm_key_id)
    allowed_ids = [m["id"] for m in result["models"]]
    if not allowed_ids:
        if allow_fallback:
            return ""
        raise ValueError(
            f"No chat models available for BYOK key '{result['keyLabel']}'."
        )
    if execution_model and execution_model in allowed_ids:
        return execution_model

    if allow_fallback:
        for candidate in _provider_fallback_models(result.get("provider")):
            if candidate in allowed_ids:
                return candidate
        return ""

    if execution_model:
        raise ValueError(
            f"Model '{execution_model}' is not available for BYOK key "
            f"'{result['keyLabel']}'. Choose a model from "
            f"GET /context-jobs/llm-keys/{llm_key_id}/models."
        )
    return allowed_ids[0]


def validate_job_execution_for_plan(
    db: Session,
    owner: str,
    package_name: str,
    execution_provider: Optional[str],
    execution_model: Optional[str],
    llm_key_id: Optional[UUID],
    *,
    allow_model_fallback: bool = False,
) -> tuple[str, str, Optional[UUID]]:
    from context_jobs.provider_key_services import resolve_llm_key_id_for_provider

    provider = (execution_provider or "openai").lower().strip()
    key_id = llm_key_id
    if package_name == "pro":
        key_id = resolve_llm_key_id_for_provider(db, owner, provider, llm_key_id)
    provider, model, key_id = normalize_execution_for_plan(
        package_name,
        execution_provider,
        execution_model,
        key_id,
    )
    validate_llm_key(db, owner, key_id, package_name=package_name)
    if package_name == "pro" and key_id:
        model = validate_execution_model_for_key(
            db, owner, key_id, execution_model or model, allow_fallback=allow_model_fallback
        )
    return provider, model, key_id


def maybe_ensure_jet_managed_namespace(db: Session, job: ContextJobModel) -> None:
    if (job.retrieval_mode or "jet_kb").lower() != "jet_kb":
        return
    ensure_managed_namespace(db, job.owner)
