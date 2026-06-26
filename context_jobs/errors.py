"""Map Context Jobs plan errors to HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from context_jobs.plan_entitlements import ContextJobsAccessError, ContextJobsQuotaError


def register_context_jobs_exception_handlers(app: FastAPI) -> None:
    """Return 403/429 for plan errors instead of 500 on unhandled routes."""

    @app.exception_handler(ContextJobsAccessError)
    async def context_jobs_access_handler(
        _request: Request,
        exc: ContextJobsAccessError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ContextJobsQuotaError)
    async def context_jobs_quota_handler(
        _request: Request,
        exc: ContextJobsQuotaError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": str(exc)},
        )


def raise_context_jobs_http(exc: Exception) -> None:
    if isinstance(exc, ContextJobsQuotaError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ContextJobsAccessError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    raise exc
