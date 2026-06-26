"""Context Jobs access via permissions + packages_permission (same pattern as prompt optimizer)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.exceptions.access import AccessDeniedException
from core.exceptions.rate_limit import RateLimitExceededException
from repositories.check_access import AccessRepository
from repositories.check_package import CheckPackageRepository
from repositories.check_role import RoleRepository
from repositories.daily_usage import UsageRepository
from repositories.subscription_repository import SubscriptionRepository
from schemas.packages_model import PackagesModel
from schemas.subscription_model import SubscriptionsModel

PERMISSION_CONTEXT_JOBS = "CONTEXT_JOBS"
PERMISSION_CONTEXT_JOBS_JOB = "CONTEXT_JOBS_JOB"
PERMISSION_CONTEXT_JOBS_RUN = "CONTEXT_JOBS_RUN"


def _is_admin(db: Session, user_id: UUID) -> bool:
    return RoleRepository.check_role(db, user_id) == "admin"


def _get_trial_subscription(db: Session, user_id: UUID):
    return (
        db.query(SubscriptionsModel, PackagesModel)
        .join(PackagesModel, SubscriptionsModel.package_id == PackagesModel.id)
        .filter(
            SubscriptionsModel.user_id == user_id,
            SubscriptionsModel.status == "active",
            PackagesModel.package_name == "trial",
        )
        .first()
    )


def get_permission_access(db: Session, user_id: UUID, permission_name: str):
    """Return packages_permission row for the user's active package, or None."""
    return AccessRepository.check_access(db, user_id, permission_name)


def _ensure_subscription_valid(db: Session, user_id: UUID) -> None:
    CheckPackageRepository.check_user_package(db, user_id)


def _enforce_trial_total_cap(
    db: Session,
    user_id: UUID,
    permission_id: UUID,
    total_limit: int,
) -> None:
    trial_subscription = _get_trial_subscription(db, user_id)
    if not trial_subscription:
        return
    sub, _pkg = trial_subscription
    if not sub.start_date or not sub.end_date:
        return
    UsageRepository.check_trial_total_usage(
        db=db,
        user_id=user_id,
        permission_id=permission_id,
        trial_start_date=sub.start_date.date(),
        trial_end_date=sub.end_date.date(),
        total_limit=total_limit,
    )


def _reject_essential_package(db: Session, user_id: UUID) -> None:
    result = SubscriptionRepository.get_active_with_package(user_id, db)
    if not result:
        return
    _subscription, package = result
    if package.package_name == "essential":
        raise AccessDeniedException(
            "Context Jobs require a Pro plan. Upgrade to access this feature."
        )


def validate_context_jobs_feature_access(db: Session, user_id: UUID) -> None:
    """Gate list/read/use Context Jobs (no usage increment)."""
    if _is_admin(db, user_id):
        return
    _ensure_subscription_valid(db, user_id)
    _reject_essential_package(db, user_id)
    access = get_permission_access(db, user_id, PERMISSION_CONTEXT_JOBS)
    if not access or not access.is_enabled:
        raise AccessDeniedException(
            "Context Jobs require a Pro plan or active trial. Upgrade to access this feature."
        )


def validate_context_jobs_job_create(db: Session, user_id: UUID) -> None:
    """Gate job creation; enforces trial lifetime cap from packages_permission.query_limit."""
    if _is_admin(db, user_id):
        return
    _ensure_subscription_valid(db, user_id)
    _reject_essential_package(db, user_id)
    access = get_permission_access(db, user_id, PERMISSION_CONTEXT_JOBS_JOB)
    if not access or not access.is_enabled:
        raise AccessDeniedException(
            "Context Jobs job creation is not enabled for your plan."
        )
    if access.query_limit is not None:
        try:
            _enforce_trial_total_cap(db, user_id, access.permission_id, access.query_limit)
        except RateLimitExceededException as exc:
            raise RateLimitExceededException(
                f"Trial limit reached: {access.query_limit} context jobs. "
                "Upgrade to Pro for unlimited jobs."
            ) from exc


def validate_context_jobs_run_create(db: Session, user_id: UUID) -> None:
    """Gate run creation; enforces trial lifetime cap from packages_permission.query_limit."""
    if _is_admin(db, user_id):
        return
    _ensure_subscription_valid(db, user_id)
    _reject_essential_package(db, user_id)
    access = get_permission_access(db, user_id, PERMISSION_CONTEXT_JOBS_RUN)
    if not access or not access.is_enabled:
        raise AccessDeniedException(
            "Context Jobs run creation is not enabled for your plan."
        )
    if access.query_limit is not None:
        try:
            _enforce_trial_total_cap(db, user_id, access.permission_id, access.query_limit)
        except RateLimitExceededException as exc:
            raise RateLimitExceededException(
                f"Trial limit reached: {access.query_limit} runs. "
                "Upgrade to Pro for unlimited runs."
            ) from exc


def record_context_jobs_job_usage(db: Session, user_id: UUID) -> None:
    if _is_admin(db, user_id):
        return
    access = get_permission_access(db, user_id, PERMISSION_CONTEXT_JOBS_JOB)
    if access:
        UsageRepository.increment_daily_usage(db, user_id, access.permission_id)


def record_context_jobs_run_usage(db: Session, user_id: UUID) -> None:
    if _is_admin(db, user_id):
        return
    access = get_permission_access(db, user_id, PERMISSION_CONTEXT_JOBS_RUN)
    if access:
        UsageRepository.increment_daily_usage(db, user_id, access.permission_id)


def get_trial_usage_total(
    db: Session,
    user_id: UUID,
    permission_id: UUID,
) -> int:
    trial_subscription = _get_trial_subscription(db, user_id)
    if not trial_subscription:
        return 0
    sub, _pkg = trial_subscription
    if not sub.start_date or not sub.end_date:
        return 0
    return UsageRepository.get_trial_total_usage(
        db,
        user_id,
        permission_id,
        sub.start_date.date(),
        sub.end_date.date(),
    )


def permission_limits_for_user(
    db: Session,
    user_id: UUID,
) -> tuple[Optional[int], Optional[int]]:
    """(max_jobs, max_runs) from packages_permission.query_limit, or None if unlimited."""
    job_access = get_permission_access(db, user_id, PERMISSION_CONTEXT_JOBS_JOB)
    run_access = get_permission_access(db, user_id, PERMISSION_CONTEXT_JOBS_RUN)
    job_limit = (
        job_access.query_limit
        if job_access and job_access.is_enabled and job_access.query_limit is not None
        else None
    )
    run_limit = (
        run_access.query_limit
        if run_access and run_access.is_enabled and run_access.query_limit is not None
        else None
    )
    return job_limit, run_limit
