"""Parse Coupa / Ironclad browser URLs into provider + resource references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class ClmReference:
    """Resolved CLM resource from a pasted URL or bare ID."""

    provider: str  # coupa | ironclad
    resource_type: str  # contract | workflow | record
    resource_id: str
    host: Optional[str] = None  # e.g. company.coupa.com or na1.ironcladapp.com
    raw_url: Optional[str] = None


_COUPA_SHOW = re.compile(
    r"/contracts/show/(?P<id>\d+)(?:/|$|\?)",
    re.IGNORECASE,
)
_COUPA_API = re.compile(
    r"/api/contracts/(?P<id>\d+)(?:/|$|\?)",
    re.IGNORECASE,
)
_IRONCLAD_WORKFLOW = re.compile(
    r"/workflow/(?P<id>[A-Za-z0-9_-]+)(?:/|$|\?)",
    re.IGNORECASE,
)
_IRONCLAD_RECORD = re.compile(
    r"/record/(?P<id>[A-Za-z0-9_-]+)(?:/|$|\?)",
    re.IGNORECASE,
)


def _normalize_host(netloc: str) -> str:
    host = (netloc or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def parse_clm_reference(
    raw: str,
    *,
    default_provider: Optional[str] = None,
) -> ClmReference:
    """
    Parse a pasted Coupa/Ironclad URL or a bare numeric/hex ID.

    Supported Coupa examples:
      https://acme.coupa.com/contracts/show/12345
      https://acme.coupacloud.com/contracts/show/12345

    Supported Ironclad examples:
      https://na1.ironcladapp.com/workflow/6013609108b8f070cee94fc1
      https://demo.ironcladapp.com/record/abc123
      https://eu1.ironcladapp.com/workflow/IC-12
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("Provide a Coupa or Ironclad contract URL (or resource ID).")

    provider_hint = (default_provider or "").strip().lower() or None

    # Bare ID (no scheme) — requires connection provider context
    if "://" not in text and "/" not in text:
        if not provider_hint:
            raise ValueError(
                "A bare ID needs a CLM connection. Select Coupa or Ironclad, "
                "or paste the full browser URL."
            )
        if provider_hint == "coupa":
            if not text.isdigit():
                raise ValueError("Coupa contract IDs must be numeric.")
            return ClmReference(
                provider="coupa",
                resource_type="contract",
                resource_id=text,
            )
        if provider_hint == "ironclad":
            # Prefer workflow for in-flight; callers may also use record IDs
            return ClmReference(
                provider="ironclad",
                resource_type="workflow",
                resource_id=text,
            )
        raise ValueError(f"Unsupported CLM provider: {provider_hint}")

    # Ensure we can parse relative-looking paths that still contain markers
    candidate = text if "://" in text else f"https://placeholder.local{text if text.startswith('/') else '/' + text}"
    parsed = urlparse(candidate)
    path = parsed.path or ""
    host = _normalize_host(parsed.netloc) if parsed.netloc and parsed.netloc != "placeholder.local" else None

    m = _COUPA_SHOW.search(path) or _COUPA_API.search(path)
    if m:
        return ClmReference(
            provider="coupa",
            resource_type="contract",
            resource_id=m.group("id"),
            host=host,
            raw_url=text if "://" in text else None,
        )

    m = _IRONCLAD_RECORD.search(path)
    if m:
        return ClmReference(
            provider="ironclad",
            resource_type="record",
            resource_id=m.group("id"),
            host=host,
            raw_url=text if "://" in text else None,
        )

    m = _IRONCLAD_WORKFLOW.search(path)
    if m:
        return ClmReference(
            provider="ironclad",
            resource_type="workflow",
            resource_id=m.group("id"),
            host=host,
            raw_url=text if "://" in text else None,
        )

    # Host heuristics when path is unfamiliar but host is known
    if host and ("coupa.com" in host or "coupacloud.com" in host):
        raise ValueError(
            "Coupa URL recognized, but no contract ID found. "
            "Expected a path like /contracts/show/12345."
        )
    if host and "ironcladapp.com" in host:
        raise ValueError(
            "Ironclad URL recognized, but no workflow/record ID found. "
            "Expected /workflow/{id} or /record/{id}."
        )

    raise ValueError(
        "Unrecognized CLM URL. Paste a Coupa /contracts/show/{id} link "
        "or an Ironclad /workflow/{id} or /record/{id} link."
    )
