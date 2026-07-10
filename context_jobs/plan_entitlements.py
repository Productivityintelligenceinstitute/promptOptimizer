"""Context Jobs plan entitlements — permissions DB + subscription package for execution rules."""

from __future__ import annotations

from typing import Any, Optional, Union
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.exceptions.access import AccessDeniedException
from core.exceptions.rate_limit import RateLimitExceededException
from permissions.context_jobs_access import (
    PERMISSION_CONTEXT_JOBS,
    PERMISSION_CONTEXT_JOBS_JOB,
    PERMISSION_CONTEXT_JOBS_RUN,
    get_permission_access,
    get_trial_usage_total,
    permission_limits_for_user,
    record_context_jobs_job_usage,
    record_context_jobs_run_usage,
    validate_context_jobs_feature_access,
    validate_context_jobs_job_create,
    validate_context_jobs_run_create,
)
from repositories.check_package import CheckPackageRepository
from repositories.subscription_repository import SubscriptionRepository
from schemas.context_jobs_model import ContextJobModel, JobRunModel
from schemas.user_model import UserModel

TRIAL_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "google": "gemini-2.5-flash",
    "anthropic": "claude-haiku-4-5",
}


class ContextJobsAccessError(ValueError):
    """Plan does not include Context Jobs or subscription is invalid."""


class ContextJobsQuotaError(ValueError):
    """Trial lifetime cap reached."""


def _map_access_errors(exc: Exception) -> None:
    if isinstance(exc, HTTPException):
        raise ContextJobsAccessError(str(exc.detail)) from exc
    if isinstance(exc, AccessDeniedException):
        raise ContextJobsAccessError(exc.message) from exc
    if isinstance(exc, RateLimitExceededException):
        raise ContextJobsQuotaError(exc.message) from exc
    raise exc


def _as_user(db: Session, owner_or_user: Union[str, UUID, UserModel]) -> UserModel:
    if isinstance(owner_or_user, UserModel):
        return owner_or_user
    if isinstance(owner_or_user, UUID):
        user = (
            db.query(UserModel)
            .filter(
                UserModel.id == owner_or_user,
                UserModel.is_active.is_(True),
                UserModel.deleted_at.is_(None),
            )
            .first()
        )
        if not user:
            raise ContextJobsAccessError("User not found.")
        return user
    from context_jobs.auth import resolve_context_jobs_user

    try:
        return resolve_context_jobs_user(db, owner_or_user)
    except HTTPException as exc:
        raise ContextJobsAccessError(str(exc.detail)) from exc


def resolve_package_name(db: Session, owner_or_user: Union[str, UUID, UserModel]) -> str:
    """Validated package name for execution rules (trial models vs pro BYOK)."""
    user = _as_user(db, owner_or_user)

    if user.role and str(user.role).lower() == "admin":
        return "pro"

    try:
        CheckPackageRepository.check_user_package(db, user.id)
    except HTTPException as exc:
        raise ContextJobsAccessError(str(exc.detail)) from exc

    result = SubscriptionRepository.get_active_with_package(user.id, db)
    if not result:
        raise ContextJobsAccessError(
            "No active subscription or trial has expired. Please upgrade your plan to continue."
        )

    _subscription, package = result
    return package.package_name


def ensure_context_jobs_access(db: Session, owner_or_user: Union[str, UUID, UserModel]) -> str:
    """Ensure CONTEXT_JOBS permission via packages_permission. Returns package_name."""
    user = _as_user(db, owner_or_user)
    try:
        validate_context_jobs_feature_access(db, user.id)
    except Exception as exc:
        _map_access_errors(exc)
    return resolve_package_name(db, user)


def assert_byok_llm_keys_allowed(db: Session, owner_or_user: Union[str, UUID, UserModel]) -> str:
    """
    BYOK LLM key management is pro-only. Trial uses platform keys; essential has no
    Context Jobs access (blocked earlier by ensure_context_jobs_access).
    """
    package_name = ensure_context_jobs_access(db, owner_or_user)
    if package_name != "pro":
        raise ContextJobsAccessError(
            "BYOK LLM keys are only available on Pro. "
            "Trial uses platform API keys; Essential does not include Context Jobs."
        )
    return package_name


def count_jobs(db: Session, owner: str) -> int:
    return db.query(ContextJobModel).filter(ContextJobModel.owner == owner).count()


def count_runs(db: Session, owner: str) -> int:
    return (
        db.query(JobRunModel)
        .join(ContextJobModel, JobRunModel.job_id == ContextJobModel.id)
        .filter(ContextJobModel.owner == owner)
        .count()
    )


def assert_can_create_job(db: Session, owner: str, package_name: str) -> None:
    user = _as_user(db, owner)
    try:
        validate_context_jobs_job_create(db, user.id)
    except Exception as exc:
        _map_access_errors(exc)


def assert_can_create_run(db: Session, owner: str, package_name: str) -> None:
    user = _as_user(db, owner)
    try:
        validate_context_jobs_run_create(db, user.id)
    except Exception as exc:
        _map_access_errors(exc)


def record_job_created(db: Session, owner: str) -> None:
    user = _as_user(db, owner)
    record_context_jobs_job_usage(db, user.id)


def record_run_created(db: Session, owner: str) -> None:
    user = _as_user(db, owner)
    record_context_jobs_run_usage(db, user.id)


