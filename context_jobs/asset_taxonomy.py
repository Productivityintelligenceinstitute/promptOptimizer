"""Asset taxonomy validation, attachments, and source pack import."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from schemas.context_jobs_model import ContextAssetModel, ContextJobModel

ASSET_TYPES = frozenset(
    {
        "policy",
        "retrieval_profile",
        "validation_contract",
        "memory_policy",
        "style_guide",
        "tool_profile",
        "glossary",
        "source_profile",
        "relationship_pattern",
    }
)

_CONFIG_SKIP_KEYS = frozenset({"attachments", "body", "terms", "patterns", "rules", "validationRules", "toolPermissions", "tools"})


def validate_asset_type(asset_type: str) -> None:
    if asset_type not in ASSET_TYPES:
        raise ValueError(
            f"Invalid asset type {asset_type!r}. Must be one of: {', '.join(sorted(ASSET_TYPES))}"
        )


def validate_asset_content(asset_type: str, content: Any) -> None:
    if content is None:
        return
    if not isinstance(content, dict):
        raise ValueError("Asset content must be a JSON object")
    if asset_type == "glossary":
        terms = content.get("terms")
        if terms is not None and not isinstance(terms, list):
            raise ValueError("glossary assets require content.terms as a list")
    if asset_type == "relationship_pattern":
        patterns = content.get("patterns")
        if patterns is not None and not isinstance(patterns, list):
            raise ValueError("relationship_pattern assets require content.patterns as a list")
    if asset_type == "source_profile":
        for key in ("defaultTrustLevel", "defaultFreshness"):
            if key in content and content[key] is None:
                raise ValueError(f"source_profile content.{key} cannot be null")
    if asset_type == "validation_contract":
        rules = content.get("rules", content.get("validationRules"))
        if rules is not None and not isinstance(rules, list):
            raise ValueError("validation_contract assets require content.rules as a list")
    if asset_type == "tool_profile":
        perms = content.get("toolPermissions", content.get("tools"))
        if perms is not None and not isinstance(perms, list):
            raise ValueError("tool_profile assets require content.toolPermissions as a list")
    if asset_type in {"policy", "style_guide"}:
        body = content.get("body")
        if body is not None and not isinstance(body, str):
            raise ValueError(f"{asset_type} assets require content.body as a string")
    if asset_type in {"retrieval_profile", "memory_policy"} and not content:
        # Empty object is allowed; nothing else to validate.
        return


def normalize_attachments(content: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = content.get("attachments") or []
    if not isinstance(attachments, list):
        raise ValueError("attachments must be a list")
    normalized = []
    for i, att in enumerate(attachments):
        if not isinstance(att, dict):
            continue
        normalized.append(
            {
                "id": att.get("id") or f"att_{i}",
                "type": att.get("type") or "link",
                "name": att.get("name") or "attachment",
                "value": att.get("value") or "",
                "fileName": att.get("fileName"),
                "fileSize": att.get("fileSize"),
            }
        )
    return normalized


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _glossary_fingerprint(term: dict[str, Any]) -> str:
    return _as_text(term.get("term") or term.get("name")).lower()


def _relationship_fingerprint(rel: dict[str, Any]) -> str:
    source = _as_text(
        rel.get("source") or rel.get("fromTerm") or rel.get("from_term") or rel.get("from")
    ).lower()
    target = _as_text(
        rel.get("target") or rel.get("toTerm") or rel.get("to_term") or rel.get("to")
    ).lower()
    relation = _as_text(rel.get("relation") or rel.get("relationship") or "relates to").lower()
    return f"{source}|{relation}|{target}"


def _validation_fingerprint(rule: dict[str, Any]) -> str:
    rule_id = _as_text(rule.get("id")).lower()
    if rule_id:
        return f"id:{rule_id}"
    name = _as_text(rule.get("name")).lower()
    rule_type = _as_text(rule.get("type")).lower()
    return f"{name}|{rule_type}"


def _tool_id(perm: Any) -> str:
    if isinstance(perm, str):
        return perm.strip().lower()
    if isinstance(perm, dict):
        return _as_text(perm.get("toolId") or perm.get("tool_id") or perm.get("id")).lower()
    return ""


def _normalize_glossary_term(raw: dict[str, Any]) -> dict[str, Any] | None:
    term = _as_text(raw.get("term") or raw.get("name"))
    if not term:
        return None
    synonyms_raw = raw.get("synonyms") or []
    synonyms = (
        [_as_text(item) for item in synonyms_raw if _as_text(item)]
        if isinstance(synonyms_raw, list)
        else []
    )
    return {
        "id": _as_text(raw.get("id")) or term,
        "term": term,
        "definition": _as_text(raw.get("definition") or raw.get("meaning")),
        "category": _as_text(raw.get("category")) or "domain",
        "synonyms": synonyms,
        "required": bool(raw.get("required")),
    }


def _normalize_relationship(raw: dict[str, Any]) -> dict[str, Any] | None:
    source = _as_text(
        raw.get("source") or raw.get("fromTerm") or raw.get("from_term") or raw.get("from")
    )
    target = _as_text(
        raw.get("target") or raw.get("toTerm") or raw.get("to_term") or raw.get("to")
    )
    relation = _as_text(raw.get("relation") or raw.get("relationship") or "relates to") or "relates to"
    if not source or not target:
        return None
    return {
        "id": _as_text(raw.get("id")) or f"{source}_{target}",
        "source": source,
        "target": target,
        "relation": relation,
        "fromTerm": source,
        "toTerm": target,
    }


def _normalize_tool_permission(raw: Any) -> dict[str, Any] | None:
    tool_id = _tool_id(raw)
    if not tool_id:
        return None
    if isinstance(raw, dict):
        read_only = raw.get("readOnly")
        if not isinstance(read_only, bool):
            read_only = tool_id not in {"file-write", "docx-generate", "code-exec"}
        return {
            "toolId": tool_id,
            "enabled": raw.get("enabled", True) is not False,
            "readOnly": read_only,
        }
    return {
        "toolId": tool_id,
        "enabled": True,
        "readOnly": tool_id not in {"file-write", "docx-generate", "code-exec"},
    }


def _merge_unique_dicts(
    existing: list[Any],
    incoming: list[Any],
    *,
    fingerprint_fn,
    normalize_fn,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        normalized = normalize_fn(item)
        if not normalized:
            continue
        fingerprint = fingerprint_fn(normalized)
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        merged.append(normalized)
    return merged


def _style_guide_marker(asset_id: Any) -> str:
    return f"[style_guide:{asset_id}]"


def import_asset_into_job(job: ContextJobModel, asset: ContextAssetModel) -> dict[str, Any]:
    """Merge asset content into job fields. Safe to re-run (dedupes where possible)."""
    validate_asset_type(asset.type)
    content = dict(asset.content or {}) if isinstance(asset.content, dict) else {}
    imported: list[str] = []
    skipped_empty = False

    if asset.type == "glossary":
        terms = content.get("terms") or []
        if not isinstance(terms, list) or not terms:
            skipped_empty = True
        else:
            job.glossary_terms = _merge_unique_dicts(
                list(job.glossary_terms or []),
                terms,
                fingerprint_fn=_glossary_fingerprint,
                normalize_fn=_normalize_glossary_term,
            )
            imported.append("glossaryTerms")

    elif asset.type == "relationship_pattern":
        patterns = content.get("patterns") or []
        if not isinstance(patterns, list) or not patterns:
            skipped_empty = True
        else:
            job.relationships = _merge_unique_dicts(
                list(job.relationships or []),
                patterns,
                fingerprint_fn=_relationship_fingerprint,
                normalize_fn=_normalize_relationship,
            )
            imported.append("relationships")

    elif asset.type == "source_profile":
        existing = list(job.trusted_sources or [])
        asset_id = str(asset.id)
        already = any(
            isinstance(item, dict)
            and (
                str(item.get("id") or "") == asset_id
                or (
                    item.get("sourceType") == "asset"
                    and str(item.get("value") or "") == asset_id
                )
            )
            for item in existing
        )
        if already:
            imported.append("trustedSources")
        else:
            profile = {
                "id": asset_id,
                "name": asset.name,
                "sourceType": "asset",
                "value": asset_id,
                "priority": int(content.get("priority") or 3),
                "trustLevel": content.get("defaultTrustLevel") or "preferred",
                "freshness": content.get("defaultFreshness") or "prefer_recent",
                "op": "contains",
            }
            if isinstance(content.get("sourceTypePolicies"), list):
                profile["sourceTypePolicies"] = content["sourceTypePolicies"]
            existing.append(profile)
            job.trusted_sources = existing
            imported.append("trustedSources")

    elif asset.type == "retrieval_profile":
        rc = dict(job.retrieval_config or {})
        updates = {k: v for k, v in content.items() if k not in _CONFIG_SKIP_KEYS}
        if not updates:
            skipped_empty = True
        else:
            rc.update(updates)
            job.retrieval_config = rc
            imported.append("retrievalConfig")

    elif asset.type == "memory_policy":
        mc = dict(job.memory_config or {})
        updates = {k: v for k, v in content.items() if k not in _CONFIG_SKIP_KEYS}
        if not updates:
            skipped_empty = True
        else:
            mc.update(updates)
            job.memory_config = mc
            imported.append("memoryConfig")

    elif asset.type == "validation_contract":
        rules = content.get("rules") or content.get("validationRules") or []
        if not isinstance(rules, list) or not rules:
            skipped_empty = True
        else:
            job.validation_rules = _merge_unique_dicts(
                list(job.validation_rules or []),
                rules,
                fingerprint_fn=_validation_fingerprint,
                normalize_fn=lambda rule: dict(rule) if isinstance(rule, dict) and (
                    _as_text(rule.get("name")) or _as_text(rule.get("id")) or _as_text(rule.get("type"))
                ) else None,
            )
            imported.append("validationRules")

    elif asset.type == "style_guide":
        body = _as_text(content.get("body"))
        if not body:
            skipped_empty = True
        else:
            marker = _style_guide_marker(asset.id)
            current = job.role_configuration or ""
            if marker in current:
                imported.append("roleConfiguration")
            else:
                block = f"\n\nStyle guide ({asset.name}) {marker}:\n{body}"
                job.role_configuration = f"{current}{block}".strip()
                imported.append("roleConfiguration")

    elif asset.type == "policy":
        body = _as_text(content.get("body"))
        if not body:
            skipped_empty = True
        else:
            policy_id = f"policy_{asset.id}"
            existing = list(job.validation_rules or [])
            already = any(
                isinstance(rule, dict) and str(rule.get("id") or "") == policy_id
                for rule in existing
            )
            if not already:
                existing.append(
                    {
                        "id": policy_id,
                        "type": "policy",
                        "name": asset.name,
                        "description": body[:500],
                        "enabled": True,
                        "severity": "blocking",
                    }
                )
                job.validation_rules = existing
            imported.append("validationRules")

    elif asset.type == "tool_profile":
        perms = content.get("toolPermissions") or content.get("tools") or []
        if not isinstance(perms, list) or not perms:
            skipped_empty = True
        else:
            existing = list(job.tool_permissions or [])
            by_id: dict[str, dict[str, Any]] = {}
            for item in existing:
                normalized = _normalize_tool_permission(item)
                if normalized:
                    by_id[normalized["toolId"]] = normalized
            for item in perms:
                normalized = _normalize_tool_permission(item)
                if not normalized:
                    continue
                # Incoming profile wins for the same toolId, but keeps unrelated tools.
                by_id[normalized["toolId"]] = normalized
            job.tool_permissions = list(by_id.values())
            imported.append("toolPermissions")

    result: dict[str, Any] = {
        "assetId": str(asset.id),
        "assetType": asset.type,
        "importedFields": imported,
    }
    if skipped_empty and not imported:
        result["warning"] = "Asset content was empty; nothing was merged into the job."
    return result


def list_source_pack_assets(db: Session, owner: str, workspace_id: Optional[str] = None) -> list[ContextAssetModel]:
    q = db.query(ContextAssetModel).filter(
        ContextAssetModel.type == "source_profile",
        ContextAssetModel.status == "active",
    )
    if hasattr(ContextAssetModel, "owner"):
        q = q.filter(
            (ContextAssetModel.owner == owner) | (ContextAssetModel.owner.is_(None))
        )
    if workspace_id and hasattr(ContextAssetModel, "workspace_id"):
        q = q.filter(
            (ContextAssetModel.workspace_id == workspace_id)
            | (ContextAssetModel.workspace_id.is_(None))
        )
    return q.order_by(ContextAssetModel.updated_at.desc()).all()
