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


def import_asset_into_job(job: ContextJobModel, asset: ContextAssetModel) -> dict[str, Any]:
    """Merge asset content into job fields. Returns summary of imported fields."""
    validate_asset_type(asset.type)
    content = dict(asset.content or {})
    imported: list[str] = []

    if asset.type == "glossary":
        terms = content.get("terms") or []
        existing = list(job.glossary_terms or [])
        for t in terms:
            if isinstance(t, dict) and t.get("term"):
                existing.append(
                    {
                        "id": t.get("id") or t["term"],
                        "term": t["term"],
                        "definition": t.get("definition", ""),
                        "synonyms": t.get("synonyms") or [],
                        "required": bool(t.get("required")),
                    }
                )
        job.glossary_terms = existing
        imported.append("glossaryTerms")

    elif asset.type == "relationship_pattern":
        patterns = content.get("patterns") or []
        existing = list(job.relationships or [])
        for p in patterns:
            if isinstance(p, dict):
                existing.append(
                    {
                        "id": p.get("id") or f"{p.get('from')}_{p.get('to')}",
                        "fromTerm": p.get("from") or p.get("fromTerm"),
                        "relation": p.get("relation", "relates to"),
                        "toTerm": p.get("to") or p.get("toTerm"),
                    }
                )
        job.relationships = existing
        imported.append("relationships")

    elif asset.type == "source_profile":
        profile = {
            "id": str(asset.id),
            "name": asset.name,
            "sourceType": "asset",
            "value": str(asset.id),
            "priority": int(content.get("priority") or 3),
            "trustLevel": content.get("defaultTrustLevel") or "preferred",
            "freshness": content.get("defaultFreshness") or "prefer_recent",
        }
        existing = list(job.trusted_sources or [])
        existing.append(profile)
        job.trusted_sources = existing
        imported.append("trustedSources")

    elif asset.type == "retrieval_profile":
        rc = dict(job.retrieval_config or {})
        rc.update({k: v for k, v in content.items() if k not in ("attachments", "body")})
        job.retrieval_config = rc
        imported.append("retrievalConfig")

    elif asset.type == "memory_policy":
        mc = dict(job.memory_config or {})
        mc.update({k: v for k, v in content.items() if k not in ("attachments", "body")})
        job.memory_config = mc
        imported.append("memoryConfig")

    elif asset.type == "validation_contract":
        rules = content.get("rules") or content.get("validationRules") or []
        existing = list(job.validation_rules or [])
        for r in rules:
            if isinstance(r, dict):
                existing.append(r)
        job.validation_rules = existing
        imported.append("validationRules")

    elif asset.type == "style_guide":
        body = content.get("body") or ""
        if body:
            job.role_configuration = (job.role_configuration or "") + f"\n\nStyle guide:\n{body}"
            imported.append("roleConfiguration")

    elif asset.type == "policy":
        body = content.get("body") or ""
        if body:
            rules = list(job.validation_rules or [])
            rules.append(
                {
                    "id": f"policy_{asset.id}",
                    "type": "policy",
                    "name": asset.name,
                    "description": body[:500],
                    "enabled": True,
                    "severity": "blocking",
                }
            )
            job.validation_rules = rules
            imported.append("validationRules")

    elif asset.type == "tool_profile":
        perms = content.get("toolPermissions") or content.get("tools") or []
        if perms:
            job.tool_permissions = perms
            imported.append("toolPermissions")

    return {"assetId": str(asset.id), "assetType": asset.type, "importedFields": imported}


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