def trial_provider_catalog() -> list[dict[str, Any]]:
    from context_jobs.providers.registry import PROVIDER_REGISTRY

    catalog = []
    for provider, model_id in TRIAL_MODELS.items():
        meta = PROVIDER_REGISTRY.get(provider, {})
        catalog.append(
            {
                "provider": provider,
                "displayName": meta.get("display_name", provider),
                "models": [{"id": model_id, "displayName": model_id}],
                "hasUserKey": False,
                "selectable": True,
            }
        )
    return catalog


def _usage_counts(db: Session, user: UserModel, owner_key: str) -> tuple[int, int]:
    job_access = get_permission_access(db, user.id, PERMISSION_CONTEXT_JOBS_JOB)
    run_access = get_permission_access(db, user.id, PERMISSION_CONTEXT_JOBS_RUN)

    if job_access and job_access.query_limit is not None:
        job_count = get_trial_usage_total(db, user.id, job_access.permission_id)
    else:
        job_count = count_jobs(db, owner_key)

    if run_access and run_access.query_limit is not None:
        run_count = get_trial_usage_total(db, user.id, run_access.permission_id)
    else:
        run_count = count_runs(db, owner_key)

    return job_count, run_count


def build_entitlements(
    db: Session,
    owner_or_user: Union[str, UUID, UserModel],
    *,
    owner: Optional[str] = None,
) -> dict[str, Any]:
    """Plan-aware entitlements from packages_permission + subscription package."""
    user = _as_user(db, owner_or_user)
    owner_key = owner or user.firebase_uid or ""
    if not owner_key:
        raise ContextJobsAccessError("User account is missing firebase_uid.")

    feature_access = get_permission_access(db, user.id, PERMISSION_CONTEXT_JOBS)
    try:
        package_name = resolve_package_name(db, user)
    except ContextJobsAccessError as exc:
        return {
            "userId": str(user.id),
            "plan": None,
            "contextJobsEnabled": False,
            "message": str(exc),
            "upgradeRequired": "pro",
            "keyMode": None,
            "limits": None,
            "usage": None,
            "canCreateJob": False,
            "canCreateRun": False,
            "providers": [],
        }

    if not feature_access or not feature_access.is_enabled:
        return {
            "userId": str(user.id),
            "plan": package_name,
            "contextJobsEnabled": False,
            "message": "Context Jobs require a Pro plan. Upgrade to access this feature.",
            "upgradeRequired": "pro",
            "keyMode": None,
            "limits": None,
            "usage": None,
            "canCreateJob": False,
            "canCreateRun": False,
            "providers": [],
        }

    job_limit, run_limit = permission_limits_for_user(db, user.id)
    job_count, run_count = _usage_counts(db, user, owner_key)

    can_create_job = True
    can_create_run = True
    if job_limit is not None:
        can_create_job = job_count < job_limit
    if run_limit is not None:
        can_create_run = run_count < run_limit

    limits = None
    if job_limit is not None or run_limit is not None:
        limits = {
            "maxJobs": job_limit,
            "maxRuns": run_limit,
        }
    usage = {"jobs": job_count, "runs": run_count}

    if package_name == "trial":
        return {
            "userId": str(user.id),
            "plan": package_name,
            "contextJobsEnabled": True,
            "message": None,
            "upgradeRequired": None,
            "keyMode": "platform",
            "limits": limits,
            "usage": usage,
            "canCreateJob": can_create_job,
            "canCreateRun": can_create_run,
            "providers": trial_provider_catalog(),
        }

    from context_jobs.provider_key_services import list_provider_catalog

    providers = [
        {**entry, "selectable": entry.get("hasUserKey", False)}
        for entry in list_provider_catalog(db, owner_key, package_name="pro")
        if entry.get("hasUserKey")
    ]
    return {
        "userId": str(user.id),
        "plan": package_name,
        "contextJobsEnabled": True,
        "message": None,
        "upgradeRequired": None,
        "keyMode": "byok",
        "limits": limits,
        "usage": usage,
        "canCreateJob": can_create_job,
        "canCreateRun": can_create_run,
        "providers": providers,
    }


def normalize_execution_for_plan(
    package_name: str,
    execution_provider: Optional[str],
    execution_model: Optional[str],
    llm_key_id: Optional[UUID],
) -> tuple[str, str, Optional[UUID]]:
    """
    Apply plan rules to execution fields. Returns (provider, model, llm_key_id).
    Trial/pro model and BYOK rules remain package-based; feature access is DB permissions.
    """
    from context_jobs.providers.registry import PROVIDER_REGISTRY, get_default_model

    provider = (execution_provider or "openai").lower().strip()
    if provider not in PROVIDER_REGISTRY:
        raise ValueError(f"Unknown execution provider: {provider}")

    if package_name == "trial":
        if llm_key_id is not None:
            raise ValueError("BYOK keys are not available during trial.")
        allowed_model = TRIAL_MODELS.get(provider)
        if not allowed_model:
            raise ValueError(
                "Trial plan supports openai, google, and anthropic only."
            )
        if execution_model and execution_model != allowed_model:
            raise ValueError(
                f"Trial plan only supports {allowed_model} for provider '{provider}'."
            )
        return provider, allowed_model, None

    if package_name == "pro":
        if not llm_key_id:
            raise ValueError(
                "Pro plan requires a BYOK LLM key for this provider. "
                "Add a key via POST /context-jobs/llm-keys or set llmKeyId on this job."
            )
        model = execution_model or get_default_model(provider)
        return provider, model, llm_key_id

    raise ContextJobsAccessError("Context Jobs require a Pro plan or active trial.")
