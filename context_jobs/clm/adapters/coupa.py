"""Coupa Core API adapter — OAuth client credentials + retrieve_legal_agreement."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from context_jobs.clm.adapters.base import ClmDocument
from context_jobs.clm.url_parser import ClmReference

logger = logging.getLogger(__name__)

DEFAULT_SCOPE = "core.contract.read"
REQUEST_TIMEOUT_S = 60.0


class CoupaAdapter:
    provider = "coupa"

    def test_connection(self, config: dict[str, Any]) -> tuple[bool, str]:
        try:
            token = self._get_access_token(config)
            instance = self._instance_url(config)
            # Lightweight authenticated probe — list one contract page
            with httpx.Client(timeout=REQUEST_TIMEOUT_S) as client:
                resp = client.get(
                    f"{instance}/api/contracts",
                    headers=self._auth_headers(token),
                    params={"limit": 1},
                )
            if resp.status_code in (200, 404):
                return True, "Coupa OAuth credentials verified."
            if resp.status_code in (401, 403):
                return False, f"Coupa auth failed ({resp.status_code}). Check client ID, secret, and scopes."
            return False, f"Coupa test returned HTTP {resp.status_code}: {resp.text[:240]}"
        except Exception as exc:
            return False, str(exc) or "Coupa connection test failed."

    def fetch_document(
        self,
        config: dict[str, Any],
        reference: ClmReference,
    ) -> ClmDocument:
        if reference.provider != "coupa" or reference.resource_type != "contract":
            raise ValueError("Coupa adapter expects a Coupa contract reference.")

        contract_id = reference.resource_id
        token = self._get_access_token(config)
        instance = self._instance_url(config, host_override=reference.host)
        headers = self._auth_headers(token)

        with httpx.Client(timeout=REQUEST_TIMEOUT_S) as client:
            meta = self._fetch_contract_meta(client, instance, headers, contract_id)
            try:
                return self._retrieve_legal_agreement(
                    client, instance, headers, contract_id, meta
                )
            except ValueError as primary_exc:
                # Fallback: first file attachment on the contract
                try:
                    return self._retrieve_first_attachment(
                        client, instance, headers, contract_id, meta
                    )
                except Exception:
                    raise primary_exc from None

    # ------------------------------------------------------------------ helpers

    def _instance_url(
        self, config: dict[str, Any], *, host_override: Optional[str] = None
    ) -> str:
        if host_override:
            host = host_override.strip().lower()
            if not host.startswith("http"):
                return f"https://{host}".rstrip("/")
            return host.rstrip("/")

        raw = (
            config.get("instance_url")
            or config.get("instanceUrl")
            or config.get("site_url")
            or config.get("siteUrl")
            or ""
        ).strip()
        if not raw:
            raise ValueError("Coupa config requires instance_url (e.g. https://acme.coupa.com).")
        if not raw.startswith("http"):
            raw = f"https://{raw}"
        return raw.rstrip("/")

    def _client_credentials(self, config: dict[str, Any]) -> tuple[str, str, str]:
        client_id = (
            config.get("client_id") or config.get("clientId") or ""
        ).strip()
        client_secret = (
            config.get("client_secret") or config.get("clientSecret") or ""
        ).strip()
        scope = (
            config.get("scope") or DEFAULT_SCOPE
        ).strip() or DEFAULT_SCOPE
        if not client_id or not client_secret:
            raise ValueError("Coupa config requires client_id and client_secret.")
        return client_id, client_secret, scope

    def _get_access_token(self, config: dict[str, Any]) -> str:
        instance = self._instance_url(config)
        client_id, client_secret, scope = self._client_credentials(config)
        with httpx.Client(timeout=REQUEST_TIMEOUT_S) as client:
            resp = client.post(
                f"{instance}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if resp.status_code >= 400:
            raise ValueError(
                f"Coupa token request failed ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        token = (data.get("access_token") or "").strip()
        if not token:
            raise ValueError("Coupa token response did not include access_token.")
        return token

    @staticmethod
    def _auth_headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    def _fetch_contract_meta(
        self,
        client: httpx.Client,
        instance: str,
        headers: dict[str, str],
        contract_id: str,
    ) -> dict[str, Any]:
        resp = client.get(f"{instance}/api/contracts/{contract_id}", headers=headers)
        if resp.status_code == 404:
            raise ValueError(f"Coupa contract {contract_id} was not found.")
        if resp.status_code >= 400:
            raise ValueError(
                f"Coupa contract lookup failed ({resp.status_code}): {resp.text[:300]}"
            )
        try:
            payload = resp.json()
        except Exception:
            return {}
        # Coupa sometimes wraps as {"contract": {...}}
        if isinstance(payload, dict) and isinstance(payload.get("contract"), dict):
            return payload["contract"]
        return payload if isinstance(payload, dict) else {}

    def _retrieve_legal_agreement(
        self,
        client: httpx.Client,
        instance: str,
        headers: dict[str, str],
        contract_id: str,
        meta: dict[str, Any],
    ) -> ClmDocument:
        resp = client.get(
            f"{instance}/api/contracts/{contract_id}/retrieve_legal_agreement",
            headers={**headers, "Accept": "*/*"},
        )
        if resp.status_code == 404:
            raise ValueError(
                "No legal agreement file is attached to this Coupa contract. "
                "Upload the MSA in Coupa, or attach a file and retry."
            )
        if resp.status_code >= 400:
            raise ValueError(
                f"Coupa retrieve_legal_agreement failed ({resp.status_code}): {resp.text[:300]}"
            )
        if not resp.content:
            raise ValueError("Coupa returned an empty legal agreement file.")

        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        # Reject HTML login pages accidentally returned
        if "text/html" in content_type or resp.content[:15].lstrip().lower().startswith(b"<!doctype"):
            raise ValueError(
                "Coupa returned an HTML page instead of a file. "
                "Check OAuth scopes (core.contract.read) and that a legal agreement exists."
            )

        filename = self._filename_from_response(resp, fallback=f"coupa-contract-{contract_id}.pdf")
        return ClmDocument(
            content=resp.content,
            filename=filename,
            content_type=content_type or None,
            provider="coupa",
            resource_type="contract",
            resource_id=contract_id,
            metadata=self._public_meta(meta, contract_id),
        )

    def _retrieve_first_attachment(
        self,
        client: httpx.Client,
        instance: str,
        headers: dict[str, str],
        contract_id: str,
        meta: dict[str, Any],
    ) -> ClmDocument:
        list_resp = client.get(
            f"{instance}/api/contracts/{contract_id}/attachments",
            headers=headers,
        )
        if list_resp.status_code >= 400:
            raise ValueError(
                f"Coupa attachments list failed ({list_resp.status_code}): {list_resp.text[:240]}"
            )
        payload = list_resp.json()
        attachments = payload if isinstance(payload, list) else payload.get("attachments") or []
        if not isinstance(attachments, list) or not attachments:
            raise ValueError("No Coupa attachments available on this contract.")

        first = attachments[0] if isinstance(attachments[0], dict) else {}
        att_id = first.get("id")
        if att_id is None:
            raise ValueError("Coupa attachment is missing an id.")

        file_resp = client.get(
            f"{instance}/api/contracts/{contract_id}/attachments/{att_id}",
            headers={**headers, "Accept": "*/*"},
        )
        if file_resp.status_code >= 400:
            # Some Coupa tenants expose file-url instead of binary on show
            file_url = (first.get("file-url") or first.get("file_url") or first.get("url") or "").strip()
            if file_url:
                file_resp = client.get(
                    file_url if file_url.startswith("http") else f"{instance}{file_url}",
                    headers={**headers, "Accept": "*/*"},
                )
            if file_resp.status_code >= 400:
                raise ValueError(
                    f"Coupa attachment download failed ({file_resp.status_code})."
                )

        if not file_resp.content:
            raise ValueError("Coupa attachment download returned empty content.")

        filename = self._filename_from_response(
            file_resp, fallback=f"coupa-attachment-{contract_id}-{att_id}.pdf"
        )
        return ClmDocument(
            content=file_resp.content,
            filename=filename,
            content_type=(file_resp.headers.get("content-type") or "").split(";")[0].strip() or None,
            provider="coupa",
            resource_type="contract",
            resource_id=contract_id,
            metadata=self._public_meta(meta, contract_id),
        )

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

    @staticmethod
    def _public_meta(meta: dict[str, Any], contract_id: str) -> dict[str, Any]:
        name = meta.get("name") or meta.get("number") or f"Coupa contract {contract_id}"
        supplier = meta.get("supplier")
        vendor = None
        if isinstance(supplier, dict):
            vendor = supplier.get("name")
        elif isinstance(supplier, str):
            vendor = supplier
        out: dict[str, Any] = {
            "contractId": str(meta.get("id") or contract_id),
            "contractNumber": meta.get("number"),
            "name": name,
            "status": meta.get("status"),
            "endDate": meta.get("end-date") or meta.get("end_date"),
            "startDate": meta.get("start-date") or meta.get("start_date"),
        }
        if vendor:
            out["vendor"] = vendor
        return {k: v for k, v in out.items() if v is not None}
