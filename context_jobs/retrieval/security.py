import json
from typing import Any

from context_jobs.security.key_encryption import decrypt_payload, encrypt_payload


def encrypt_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Fernet-encrypt a vector connection config dict for storage."""
    payload = json.dumps(raw or {})
    return {"v": 2, "ciphertext": encrypt_payload(payload)}


def decrypt_config(encrypted: dict[str, Any]) -> dict[str, Any]:
    """Decrypt a Fernet-encrypted vector connection config."""
    ciphertext = (encrypted or {}).get("ciphertext", "")
    if not ciphertext:
        return {}
    payload = decrypt_payload(ciphertext)
    return json.loads(payload)


def hydrate_embedding_credentials(
    config: dict[str, Any],
    *,
    db: Any = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """
    Resolve embedding_llm_key_id into embedding_api_key when present.
    Leaves config unchanged when no key id is set.
    """
    cfg = dict(config or {})
    raw_key_id = cfg.get("embedding_llm_key_id") or cfg.get("embeddingLlmKeyId")
    if not raw_key_id or not db or not owner:
        return cfg
    if isinstance(cfg.get("embedding_api_key"), str) and cfg["embedding_api_key"].strip():
        return cfg
    from uuid import UUID

    from context_jobs.provider_key_services import resolve_embedding_api_key

    provider = (cfg.get("embedding_provider") or "").strip().lower() or None
    cfg["embedding_api_key"] = resolve_embedding_api_key(
        db,
        owner,
        UUID(str(raw_key_id)),
        expected_provider=provider,
    )
    return cfg


def masked_config(raw: dict[str, Any]) -> dict[str, Any]:
    masked = {}
    for k, v in raw.items():
        if "key" in k.lower() or "token" in k.lower() or "secret" in k.lower() or "password" in k.lower():
            masked[k] = "***"
        else:
            masked[k] = v
    return masked
