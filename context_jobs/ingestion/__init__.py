"""
Context Jobs vector ingestion.

Import from submodules to avoid import cycles at package load:
  from context_jobs.ingestion.ingestion_service import ingest_documents
"""

from context_jobs.ingestion.types import IngestionResult, IngestionTarget, UpsertResult

__all__ = [
    "IngestionResult",
    "IngestionTarget",
    "UpsertResult",
    "ingest_documents",
    "validate_ingestion_setup",
    "get_ingestion_adapter",
]


def __getattr__(name: str):
    if name == "ingest_documents":
        from context_jobs.ingestion.ingestion_service import ingest_documents

        return ingest_documents
    if name == "validate_ingestion_setup":
        from context_jobs.ingestion.ingestion_service import validate_ingestion_setup

        return validate_ingestion_setup
    if name == "get_ingestion_adapter":
        from context_jobs.ingestion.factory import get_ingestion_adapter

        return get_ingestion_adapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
