"""
Pre-flight validation for ingestion operations.

Checks embedding keys, dimension compatibility, account limits, and provider-specific constraints.
Returns structured validation results compatible with Context Jobs error/escalation pattern.
"""

from __future__ import annotations

import os
from typing import Any

from context_jobs.embeddings.registry import MODEL_DEFAULT_DIMS


class ValidationCheck:
    """Single validation check result."""

    def __init__(
        self,
        rule: str,
        passed: bool,
        severity: str,  # "warning" | "error" | "blocking"
        message: str,
        code: str | None = None,
        suggested_action: str | None = None,
    ):
        self.rule = rule
        self.passed = passed
        self.severity = severity
        self.message = message
        self.code = code
        self.suggested_action = suggested_action

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "code": self.code,
            "suggestedAction": self.suggested_action,
        }


def validate_embedding_key(config: dict[str, Any]) -> ValidationCheck:
    """
    Check that the embedding API key exists (server platform key or BYO).

    Severity: blocking (cannot embed without key).
    """
    provider = (config.get("embedding_provider") or "openai").strip().lower()
    byo_key = config.get("embedding_api_key")
    key_id = config.get("embedding_llm_key_id") or config.get("embeddingLlmKeyId")

    if byo_key and str(byo_key).strip():
        return ValidationCheck(
            rule="embedding_key_check",
            passed=True,
            severity="blocking",
            message=f"BYO {provider} embedding key provided.",
        )

    if key_id and str(key_id).strip():
        return ValidationCheck(
            rule="embedding_key_check",
            passed=True,
            severity="blocking",
            message=f"BYOK embedding key id provided for {provider}.",
        )

    # Check server platform keys
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if key:
            return ValidationCheck(
                rule="embedding_key_check",
                passed=True,
                severity="blocking",
                message="Platform OPENAI_API_KEY available.",
            )
        return ValidationCheck(
            rule="embedding_key_check",
            passed=False,
            severity="blocking",
            message="Missing OPENAI_API_KEY. Set server env or provide embedding_api_key on connection.",
            code="missing_embedding_key",
            suggested_action="Add OPENAI_API_KEY to server .env or set embedding_api_key on vector connection.",
        )

    if provider in {"google", "gemini"}:
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if key and key.strip():
            return ValidationCheck(
                rule="embedding_key_check",
                passed=True,
                severity="blocking",
                message="Platform Google/Gemini key available.",
            )
        return ValidationCheck(
            rule="embedding_key_check",
            passed=False,
            severity="blocking",
            message="Missing GOOGLE_API_KEY or GEMINI_API_KEY. Set server env or provide embedding_api_key.",
            code="missing_embedding_key",
            suggested_action="Add GOOGLE_API_KEY to server .env or set embedding_api_key on connection.",
        )

    # Other providers (Cohere, Voyage, Mistral, Jina) require BYO key
    return ValidationCheck(
        rule="embedding_key_check",
        passed=False,
        severity="blocking",
        message=f"Provider '{provider}' requires BYO API key (set embedding_api_key on connection).",
        code="missing_embedding_key",
        suggested_action=f"Set embedding_api_key on vector connection for provider '{provider}'.",
    )


def validate_dimension_match(
    config: dict[str, Any],
    target_dimension: int | None,
) -> ValidationCheck:
    """
    Check that embedding model output dimension matches target index/collection dimension.

    Severity: blocking (dimension mismatch causes insert failures).
    """
    model_id = config.get("embedding_model", "").strip()
    if not model_id:
        return ValidationCheck(
            rule="dimension_match",
            passed=True,
            severity="blocking",
            message="No embedding_model specified; skipping dimension check.",
        )

    expected_dim = MODEL_DEFAULT_DIMS.get(model_id)
    # Check if user overrode dimensions (OpenAI Matryoshka)
    user_dim = config.get("embedding_dimensions")
    if user_dim is not None:
        try:
            expected_dim = int(user_dim)
        except (ValueError, TypeError):
            pass

    if expected_dim is None:
        return ValidationCheck(
            rule="dimension_match",
            passed=True,
            severity="blocking",
            message=f"Unknown embedding model '{model_id}'; cannot verify dimension.",
        )

    if target_dimension is None:
        return ValidationCheck(
            rule="dimension_match",
            passed=True,
            severity="blocking",
            message="Target dimension unknown; skipping match check.",
        )

    if expected_dim == target_dimension:
        return ValidationCheck(
            rule="dimension_match",
            passed=True,
            severity="blocking",
            message=f"Dimension match: {expected_dim} (model) == {target_dimension} (target).",
        )

    return ValidationCheck(
        rule="dimension_match",
        passed=False,
        severity="blocking",
        message=(
            f"Dimension mismatch: embedding_model '{model_id}' outputs {expected_dim}-dim vectors, "
            f"but target expects {target_dimension}-dim. Upsert will fail."
        ),
        code="dimension_mismatch",
        suggested_action=(
            f"Use embedding_model with {target_dimension} dimensions or recreate target with {expected_dim} dimensions."
        ),
    )


