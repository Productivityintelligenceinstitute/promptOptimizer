"""Services for LLM and tool provider BYOK key management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from context_jobs.errors import ContextJobsNotFoundError
from context_jobs.provider_key_schemas import LlmKeyCreate, ToolKeyCreate
from context_jobs.providers.registry import PROVIDER_REGISTRY
from context_jobs.security.key_encryption import decrypt_api_key, encrypt_api_key, mask_key
from schemas.llm_provider_key_model import LlmProviderKeyModel
from schemas.tool_provider_key_model import ToolProviderKeyModel
from schemas.tool_registry_model import ToolRegistryModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _verify_llm_key(provider: str, api_key: str) -> None:
    provider = provider.lower().strip()
    if provider == "openai":
        import openai

        client = openai.OpenAI(api_key=api_key)
        client.models.list()
        return
    if provider == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=16,
            messages=[{"role": "user", "content": "ping"}],
        )
        return
    if provider == "google":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        client.models.generate_content(
            model="gemini-2.5-flash",
            contents="ping",
            config=types.GenerateContentConfig(max_output_tokens=16),
        )
        return
    raise ValueError(f"Unsupported LLM provider: {provider}")


def _verify_tool_key(tool_id: str, provider: str, api_key: str) -> None:
    tool_id = tool_id.lower().strip()
    provider = provider.lower().strip()
    if tool_id == "web-search" and provider == "tavily":
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        client.search("test", max_results=1)
        return
    raise ValueError(f"Unsupported tool/provider combination: {tool_id}/{provider}")


def list_llm_keys(
    db: Session,
    owner: str,
    *,
    provider: Optional[str] = None,
) -> list[LlmProviderKeyModel]:
    query = db.query(LlmProviderKeyModel).filter(
        LlmProviderKeyModel.owner == owner,
        LlmProviderKeyModel.status != "revoked",
    )
    if provider:
        query = query.filter(
            LlmProviderKeyModel.provider == provider.lower().strip()
        )
    return query.order_by(LlmProviderKeyModel.created_at.desc()).all()


def get_llm_key(db: Session, owner: str, key_id: UUID) -> Optional[LlmProviderKeyModel]:
    return (
        db.query(LlmProviderKeyModel)
        .filter(
            LlmProviderKeyModel.id == key_id,
            LlmProviderKeyModel.owner == owner,
            LlmProviderKeyModel.status != "revoked",
        )
        .first()
    )


def list_models_for_llm_key(db: Session, owner: str, key_id: UUID) -> dict:
    from context_jobs.provider_model_catalog import fetch_chat_models_for_key

    row = get_llm_key(db, owner, key_id)
    if not row:
        raise ContextJobsNotFoundError("LLM key not found")
    if row.status != "active":
        raise ValueError(
            f"LLM key '{row.key_label}' is not active (status: {row.status}). "
            "Verify or replace the key before listing models."
        )

    api_key = decrypt_api_key(row.encrypted_key)
    models = fetch_chat_models_for_key(
        row.provider,
        api_key,
        cache_key=f"llm_key:{row.id}",
    )
    return {
        "keyId": row.id,
        "provider": row.provider,
        "keyLabel": row.key_label,
        "models": models,
        "fetchedAt": _now(),
    }


def get_active_llm_key_for_provider(
    db: Session,
    owner: str,
    provider: str,
) -> Optional[LlmProviderKeyModel]:
    """Most recently updated active BYOK key for owner + provider (openai, google, anthropic)."""
    provider = provider.lower().strip()
    return (
        db.query(LlmProviderKeyModel)
        .filter(
            LlmProviderKeyModel.owner == owner,
            LlmProviderKeyModel.provider == provider,
            LlmProviderKeyModel.status == "active",
        )
        .order_by(LlmProviderKeyModel.updated_at.desc())
        .first()
    )


def resolve_llm_key_id_for_provider(
    db: Session,
    owner: str,
    provider: str,
    llm_key_id: Optional[UUID] = None,
) -> UUID:
    """
    Use explicit llmKeyId when provided; otherwise the user's active key for that provider.
    """
    if llm_key_id:
        return llm_key_id
    provider = provider.lower().strip()
    row = get_active_llm_key_for_provider(db, owner, provider)
    if not row:
        display = PROVIDER_REGISTRY.get(provider, {}).get("display_name", provider)
        raise ValueError(
            f"No active BYOK key configured for {display}. "
            "Add a key via POST /context-jobs/llm-keys or set llmKeyId on this job."
        )
    return row.id


def create_llm_key(db: Session, owner: str, data: LlmKeyCreate) -> LlmProviderKeyModel:
    provider = data.provider.lower().strip()
    if provider not in PROVIDER_REGISTRY:
        raise ValueError(f"Unknown provider: {provider}")

    existing = (
        db.query(LlmProviderKeyModel)
        .filter(
            LlmProviderKeyModel.owner == owner,
            LlmProviderKeyModel.provider == provider,
            LlmProviderKeyModel.key_label == data.key_label.strip(),
            LlmProviderKeyModel.status != "revoked",
        )
        .first()
    )
    if existing:
        raise ValueError(f"A key with label '{data.key_label}' already exists for provider '{provider}'")

    _verify_llm_key(provider, data.api_key)

    row = LlmProviderKeyModel(
        owner=owner,
        provider=provider,
        key_label=data.key_label.strip(),
        encrypted_key=encrypt_api_key(data.api_key),
        key_last_four=mask_key(data.api_key),
        status="active",
        last_verified_at=_now(),
        last_error=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    from context_jobs.provider_model_catalog import invalidate_models_cache_for_key

    invalidate_models_cache_for_key(str(row.id))
    return row


def revoke_llm_key(db: Session, owner: str, key_id: UUID) -> None:
    row = (
        db.query(LlmProviderKeyModel)
        .filter(LlmProviderKeyModel.id == key_id, LlmProviderKeyModel.owner == owner)
        .first()
    )
    if not row:
        raise ContextJobsNotFoundError("LLM key not found")
    row.status = "revoked"
    row.updated_at = _now()
    db.add(row)
    db.commit()
    from context_jobs.provider_model_catalog import invalidate_models_cache_for_key

    invalidate_models_cache_for_key(str(key_id))


def verify_llm_key(db: Session, owner: str, key_id: UUID) -> LlmProviderKeyModel:
    row = (
        db.query(LlmProviderKeyModel)
        .filter(LlmProviderKeyModel.id == key_id, LlmProviderKeyModel.owner == owner)
        .first()
    )
    if not row or row.status == "revoked":
        raise ContextJobsNotFoundError("LLM key not found")
    try:
        api_key = decrypt_api_key(row.encrypted_key)
        _verify_llm_key(row.provider, api_key)
        row.last_verified_at = _now()
        row.last_error = None
        row.status = "active"
    except Exception as exc:
        row.last_error = str(exc)
        row.status = "expired"
        db.add(row)
        db.commit()
        raise ValueError(f"Key verification failed: {exc}") from exc
    db.add(row)
    db.commit()
    db.refresh(row)
    from context_jobs.provider_model_catalog import invalidate_models_cache_for_key

    invalidate_models_cache_for_key(str(row.id))
    return row


def resolve_llm_api_key(
    db: Session,
    owner: str,
    llm_key_id: Optional[UUID],
    execution_provider: Optional[str] = None,
    *,
    package_name: Optional[str] = None,
) -> tuple[str, str]:
    import os

    from context_jobs.plan_entitlements import ensure_context_jobs_access
    from repositories.user_repository import UserRepository

    provider_env_map = {
        "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
        "openai": os.environ.get("OPENAI_API_KEY"),
        "google": os.environ.get("GEMINI_API_KEY"),
    }

    user = UserRepository.get_active_by_firebase_uid(owner, db)
    is_admin = bool(user and user.role and str(user.role).lower() == "admin")
    if not is_admin:
        if not user:
            raise ValueError("User not found. Please create an account first.")
        if package_name is None:
            package_name = ensure_context_jobs_access(db, user)
        if package_name == "trial":
            llm_key_id = None
        elif package_name == "pro" and not llm_key_id:
            provider = (execution_provider or "openai").lower().strip()
            llm_key_id = resolve_llm_key_id_for_provider(db, owner, provider)

    if not llm_key_id:
        provider = (execution_provider or "").lower().strip()
        if provider and provider_env_map.get(provider):
            return provider, provider_env_map[provider]

        for provider, env_key in provider_env_map.items():
            if env_key:
                return provider, env_key
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
    row.usage_count = (row.usage_count or 0) + 1
    row.updated_at = _now()
    db.add(row)
    db.commit()
    return row.provider, decrypt_api_key(row.encrypted_key)


def list_tool_keys(db: Session, owner: str) -> list[ToolProviderKeyModel]:
    return (
        db.query(ToolProviderKeyModel)
        .filter(ToolProviderKeyModel.owner == owner, ToolProviderKeyModel.status != "revoked")
        .order_by(ToolProviderKeyModel.created_at.desc())
        .all()
    )


def create_tool_key(db: Session, owner: str, data: ToolKeyCreate) -> ToolProviderKeyModel:
    tool_id = data.tool_id.lower().strip()
    provider = data.provider.lower().strip()
    _verify_tool_key(tool_id, provider, data.api_key)
    row = ToolProviderKeyModel(
        owner=owner,
        tool_id=tool_id,
        provider=provider,
        key_label=data.key_label.strip(),
        encrypted_key=encrypt_api_key(data.api_key),
        key_last_four=mask_key(data.api_key),
        status="active",
        last_verified_at=_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def revoke_tool_key(db: Session, owner: str, key_id: UUID) -> None:
    row = (
        db.query(ToolProviderKeyModel)
        .filter(ToolProviderKeyModel.id == key_id, ToolProviderKeyModel.owner == owner)
        .first()
    )
    if not row:
        raise ContextJobsNotFoundError("LLM key not found")
    row.status = "revoked"
    row.updated_at = _now()
    db.add(row)
    db.commit()


def resolve_tool_api_key(db: Session, owner: str, tool_id: str) -> str:
    tool_id = tool_id.lower().strip()
    row = (
        db.query(ToolProviderKeyModel)
        .filter(
            ToolProviderKeyModel.owner == owner,
            ToolProviderKeyModel.tool_id == tool_id,
            ToolProviderKeyModel.status == "active",
        )
        .order_by(ToolProviderKeyModel.updated_at.desc())
        .first()
    )
    if not row:
        raise ValueError(
            f"No active BYOK key configured for tool '{tool_id}'. "
            "Add a tool provider key before running jobs that use this tool."
        )
    return decrypt_api_key(row.encrypted_key)


def list_provider_catalog(
    db: Session,
    owner: str,
    *,
    package_name: Optional[str] = None,
) -> list[dict]:
    from context_jobs.plan_entitlements import trial_provider_catalog

    if package_name == "trial":
        return trial_provider_catalog()

    user_keys = {k.provider for k in list_llm_keys(db, owner)}
    catalog = []
    for provider, meta in PROVIDER_REGISTRY.items():
        if package_name == "pro" and provider not in user_keys:
            continue
        models = meta["models"]
        catalog.append(
            {
                "provider": provider,
                "displayName": meta["display_name"],
                "models": [
                    {"id": m, "displayName": m} for m in models
                ],
                "hasUserKey": provider in user_keys,
            }
        )
    return catalog


def list_tool_catalog(db: Session, owner: str) -> list[dict]:
    tools = db.query(ToolRegistryModel).filter(ToolRegistryModel.enabled == True).all()
    user_tool_keys = {k.tool_id for k in list_tool_keys(db, owner)}
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "isReadOnly": t.is_read_only,
            "externalProvider": t.external_provider,
            "hasUserKey": t.id in user_tool_keys or t.external_provider is None,
        }
        for t in tools
    ]

