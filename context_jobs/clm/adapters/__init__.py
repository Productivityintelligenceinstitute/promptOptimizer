"""CLM adapter registry."""

from __future__ import annotations

from typing import Any

from context_jobs.clm.adapters.coupa import CoupaAdapter
from context_jobs.clm.adapters.ironclad import IroncladAdapter

_ADAPTERS: dict[str, Any] = {
    "coupa": CoupaAdapter(),
    "ironclad": IroncladAdapter(),
}

SUPPORTED_CLM_PROVIDERS = frozenset(_ADAPTERS.keys())


def get_clm_adapter(provider: str):
    key = (provider or "").strip().lower()
    adapter = _ADAPTERS.get(key)
    if not adapter:
        supported = ", ".join(sorted(SUPPORTED_CLM_PROVIDERS))
        raise ValueError(f"Unsupported CLM provider '{provider}'. Supported: {supported}.")
    return adapter