def validate_target_exists(
    provider: str,
    target_name: str,
    exists: bool,
    auto_create: bool,
) -> ValidationCheck:
    """
    Check that the target namespace/collection/table exists or auto-create is enabled.

    Severity: error (can be repaired by creating target or enabling auto_create).
    """
    if exists:
        return ValidationCheck(
            rule="target_exists",
            passed=True,
            severity="error",
            message=f"{provider} target '{target_name}' exists.",
        )

    if auto_create:
        return ValidationCheck(
            rule="target_exists",
            passed=True,
            severity="error",
            message=f"{provider} target '{target_name}' will be auto-created.",
        )

    target_type = {
        "pinecone": "namespace",
        "qdrant": "collection",
        "weaviate": "collection",
        "pgvector": "table",
    }.get(provider.lower(), "target")

    return ValidationCheck(
        rule="target_exists",
        passed=False,
        severity="error",
        message=(
            f"{provider} {target_type} '{target_name}' does not exist. "
            f"Enable auto_create_target or create manually."
        ),
        code="target_not_found",
        suggested_action=f"Create {target_type} '{target_name}' or set ingestion_config.auto_create_target=true.",
    )


def check_quota_error(exception: Exception, provider: str) -> ValidationCheck | None:
    """
    Parse provider API exceptions for quota/limit errors.

    Returns ValidationCheck with severity=blocking if quota exceeded, else None.
    """
    msg = str(exception).lower()

    if provider == "pinecone":
        if "forbidden" in msg or "quota" in msg or "limit" in msg:
            return ValidationCheck(
                rule="quota_check",
                passed=False,
                severity="blocking",
                message=f"Pinecone quota or limit exceeded: {exception}",
                code="quota_exceeded",
                suggested_action="Upgrade Pinecone plan, delete unused indexes/namespaces, or contact support.",
            )

    if provider == "qdrant":
        if "quota" in msg or "limit" in msg or "storage" in msg:
            return ValidationCheck(
                rule="quota_check",
                passed=False,
                severity="blocking",
                message=f"Qdrant quota or storage limit exceeded: {exception}",
                code="quota_exceeded",
                suggested_action="Upgrade Qdrant plan or contact support.",
            )

    if provider == "weaviate":
        if "quota" in msg or "limit" in msg or "tenant" in msg:
            return ValidationCheck(
                rule="quota_check",
                passed=False,
                severity="blocking",
                message=f"Weaviate quota or tenant limit exceeded: {exception}",
                code="quota_exceeded",
                suggested_action="Upgrade Weaviate plan or reduce tenant/object count.",
            )

    if provider == "pgvector":
        if "disk" in msg or "storage" in msg or "full" in msg:
            return ValidationCheck(
                rule="quota_check",
                passed=False,
                severity="blocking",
                message=f"PostgreSQL storage full: {exception}",
                code="storage_full",
                suggested_action="Increase database storage or delete old data.",
            )
        if "privilege" in msg or "permission" in msg:
            return ValidationCheck(
                rule="quota_check",
                passed=False,
                severity="blocking",
                message=f"PostgreSQL permission denied: {exception}",
                code="insufficient_privilege",
                suggested_action="Grant INSERT/CREATE permissions to database user.",
            )

    return None
