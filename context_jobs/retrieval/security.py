import base64
import json
from typing import Any


def encrypt_config(raw: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(raw).encode("utf-8")
    return {"v": 1, "ciphertext": base64.b64encode(payload).decode("utf-8")}


def decrypt_config(encrypted: dict[str, Any]) -> dict[str, Any]:
    ciphertext = encrypted.get("ciphertext", "")
    if not ciphertext:
        return {}
    payload = base64.b64decode(ciphertext.encode("utf-8"))
    return json.loads(payload.decode("utf-8"))


def masked_config(raw: dict[str, Any]) -> dict[str, Any]:
    masked = {}
    for k, v in raw.items():
        if "key" in k.lower() or "token" in k.lower() or "secret" in k.lower() or "password" in k.lower():
            masked[k] = "***"
        else:
            masked[k] = v
    return masked

