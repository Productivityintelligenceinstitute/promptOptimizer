"""Ironclad Public API adapter — Bearer token + workflow/record document download."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from context_jobs.clm.adapters.base import ClmDocument
from context_jobs.clm.url_parser import ClmReference

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_S = 60.0
DEFAULT_HOST = "na1.ironcladapp.com"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_loopback_host(host: str) -> bool:
    hostname = (host or "").split("%", 1)[0].split(":", 1)[0].strip().strip("[]").lower()
    return hostname in _LOOPBACK_HOSTS


class IroncladAdapter:
    provider = "ironclad"

    def test_connection(self, config: dict[str, Any]) -> tuple[bool, str]:
        try:
            base = self._api_base(config)
            headers = self._auth_headers(config)
            with httpx.Client(timeout=REQUEST_TIMEOUT_S) as client:
                # Prefer records list (signed contracts); fall back to workflows
                resp = client.get(f"{base}/records", headers=headers, params={"pageSize": 1})
                if resp.status_code in (401, 403):
                    # Try workflows if record scope is missing
                    resp = client.get(f"{base}/workflows", headers=headers, params={"pageSize": 1})
                if resp.status_code in (401, 403):
                    return False, (
                        f"Ironclad auth failed ({resp.status_code}). "
                        "Check the API token and that it can read records/workflows."
                    )
                if resp.status_code >= 400:
                    return False, f"Ironclad test returned HTTP {resp.status_code}: {resp.text[:240]}"
            return True, "Ironclad API token verified."
        except Exception as exc:
            return False, str(exc) or "Ironclad connection test failed."

    def fetch_document(
        self,
        config: dict[str, Any],
        reference: ClmReference,
    ) -> ClmDocument:
        if reference.provider != "ironclad":
            raise ValueError("Ironclad adapter expects an Ironclad reference.")

        if reference.resource_type == "record":
            return self._fetch_record_attachment(config, reference)
        if reference.resource_type == "workflow":
            return self._fetch_workflow_document(config, reference)
        raise ValueError(f"Unsupported Ironclad resource type: {reference.resource_type}")

    # ------------------------------------------------------------------ helpers

    def _api_base(self, config: dict[str, Any], *, host_override: Optional[str] = None) -> str:
        """
        Build the Public API root.

        Production hosts stay on https://{region}.ironcladapp.com/public/api/v1.
        A full http(s) base_url (used by the local CLM mock) keeps its scheme and port.
        Loopback hosts default to http so localhost mocks work without TLS.
        """
        scheme = "https"
        host = (host_override or "").strip().lower()
        if not host:
            raw = (
                config.get("base_url")
                or config.get("baseUrl")
                or config.get("host")
                or DEFAULT_HOST
            ).strip()
            if raw.startswith("http://"):
                scheme = "http"
                host = raw[7:].split("/", 1)[0].lower()
            elif raw.startswith("https://"):
                scheme = "https"
                host = raw[8:].split("/", 1)[0].lower()
            else:
                host = raw.lower()
        if host.endswith(".com") and "/" in host:
            host = host.split("/", 1)[0]
        if not host:
            host = DEFAULT_HOST
        # Bare region only (na1 / eu1 / demo) — not localhost:8765 or 127.0.0.1:8765
        if "." not in host and ":" not in host:
            host = f"{host}.ironcladapp.com"
        if _is_loopback_host(host):
            scheme = "http"
        return f"{scheme}://{host}/public/api/v1"

    def _origin(self, config: dict[str, Any], *, host_override: Optional[str] = None) -> str:
        base = self._api_base(config, host_override=host_override)
        # https://na1.ironcladapp.com/public/api/v1 -> https://na1.ironcladapp.com
        return base.split("/public/api/", 1)[0]

    def _api_token(self, config: dict[str, Any]) -> str:
        token = (
            config.get("api_token")
            or config.get("apiToken")
            or config.get("api_key")
            or config.get("apiKey")
            or config.get("token")
            or ""
        ).strip()
        if not token:
            raise ValueError("Ironclad config requires api_token.")
        return token

    def _auth_headers(self, config: dict[str, Any]) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_token(config)}",
            "Accept": "application/json",
        }
        as_email = (
            config.get("as_user_email")
            or config.get("asUserEmail")
            or config.get("x_as_user_email")
            or ""
        ).strip()
        as_user_id = (
            config.get("as_user_id")
            or config.get("asUserId")
            or config.get("x_as_user_id")
            or ""
        ).strip()
        if as_email:
            headers["x-as-user-email"] = as_email
        elif as_user_id:
            headers["x-as-user-id"] = as_user_id
        return headers

    def _fetch_workflow_document(
        self,
        config: dict[str, Any],
        reference: ClmReference,
    ) -> ClmDocument:
        base = self._api_base(config, host_override=reference.host)
        origin = self._origin(config, host_override=reference.host)
        headers = self._auth_headers(config)
        workflow_id = reference.resource_id

        with httpx.Client(timeout=REQUEST_TIMEOUT_S) as client:
            resp = client.get(f"{base}/workflows/{workflow_id}", headers=headers)
            if resp.status_code == 404:
                raise ValueError(f"Ironclad workflow {workflow_id} was not found.")
            if resp.status_code >= 400:
                raise ValueError(
                    f"Ironclad workflow lookup failed ({resp.status_code}): {resp.text[:300]}"
                )
            data = resp.json() if resp.content else {}
            download_path = self._pick_workflow_download_path(data)
            if not download_path:
                raise ValueError(
                    "This Ironclad workflow has no downloadable signed or draft document yet."
                )
            file_resp = self._download_path(client, origin, base, download_path, headers)

        title = (data.get("title") or f"Ironclad workflow {workflow_id}").strip()
        filename = self._filename_from_response(
            file_resp, fallback=f"ironclad-workflow-{workflow_id}.pdf"
        )
        return ClmDocument(
            content=file_resp.content,
            filename=filename,
            content_type=(file_resp.headers.get("content-type") or "").split(";")[0].strip() or None,
            provider="ironclad",
            resource_type="workflow",
            resource_id=workflow_id,
            metadata={
                "name": title,
                "contractId": data.get("ironcladId") or workflow_id,
                "ironcladId": data.get("ironcladId"),
                "workflowId": data.get("id") or workflow_id,
                "step": data.get("step"),
            },
        )

    def _fetch_record_attachment(
        self,
        config: dict[str, Any],
        reference: ClmReference,
    ) -> ClmDocument:
        base = self._api_base(config, host_override=reference.host)
        headers = self._auth_headers(config)
        record_id = reference.resource_id
        attachment_key = (
            config.get("attachment_key")
            or config.get("attachmentKey")
            or "signedCopy"
        ).strip() or "signedCopy"

        with httpx.Client(timeout=REQUEST_TIMEOUT_S) as client:
            meta_resp = client.get(f"{base}/records/{record_id}", headers=headers)
            meta: dict[str, Any] = {}
            if meta_resp.status_code == 200 and meta_resp.content:
                try:
                    meta = meta_resp.json()
                except Exception:
                    meta = {}

            file_resp = client.get(
                f"{base}/records/{record_id}/attachments/{attachment_key}",
                headers={**headers, "Accept": "*/*"},
            )
            if file_resp.status_code == 404 and attachment_key != "signedCopy":
                file_resp = client.get(
                    f"{base}/records/{record_id}/attachments/signedCopy",
                    headers={**headers, "Accept": "*/*"},
                )
            if file_resp.status_code == 404:
                raise ValueError(
                    f"No '{attachment_key}' attachment on Ironclad record {record_id}."
                )
            if file_resp.status_code >= 400:
                raise ValueError(
                    f"Ironclad record attachment download failed ({file_resp.status_code}): "
                    f"{file_resp.text[:300]}"
                )
            if not file_resp.content:
                raise ValueError("Ironclad record attachment was empty.")

        name = (
            meta.get("name")
            or meta.get("title")
            or f"Ironclad record {record_id}"
        )
        filename = self._filename_from_response(
            file_resp, fallback=f"ironclad-record-{record_id}.pdf"
        )
        return ClmDocument(
            content=file_resp.content,
            filename=filename,
            content_type=(file_resp.headers.get("content-type") or "").split(";")[0].strip() or None,
            provider="ironclad",
            resource_type="record",
            resource_id=record_id,
            metadata={
                "name": name,
                "contractId": meta.get("ironcladId") or record_id,
                "ironcladId": meta.get("ironcladId"),
                "recordId": meta.get("id") or record_id,
            },
        )

    def _pick_workflow_download_path(self, data: dict[str, Any]) -> Optional[str]:
        attrs = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
        signed = attrs.get("signed")
        if isinstance(signed, dict) and signed.get("download"):
            return str(signed["download"])
        if isinstance(signed, list) and signed:
            first = signed[0]
            if isinstance(first, dict) and first.get("download"):
                return str(first["download"])

        draft = attrs.get("draft")
        if isinstance(draft, list) and draft:
            first = draft[0]
            if isinstance(first, dict) and first.get("download"):
                return str(first["download"])
        if isinstance(draft, dict) and draft.get("download"):
            return str(draft["download"])
        return None

    def _download_path(
        self,
        client: httpx.Client,
        origin: str,
        api_base: str,
        download_path: str,
        headers: dict[str, str],
    ) -> httpx.Response:
        path = download_path.strip()
        if path.startswith("http"):
            url = path
        elif path.startswith("/public/api/"):
            url = f"{origin}{path}"
        elif path.startswith("/"):
            url = f"{origin}{path}"
        else:
            url = f"{api_base.rstrip('/')}/{path.lstrip('/')}"

        resp = client.get(url, headers={**headers, "Accept": "*/*"})
        if resp.status_code >= 400:
            raise ValueError(
                f"Ironclad document download failed ({resp.status_code}): {resp.text[:300]}"
            )
        if not resp.content:
            raise ValueError("Ironclad document download returned empty content.")
        return resp

    @staticmethod
    def _filename_from_response(resp: httpx.Response, *, fallback: str) -> str:
        cd = resp.headers.get("content-disposition") or ""
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.IGNORECASE)
        if match:
            name = match.group(1).strip().strip("'")
            if name:
                return name
        ctype = (resp.headers.get("content-type") or "").lower()
        if "pdf" in ctype:
            return fallback if fallback.endswith(".pdf") else f"{fallback}.pdf"
        if "word" in ctype or "officedocument" in ctype:
            return fallback if fallback.endswith(".docx") else f"{fallback}.docx"
        return fallback
