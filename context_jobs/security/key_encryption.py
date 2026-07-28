"""Fernet encryption for BYOK API keys and vector connection secrets at rest."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


class KeyEncryptionError(Exception):
    """Raised when encryption configuration or operations fail."""


def _fernet() -> Fernet:
    raw = os.environ.get("KEY_ENCRYPTION_KEY", "").strip()
    if not raw:
        raise KeyEncryptionError(
            "KEY_ENCRYPTION_KEY is not configured. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(raw.encode() if isinstance(raw, str) else raw)
    except Exception as exc:
        raise KeyEncryptionError("KEY_ENCRYPTION_KEY is invalid") from exc


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


def encrypt_payload(plaintext: str) -> str:
    """Encrypt an arbitrary string payload (e.g. JSON config)."""
    if plaintext is None:
        raise KeyEncryptionError("Payload cannot be empty")
    return _fernet().encrypt(plaintext.encode("utf-8")).decode()


def decrypt_payload(ciphertext: str) -> str:
    """Decrypt an arbitrary string payload encrypted with encrypt_payload."""
    if not ciphertext:
        raise KeyEncryptionError("Encrypted payload is empty")
    try:
        return _fernet().decrypt(ciphertext.encode()).decode("utf-8")
    except InvalidToken as exc:
        raise KeyEncryptionError("Failed to decrypt payload") from exc


def mask_key(plaintext: str) -> str:
    text = (plaintext or "").strip()
    if len(text) >= 4:
        return text[-4:]
    return "****"
