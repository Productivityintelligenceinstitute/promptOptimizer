from fastapi import APIRouter

from apis.routers.context_jobs import assets, ingestion, jobs, procurement, runs, workspace

context_jobs_router = APIRouter(prefix="/context-jobs")

context_jobs_router.include_router(jobs.router)
context_jobs_router.include_router(runs.router)
context_jobs_router.include_router(assets.router)
context_jobs_router.include_router(workspace.router)
context_jobs_router.include_router(ingestion.router)
context_jobs_router.include_router(procurement.router)
