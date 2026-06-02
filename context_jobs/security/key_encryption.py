"""Fernet encryption for BYOK API keys at rest."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class KeyEncryptionError(Exception):
    """Raised when encryption configuration or operations fail."""


def _fernet() -> Fernet:
    raw = os.environ.get("LLM_KEY_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise KeyEncryptionError(
            "LLM_KEY_ENCRYPTION_KEY is not configured. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(raw.encode() if isinstance(raw, str) else raw)
    except Exception as exc:
        raise KeyEncryptionError("LLM_KEY_ENCRYPTION_KEY is invalid") from exc


def encrypt_api_key(plaintext: str) -> str:
    if not plaintext or not plaintext.strip():
        raise KeyEncryptionError("API key cannot be empty")
    return _fernet().encrypt(plaintext.strip().encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    if not ciphertext:
        raise KeyEncryptionError("Encrypted key payload is empty")
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise KeyEncryptionError("Failed to decrypt API key") from exc


def mask_key(plaintext: str) -> str:
    text = (plaintext or "").strip()
    if len(text) >= 4:
        return text[-4:]
    return "****"
