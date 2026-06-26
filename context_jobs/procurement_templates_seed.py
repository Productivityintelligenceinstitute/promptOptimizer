"""Idempotent seed for procurement system job templates and shared assets."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from context_jobs.asset_taxonomy import import_asset_into_job
from schemas.context_jobs_model import ContextAssetModel, ContextJobModel

logger = logging.getLogger(__name__)

SYSTEM_OWNER = "__system__"

VALIDATION_CONTRACT_ASSET_NAME = "Procurement Validation Contract"

# Rule IDs owned by the validation_contract asset (used for patch re-import).
VALIDATION_CONTRACT_RULE_IDS = frozenset(
    {
        "proc_citation",
        "proc_format",
        "proc_high_risk",
        "proc_mandatory_clauses",
    }
)

ASSET_NAMES = (
    "Procurement Glossary",
    "Procurement Validation Contract",
    "Procurement Tool Profile",
    "Policy Placeholder",
    "Trusted Source Profile",
)

ANALYSIS_BUDGET_SETTINGS: dict[str, Any] = {
    "maxTokens": 4096,
    "maxTotalTokens": 24000,
    "maxCostUsd": 0.08,
    "maxToolCalls": 3,
    "maxLatencyMs": 300000,
}

ANALYSIS_MAX_AGENT_TURNS = 5

RATE_CARD_BUDGET_SETTINGS: dict[str, Any] = {
    "maxTokens": 4096,
    "maxTotalTokens": 24000,
    "maxCostUsd": 0.10,
    "maxToolCalls": 2,
    "maxLatencyMs": 300000,
}

RATE_CARD_MAX_AGENT_TURNS = 15

IMPORT_ASSET_NAMES = (
    "Procurement Glossary",
    "Procurement Validation Contract",
    "Procurement Tool Profile",
    "Policy Placeholder",
)


def _rate_card_job_fields() -> dict[str, Any]:
    return {
        "max_agent_turns": RATE_CARD_MAX_AGENT_TURNS,
        "budget_settings": dict(RATE_CARD_BUDGET_SETTINGS),
    }


def _analysis_job_fields() -> dict[str, Any]:
    return {
        "max_agent_turns": ANALYSIS_MAX_AGENT_TURNS,
        "budget_settings": dict(ANALYSIS_BUDGET_SETTINGS),
    }


def _perm(tool_id: str, *, read_only: bool = False, require_approval: bool = False) -> dict[str, Any]:
    return {
        "toolId": tool_id,
        "enabled": True,
        "readOnly": read_only,
        "requireApproval": require_approval,
    }


REVIEW_TOOL_PERMISSIONS = [
    _perm("doc-reader", read_only=True),
    _perm("web-search", read_only=True),
    _perm("docx-generate", read_only=False),
    _perm("file-write", read_only=False),
    _perm("contract-analyzer", read_only=True),
]

ANALYSIS_TOOL_PERMISSIONS = [
    _perm("doc-reader", read_only=True),
    _perm("web-search", read_only=True),
    _perm("code-exec", read_only=False),
    _perm("calculator", read_only=True),
    _perm("file-write", read_only=False),
    _perm("spend-analyzer", read_only=True),
]

# Rate card jobs: spend-analyzer only (no doc-reader, file-write, or code-exec).
RATE_CARD_TOOL_PERMISSIONS = [
    _perm("web-search", read_only=True),
    _perm("calculator", read_only=True),
    _perm("spend-analyzer", read_only=True),
]

TOOL_PROFILE_UNION = [
    _perm("doc-reader", read_only=True),
    _perm("web-search", read_only=True),
    _perm("docx-generate", read_only=False),
    _perm("file-write", read_only=False),
    _perm("contract-analyzer", read_only=True),
    _perm("code-exec", read_only=False),
    _perm("calculator", read_only=True),
    _perm("spend-analyzer", read_only=True),
]

CONTRACT_CLAUSE_CHECKLIST = """Review each clause area and cite contract evidence:
0. If contract text or a URL is provided, call contract-analyzer first (source=text or source=url).
   For source=text, include the FULL contract from every Retrieved Context block (all chunks/sections).
   Do not omit renewal, termination, or notice sections when passing text to the tool.
1. Expiry date, contract term, and renewal timeline
2. Termination rights (for convenience, for cause, cure periods)
3. Liability cap, indemnification, and limitation of remedies
4. Data privacy, confidentiality, and cross-border transfer controls
5. AI use restrictions, training/data reuse, and model-output ownership
6. Subprocessors, flow-down obligations, and notification rights
7. Pricing, rate cards, escalation, and indexation mechanics
8. Renewal notice period, auto-renewal, and opt-out windows"""

ANALYSIS_PROCUREMENT_VALIDATION_RULES: list[dict[str, Any]] = [
    {
        "id": "proc_rate_benchmark",
        "name": "Rate benchmark variance",
        "type": "procurement",
        "checker": "rate_benchmark",
        "params": {"thresholdPercent": 15},
        "severity": "warning",
        "enabled": True,
    },
]

CONTRACT_OUTPUT_FULL = """# Executive Summary
## Contract Overview
## Key Dates and Renewal Timeline
## Clause Assessment
## Risk Register
## Commercial and Pricing Terms
## Data Privacy and AI Compliance
## Recommendations and Next Steps"""

CONTRACT_OUTPUT_EXECUTIVE = """## Decision:
## Key Risks:
## Next Step:"""

CONTRACT_OUTPUT_SCORECARD = """{
  "overallRiskScore": 0,
  "renewalUrgency": "low|medium|high|critical",
  "clauseScores": {
    "expiryAndTerm": {"score": 0, "status": "pass|watch|fail", "notes": ""},
    "termination": {"score": 0, "status": "pass|watch|fail", "notes": ""},
    "liability": {"score": 0, "status": "pass|watch|fail", "notes": ""},
    "dataPrivacy": {"score": 0, "status": "pass|watch|fail", "notes": ""},
    "aiUse": {"score": 0, "status": "pass|watch|fail", "notes": ""},
    "subprocessors": {"score": 0, "status": "pass|watch|fail", "notes": ""},
    "pricing": {"score": 0, "status": "pass|watch|fail", "notes": ""},
    "renewalNotice": {"score": 0, "status": "pass|watch|fail", "notes": ""}
  }
}"""

CAPABILITY_OUTPUT_FULL = """# Executive Summary
## Supplier Profiles
## Capability Comparison Matrix
## Differentiation Analysis
## Me-Too Risk Flags
## Evidence Gaps
## Recommendation"""

CAPABILITY_OUTPUT_EXECUTIVE = """## Decision:
## Top Differentiators:
## Me-Too Risks:
## Next Step:"""

CAPABILITY_OUTPUT_SCORECARD = """{
  "dimensionScores": {
    "supplierName": {
      "technicalCapability": 0,
      "deliveryTrackRecord": 0,
      "commercialFit": 0,
      "riskPosture": 0,
      "differentiation": 0
    }
  },
  "overallRanking": [],
  "meTooRisks": []
}"""

RATE_CARD_OUTPUT_FULL = """# Executive Summary
## Normalized Rate Card Table
## Unmapped Roles
## Variance Flags (>15% Above Benchmark)
## Spend Concentration Summary
## Recommendations"""

RATE_CARD_OUTPUT_EXECUTIVE = """## Decision:
## Top Rate Variances:
## Concentration Risk:
## Next Step:"""

RATE_CARD_OUTPUT_SCORECARD = """{
  "normalizedRows": [],
  "unmappedTitles": [],
  "varianceFlags": [],
  "spendConcentration": []
}"""

ONBOARDING_OUTPUT_FULL = """# Executive Summary
## Stakeholder Checklist
## Capability Summary
## Commercial Summary
## Risk Flags
## Required Approvals
## Open Items"""

ONBOARDING_OUTPUT_EXECUTIVE = """## Decision:
## Risk Tier:
## Open Items Summary:
## Next Step:"""

ONBOARDING_OUTPUT_SCORECARD = """{
  "goNoGo": "go|no_go|conditional",
  "riskTier": "low|medium|high|critical",
  "openItemCount": 0,
  "stakeholderCompletionPercent": 0,
  "topRisks": []
}"""


def _glossary_content() -> dict[str, Any]:
    terms = [
        ("MSA", "Master Service Agreement governing the overall commercial relationship."),
        ("SOW", "Statement of Work defining scoped deliverables, timelines, and acceptance criteria."),
        ("RFP", "Request for Proposal soliciting structured vendor bids."),
        ("RFI", "Request for Information used to qualify market capability before an RFP."),
        ("T&M", "Time and Materials pricing based on actual effort and agreed rates."),
        ("FFP", "Firm Fixed Price pricing for a defined scope at a set amount."),
        ("incumbent", "The supplier currently holding the active contract or spend category."),
        ("rate card", "Standardized schedule of role/level rates used for benchmarking and billing."),
        ("job taxonomy", "Classification scheme mapping vendor titles to normalized role and level."),
        ("subprocessor", "Third party engaged by a vendor to process customer or contract data."),
        ("auto-renewal", "Contract term that renews automatically unless notice is provided."),
        ("renewal notice period", "Minimum advance notice required to prevent renewal or terminate."),
    ]
    return {
        "terms": [
            {
                "id": term.lower().replace(" ", "_").replace("&", "and"),
                "term": term,
                "definition": definition,
                "synonyms": [],
                "required": term in {"MSA", "SOW", "rate card", "subprocessor"},
            }
            for term, definition in terms
        ]
    }


def _validation_contract_content() -> dict[str, Any]:
    return {
        "rules": [
            {
                "id": "proc_citation",
                "name": "Citation coverage",
                "type": "citation",
                "severity": "warning",
                "enabled": True,
                "description": "Material claims must include [source:] citations.",
            },
            {
                "id": "proc_format",
                "name": "Output format compliance",
                "type": "format",
                "severity": "error",
                "enabled": True,
                "description": "Output must match the job output template structure.",
            },
            {
                "id": "proc_high_risk",
                "name": "High-risk flag warning",
                "type": "custom",
                "severity": "warning",
                "enabled": True,
                "description": (
                    "Explicitly flag material risks for this workflow type. "
                    "Contract review: contractual/commercial/renewal issues. "
                    "Supplier assessment: me-too risk and unsupported claims. "
                    "Analysis: rate variance and concentration. "
                    "Procurement: onboarding blockers."
                ),
            },
        ]
    }


def _tool_profile_content() -> dict[str, Any]:
    return {
        "workflows": {
            "review": [p["toolId"] for p in REVIEW_TOOL_PERMISSIONS],
            "analysis": [p["toolId"] for p in ANALYSIS_TOOL_PERMISSIONS],
        },
        "toolPermissions": TOOL_PROFILE_UNION,
    }


def _policy_placeholder_content() -> dict[str, Any]:
    return {
        "body": (
            "REPLACE THIS PLACEHOLDER with your organization's procurement and vendor "
            "management policy. Until replaced, apply the generic mandatory clause checklist below.\n\n"
            "Mandatory clause checklist:\n"
            "- Scope of services and deliverables\n"
            "- Payment terms, invoicing, and audit rights\n"
            "- Confidentiality and data protection\n"
            "- Information security and incident notification\n"
            "- Subprocessor approval and flow-down controls\n"
            "- AI/data use restrictions and training prohibitions\n"
            "- Liability caps, indemnities, and insurance requirements\n"
            "- Termination, transition assistance, and exit obligations\n"
            "- Renewal notice, auto-renewal, and price change mechanics\n"
            "- Governing law, dispute resolution, and regulatory compliance"
        ),
    }


def _trusted_source_profile_content() -> dict[str, Any]:
    return {
        "defaultTrustLevel": "high",
        "defaultFreshness": "prefer_recent",
        "sourceTypePolicies": [
            {"sourceType": "policy", "trustLevel": "high", "maxAgeMonths": 12},
            {"sourceType": "contract", "trustLevel": "high", "maxAgeMonths": 24},
            {"sourceType": "rate_card", "trustLevel": "medium", "maxAgeMonths": 6},
        ],
    }


def _contract_retrieval_config(policy_asset_id: str | None) -> dict[str, Any]:
    """Pull more contract KB chunks; preserve section-specific terms (e.g. RENEWAL NOTICE)."""
    config = _base_retrieval_config(policy_asset_id)
    config["maxDocuments"] = 24
    config["queryRewriting"] = False
    return config


def _base_retrieval_config(policy_asset_id: str | None) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    if policy_asset_id:
        sources.append(
            {
                "id": "customer_policy",
                "type": "asset",
                "label": "Customer Policy Placeholder",
                "value": policy_asset_id,
            }
        )
    return {
        "maxDocuments": 12,
        "hybridRetrieval": True,
        "queryRewriting": True,
        "reranking": True,
        "knowledgeSources": sources,
    }


def _rate_card_retrieval_config(policy_asset_id: str | None) -> dict[str, Any]:
    """Pull more KB chunks; avoid query rewrite dropping vendor-specific terms."""
    config = _base_retrieval_config(policy_asset_id)
    config["maxDocuments"] = 24
    config["queryRewriting"] = False
    return config


def _contract_role() -> str:
    return (
        "You are a senior procurement contract analyst. Review supplier agreements for renewal "
        "risk, commercial exposure, and compliance gaps. Cite evidence from contract text and "
        "trusted sources. Escalate high-risk clauses clearly."
    )


def _capability_role() -> str:
    return (
        "You are a strategic sourcing analyst building supplier capability comparisons. "
        "Emphasize differentiation, flag me-too positioning, and require evidence for every "
        "material capability claim."
    )


def _rate_card_role() -> str:
    return (
        "You are a procurement rate-benchmarking analyst. Use rate card data from retrieved "
        "context (and the user request), build one consolidated CSV with vendor/title/level/rate, "
        "and call spend-analyzer exactly once. Do not use doc-reader, file-write, or code-exec."
    )


def _onboarding_role() -> str:
    return (
        "You are a supplier onboarding lead coordinating stakeholders, commercial review, and "
        "risk acceptance. Produce actionable checklists and flag blockers before go-live."
    )


RATE_CARD_STABLE_INSTRUCTIONS = (
    "Normalize the supplied rate card data using the job taxonomy.\n"
    "- Use rate card data from EVERY block in Retrieved Context (all vendors, all roles)\n"
    "- Do not stop after the first source block — scan all [source:...] sections\n"
    "- Build a CSV string with columns: vendor, title, level, rate\n"
    "- Every row MUST include vendor, title, and a numeric rate\n"
    "- Call spend-analyzer EXACTLY ONCE with the full consolidated CSV\n"
    "- Do NOT use doc-reader or file-write before calling spend-analyzer\n"
    "- Do NOT call spend-analyzer more than once\n"
    "- Do NOT use code-exec for normalization\n"
    "- Pass taxonomy entries with role, level, and explicit titles "
    '(e.g. titles: ["Senior Cloud Engineer"] for Engineering/Senior)\n'
    "- Copy the tool's full normalizedRows, unmappedTitles, varianceFlags, and "
    "spendConcentration into the final output without dropping rows\n"
    "- Flag unmapped titles and rates more than 15% above the peer benchmark"
)

_RATE_CARD_JOB_NAMES = (
    "Rate Card Normalization",
    "Rate Card Normalization (Executive)",
    "Rate Card Normalization (Scorecard)",
)


def _job_definitions() -> list[dict[str, Any]]:
    capability_instructions = (
        "Build a supplier capability matrix focused on differentiation, not feature parity.\n"
        "- Require cited evidence for every material capability claim\n"
        "- Flag me-too risk when suppliers lack distinct strengths\n"
        "- Compare delivery, technical depth, commercial fit, and risk posture\n"
        "- Highlight evidence gaps that block a confident recommendation"
    )
    rate_card_instructions = RATE_CARD_STABLE_INSTRUCTIONS
    onboarding_instructions = (
        "Produce a supplier onboarding package covering stakeholders, capability validation, "
        "commercial terms, risk acceptance, and open items.\n"
        "- Confirm required internal approvals and accountable owners\n"
        "- Summarize capability and commercial posture from submitted materials\n"
        "- Flag compliance, security, and continuity risks before onboarding"
    )

    return [
        {
            "name": "Contract Review & Renewal",
            "workflow_type": "contract_review",
            "goal": "Review an active supplier contract for renewal risk and produce a structured assessment.",
            "role_configuration": _contract_role(),
            "stable_instructions": CONTRACT_CLAUSE_CHECKLIST,
            "output_template": CONTRACT_OUTPUT_FULL,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
            "validation_rules": [
                {
                    "id": "proc_mandatory_clauses",
                    "name": "Mandatory clause coverage",
                    "type": "procurement",
                    "checker": "mandatory_clause",
                    "severity": "blocking",
                    "enabled": True,
                    "params": {
                        "requiredClauseIds": [
                            "liability_cap",
                            "subprocessors",
                            "termination",
                            "pricing",
                            "data_protection",
                            "ai_use_restrictions",
                        ],
                    },
                },
            ],
        },
        {
            "name": "Contract Review & Renewal (Executive)",
            "workflow_type": "contract_review",
            "goal": "Deliver a concise executive decision brief on contract renewal risk.",
            "role_configuration": _contract_role(),
            "stable_instructions": CONTRACT_CLAUSE_CHECKLIST,
            "output_template": CONTRACT_OUTPUT_EXECUTIVE,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
        },
        {
            "name": "Contract Review & Renewal (Scorecard)",
            "workflow_type": "contract_review",
            "goal": "Score contract renewal risk and clause health as structured JSON.",
            "role_configuration": _contract_role(),
            "stable_instructions": CONTRACT_CLAUSE_CHECKLIST,
            "output_template": CONTRACT_OUTPUT_SCORECARD,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
        },
        {
            "name": "Supplier Capability Matrix",
            "workflow_type": "supplier_assessment",
            "goal": "Compare supplier capabilities with emphasis on differentiation and evidence quality.",
            "role_configuration": _capability_role(),
            "stable_instructions": capability_instructions,
            "output_template": CAPABILITY_OUTPUT_FULL,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
        },
        {
            "name": "Supplier Capability Matrix (Executive)",
            "workflow_type": "supplier_assessment",
            "goal": "Deliver a concise executive supplier selection brief.",
            "role_configuration": _capability_role(),
            "stable_instructions": capability_instructions,
            "output_template": CAPABILITY_OUTPUT_EXECUTIVE,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
        },
        {
            "name": "Supplier Capability Matrix (Scorecard)",
            "workflow_type": "supplier_assessment",
            "goal": "Return structured supplier dimension scores as JSON.",
            "role_configuration": _capability_role(),
            "stable_instructions": capability_instructions,
            "output_template": CAPABILITY_OUTPUT_SCORECARD,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
        },
        {
            "name": "Rate Card Normalization",
            "workflow_type": "analysis",
            "goal": "Normalize vendor rate cards, flag variance, and summarize spend concentration.",
            "role_configuration": _rate_card_role(),
            "stable_instructions": rate_card_instructions,
            "output_template": RATE_CARD_OUTPUT_FULL,
            "tool_permissions": RATE_CARD_TOOL_PERMISSIONS,
            **_rate_card_job_fields(),
        },
        {
            "name": "Rate Card Normalization (Executive)",
            "workflow_type": "analysis",
            "goal": "Deliver a concise executive brief on rate card normalization findings.",
            "role_configuration": _rate_card_role(),
            "stable_instructions": rate_card_instructions,
            "output_template": RATE_CARD_OUTPUT_EXECUTIVE,
            "tool_permissions": RATE_CARD_TOOL_PERMISSIONS,
            **_rate_card_job_fields(),
        },
        {
            "name": "Rate Card Normalization (Scorecard)",
            "workflow_type": "analysis",
            "goal": "Return spend-analyzer structured JSON for normalized rate card analysis.",
            "role_configuration": _rate_card_role(),
            "stable_instructions": rate_card_instructions,
            "output_template": RATE_CARD_OUTPUT_SCORECARD,
            "tool_permissions": RATE_CARD_TOOL_PERMISSIONS,
            **_rate_card_job_fields(),
        },
        {
            "name": "Supplier Onboarding Checklist",
            "workflow_type": "procurement",
            "goal": "Build a stakeholder onboarding checklist with capability, commercial, and risk summaries.",
            "role_configuration": _onboarding_role(),
            "stable_instructions": onboarding_instructions,
            "output_template": ONBOARDING_OUTPUT_FULL,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
        },
        {
            "name": "Supplier Onboarding Checklist (Executive)",
            "workflow_type": "procurement",
            "goal": "Deliver a concise executive onboarding go/no-go brief.",
            "role_configuration": _onboarding_role(),
            "stable_instructions": onboarding_instructions,
            "output_template": ONBOARDING_OUTPUT_EXECUTIVE,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
        },
        {
            "name": "Supplier Onboarding Checklist (Scorecard)",
            "workflow_type": "procurement",
            "goal": "Return structured onboarding scorecard JSON.",
            "role_configuration": _onboarding_role(),
            "stable_instructions": onboarding_instructions,
            "output_template": ONBOARDING_OUTPUT_SCORECARD,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
        },
    ]


def _find_asset(db, name: str) -> ContextAssetModel | None:
    return (
        db.query(ContextAssetModel)
        .filter(ContextAssetModel.owner == SYSTEM_OWNER, ContextAssetModel.name == name)
        .first()
    )


def _find_job(db, name: str) -> ContextJobModel | None:
    return (
        db.query(ContextJobModel)
        .filter(ContextJobModel.owner == SYSTEM_OWNER, ContextJobModel.name == name)
        .first()
    )


def _seed_assets(db) -> tuple[list[str], list[str]]:
    created: list[str] = []
    skipped: list[str] = []

    asset_specs = [
        ("Procurement Glossary", "glossary", "Shared procurement terminology.", _glossary_content()),
        (
            "Procurement Validation Contract",
            "validation_contract",
            "Standard procurement validation rules.",
            _validation_contract_content(),
        ),
        (
            "Procurement Tool Profile",
            "tool_profile",
            "Tool sets for review and analysis procurement workflows.",
            _tool_profile_content(),
        ),
        (
            "Policy Placeholder",
            "policy",
            "Customer policy placeholder with generic mandatory clause checklist.",
            _policy_placeholder_content(),
        ),
        (
            "Trusted Source Profile",
            "source_profile",
            "Trust and freshness defaults for policy, contract, and rate card sources.",
            _trusted_source_profile_content(),
        ),
    ]

    for name, asset_type, description, content in asset_specs:
        if _find_asset(db, name):
            skipped.append(name)
            continue
        db.add(
            ContextAssetModel(
                name=name,
                type=asset_type,
                description=description,
                content=content,
                owner=SYSTEM_OWNER,
                status="active",
                approval_status="approved",
            )
        )
        created.append(name)

    if created:
        db.commit()
    return created, skipped


def _merge_validation_rules(job: ContextJobModel, rules: list[dict[str, Any]]) -> None:
    existing = list(job.validation_rules or [])
    existing_ids = {str(r.get("id")) for r in existing if isinstance(r, dict) and r.get("id")}
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_id = str(rule.get("id") or "")
        if rule_id and rule_id in existing_ids:
            continue
        existing.append(rule)
        if rule_id:
            existing_ids.add(rule_id)
    job.validation_rules = existing


def _apply_imports(
    job: ContextJobModel,
    assets_by_name: dict[str, ContextAssetModel],
    workflow_tools: list[dict[str, Any]],
    job_validation_rules: list[dict[str, Any]] | None = None,
) -> list[str]:
    summaries: list[str] = []
    for asset_name in IMPORT_ASSET_NAMES:
        asset = assets_by_name.get(asset_name)
        if not asset:
            continue
        summary = import_asset_into_job(job, asset)
        summaries.append(f"{asset_name} -> {summary.get('importedFields', [])}")
    workflow = (job.workflow_type or "").lower()
    if job_validation_rules:
        _merge_validation_rules(job, job_validation_rules)
    elif workflow == "analysis":
        _merge_validation_rules(job, ANALYSIS_PROCUREMENT_VALIDATION_RULES)
    job.tool_permissions = workflow_tools
    return summaries


def _seed_jobs(db, assets_by_name: dict[str, ContextAssetModel]) -> tuple[list[str], list[str]]:
    created: list[str] = []
    skipped: list[str] = []
    policy_asset = assets_by_name.get("Policy Placeholder")
    policy_asset_id = str(policy_asset.id) if policy_asset else None

    for job_def in _job_definitions():
        name = job_def["name"]
        if _find_job(db, name):
            skipped.append(name)
            continue

        if name in _RATE_CARD_JOB_NAMES:
            retrieval_config = _rate_card_retrieval_config(policy_asset_id)
        elif job_def["workflow_type"] == "contract_review":
            retrieval_config = _contract_retrieval_config(policy_asset_id)
        else:
            retrieval_config = _base_retrieval_config(policy_asset_id)

        workflow_tools = job_def["tool_permissions"]
        job = ContextJobModel(
            name=name,
            description=f"System procurement template: {name}",
            status="published",
            goal=job_def["goal"],
            workflow_type=job_def["workflow_type"],
            role_configuration=job_def["role_configuration"],
            stable_instructions=job_def["stable_instructions"],
            output_template=job_def["output_template"],
            tool_permissions=workflow_tools,
            retrieval_config=retrieval_config,
            retrieval_mode="jet_kb",
            execution_provider="openai",
            execution_model="gpt-4o-mini",
            execution_mode="provider_multi_agent",
            max_agent_turns=job_def.get("max_agent_turns", 10),
            budget_settings=job_def.get("budget_settings"),
            owner=SYSTEM_OWNER,
        )
        db.add(job)
        db.flush()

        import_summaries = _apply_imports(
            job,
            assets_by_name,
            workflow_tools,
            job_validation_rules=job_def.get("validation_rules"),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        created.append(f"{name} (imports: {'; '.join(import_summaries)})")

    return created, skipped


_EXECUTIVE_TEMPLATE_PATCHES: dict[str, str] = {
    "Contract Review & Renewal (Executive)": CONTRACT_OUTPUT_EXECUTIVE,
    "Supplier Capability Matrix (Executive)": CAPABILITY_OUTPUT_EXECUTIVE,
    "Rate Card Normalization (Executive)": RATE_CARD_OUTPUT_EXECUTIVE,
    "Supplier Onboarding Checklist (Executive)": ONBOARDING_OUTPUT_EXECUTIVE,
}


def _patch_executive_output_templates(db: Session) -> list[str]:
    """Update legacy executive templates that embedded format instructions in output_template."""
    updated: list[str] = []
    for name, template in _EXECUTIVE_TEMPLATE_PATCHES.items():
        job = _find_job(db, name)
        if not job:
            continue
        current = (job.output_template or "").strip()
        if current == template.strip():
            continue
        if "produce a concise executive" in current.lower() or not current.startswith("##"):
            job.output_template = template
            db.add(job)
            updated.append(name)
    if updated:
        db.commit()
    return updated


def _tool_permission_ids(perms: list[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for perm in perms:
        if not isinstance(perm, dict):
            continue
        tool_id = perm.get("toolId") or perm.get("tool_id")
        if tool_id and perm.get("enabled", True):
            ids.add(str(tool_id))
    return ids


def _patch_rate_card_templates(db: Session) -> list[str]:
    """Sync rate card system templates in DB (instructions, tools, budget, turns)."""
    updated: list[str] = []
    target_instructions = RATE_CARD_STABLE_INSTRUCTIONS.strip()
    target_role = _rate_card_role().strip()
    target_tool_ids = _tool_permission_ids(RATE_CARD_TOOL_PERMISSIONS)
    target_budget = dict(RATE_CARD_BUDGET_SETTINGS)
    policy_asset = (
        db.query(ContextAssetModel)
        .filter(
            ContextAssetModel.owner == SYSTEM_OWNER,
            ContextAssetModel.name == "Policy Placeholder",
        )
        .first()
    )
    policy_asset_id = str(policy_asset.id) if policy_asset else None
    target_retrieval = _rate_card_retrieval_config(policy_asset_id)

    for name in _RATE_CARD_JOB_NAMES:
        job = _find_job(db, name)
        if not job:
            continue

        changed = False
        if (job.stable_instructions or "").strip() != target_instructions:
            job.stable_instructions = RATE_CARD_STABLE_INSTRUCTIONS
            changed = True
        if (job.role_configuration or "").strip() != target_role:
            job.role_configuration = _rate_card_role()
            changed = True
        if int(job.max_agent_turns or 0) != RATE_CARD_MAX_AGENT_TURNS:
            job.max_agent_turns = RATE_CARD_MAX_AGENT_TURNS
            changed = True
        if dict(job.budget_settings or {}) != target_budget:
            job.budget_settings = target_budget
            changed = True

        current_rc = dict(job.retrieval_config or {})
        if (
            int(current_rc.get("maxDocuments") or 0) != target_retrieval["maxDocuments"]
            or bool(current_rc.get("queryRewriting")) != target_retrieval["queryRewriting"]
        ):
            merged_rc = {**current_rc, **target_retrieval}
            job.retrieval_config = merged_rc
            changed = True

        current_tool_ids = _tool_permission_ids(list(job.tool_permissions or []))
        disallowed = current_tool_ids & {"code-exec", "doc-reader", "file-write"}
        if current_tool_ids != target_tool_ids or disallowed:
            job.tool_permissions = [dict(p) for p in RATE_CARD_TOOL_PERMISSIONS]
            changed = True

        if changed:
            db.add(job)
            updated.append(name)

    if updated:
        db.commit()
    return updated


def _patch_procurement_validation_and_retrieval(db: Session) -> list[str]:
    """Wire procurement validation rules and contract retrieval settings on system templates."""
    updated: list[str] = []
    policy_asset = _find_asset(db, "Policy Placeholder")
    policy_asset_id = str(policy_asset.id) if policy_asset else None
    contract_retrieval = _contract_retrieval_config(policy_asset_id)
    target_instructions = CONTRACT_CLAUSE_CHECKLIST.strip()
    contract_review_rules = next(
        (
            list(job_def.get("validation_rules") or [])
            for job_def in _job_definitions()
            if job_def["name"] == "Contract Review & Renewal"
        ),
        [],
    )

    jobs = (
        db.query(ContextJobModel)
        .filter(ContextJobModel.owner == SYSTEM_OWNER)
        .all()
    )
    for job in jobs:
        workflow = (job.workflow_type or "").lower()
        changed = False

        if workflow == "contract_review":
            if (job.stable_instructions or "").strip() != target_instructions:
                job.stable_instructions = CONTRACT_CLAUSE_CHECKLIST
                changed = True
            current_rc = dict(job.retrieval_config or {})
            if current_rc.get("maxDocuments") != 24 or current_rc.get("queryRewriting") is not False:
                job.retrieval_config = {**current_rc, **contract_retrieval}
                changed = True
            if job.name == "Contract Review & Renewal" and contract_review_rules:
                before = len(job.validation_rules or [])
                _merge_validation_rules(job, contract_review_rules)
                if len(job.validation_rules or []) != before:
                    changed = True

        elif workflow == "analysis":
            before = len(job.validation_rules or [])
            _merge_validation_rules(job, ANALYSIS_PROCUREMENT_VALIDATION_RULES)
            if len(job.validation_rules or []) != before:
                changed = True

        if changed:
            db.add(job)
            updated.append(job.name)

    if updated:
        db.commit()
    return updated


def _system_template_job_names() -> set[str]:
    return {job_def["name"] for job_def in _job_definitions()}


def _job_has_validation_contract_asset(job: ContextJobModel) -> bool:
    """True when a __system__ template job has rules from the validation contract asset."""
    if (job.owner or "") != SYSTEM_OWNER:
        return False
    if (job.name or "") not in _system_template_job_names():
        return False
    job_rule_ids = {
        str(rule.get("id") or "")
        for rule in (job.validation_rules or [])
        if isinstance(rule, dict) and rule.get("id")
    }
    return bool(VALIDATION_CONTRACT_RULE_IDS & job_rule_ids)


def _strip_validation_contract_rules(job: ContextJobModel) -> None:
    job.validation_rules = [
        rule
        for rule in (job.validation_rules or [])
        if not (
            isinstance(rule, dict)
            and str(rule.get("id") or "") in VALIDATION_CONTRACT_RULE_IDS
        )
    ]


def patch_procurement_validation_contract(db: Session) -> tuple[list[str], list[str]]:
    """
    Update the Procurement Validation Contract asset and re-import it into system
    template jobs that already have this asset attached.
    """
    asset = _find_asset(db, VALIDATION_CONTRACT_ASSET_NAME)
    if not asset:
        return [], []

    asset.content = _validation_contract_content()
    db.add(asset)

    reimported_jobs: list[str] = []
    jobs = (
        db.query(ContextJobModel)
        .filter(ContextJobModel.owner == SYSTEM_OWNER)
        .all()
    )
    for job in jobs:
        if not _job_has_validation_contract_asset(job):
            continue
        _strip_validation_contract_rules(job)
        import_asset_into_job(job, asset)
        if job.name == "Contract Review & Renewal":
            contract_review_rules = next(
                (
                    list(job_def.get("validation_rules") or [])
                    for job_def in _job_definitions()
                    if job_def["name"] == "Contract Review & Renewal"
                ),
                [],
            )
            if contract_review_rules:
                _merge_validation_rules(job, contract_review_rules)
        db.add(job)
        reimported_jobs.append(job.name)

    db.commit()
    return [VALIDATION_CONTRACT_ASSET_NAME], reimported_jobs


_CHAIN_PATCH_SPECS: list[dict[str, Any]] = [
    {
        "name": "Contract Review & Renewal",
        "workflow_type": "contract_review",
        "child_name": "Supplier Capability Matrix",
        "user_request": (
            "Assess supplier capabilities based on this contract "
            "review findings: {primaryResult}"
        ),
    },
    {
        "name": "Supplier Capability Matrix",
        "workflow_type": "supplier_assessment",
        "child_name": "Supplier Onboarding Checklist",
        "user_request": (
            "Produce a supplier onboarding checklist based on "
            "this capability assessment: {primaryResult}"
        ),
    },
]


def patch_procurement_chain_configs(db: Session) -> list[str]:
    """Patch chain_config onto standard procurement system templates (idempotent)."""
    child_names = {spec["child_name"] for spec in _CHAIN_PATCH_SPECS}
    for child_name in child_names:
        if not _find_job(db, child_name):
            raise ValueError(f"System template not found: {child_name}")

    updated: list[str] = []
    for spec in _CHAIN_PATCH_SPECS:
        job = _find_job(db, spec["name"])
        if not job:
            raise ValueError(f"System template not found: {spec['name']}")
        if (job.workflow_type or "") != spec["workflow_type"]:
            raise ValueError(
                f"Template {spec['name']!r} has workflow_type={job.workflow_type!r}, "
                f"expected {spec['workflow_type']!r}"
            )
        if isinstance(job.chain_config, dict) and job.chain_config:
            continue

        child = _find_job(db, spec["child_name"])
        if not child:
            raise ValueError(f"System template not found: {spec['child_name']}")

        job.chain_config = {
            "triggerOnSuccess": True,
            "childJobId": str(child.id),
            "inputMapping": {"userRequest": spec["user_request"]},
            "maxDepth": 3,
        }
        db.add(job)
        updated.append(job.name)

    if updated:
        db.commit()
    return updated


def seed_procurement_templates(db: Session) -> None:
    """Ensure shared procurement assets and system job templates exist."""
    created_assets, skipped_assets = _seed_assets(db)

    assets_by_name = {
        name: asset
        for name in ASSET_NAMES
        if (asset := _find_asset(db, name)) is not None
    }

    created_jobs, skipped_jobs = _seed_jobs(db, assets_by_name)
    patched_jobs = _patch_executive_output_templates(db)
    patched_rate_card = _patch_rate_card_templates(db)
    patched_procurement = _patch_procurement_validation_and_retrieval(db)

    if created_assets:
        logger.info("Created procurement assets: %s", ", ".join(created_assets))
    if skipped_assets:
        logger.debug("Skipped existing procurement assets: %s", ", ".join(skipped_assets))
    if created_jobs:
        logger.info("Created procurement templates: %s", ", ".join(created_jobs))
    if skipped_jobs:
        logger.debug("Skipped existing procurement templates: %s", ", ".join(skipped_jobs))
    if patched_jobs:
        logger.info("Patched executive output templates: %s", ", ".join(patched_jobs))
    if patched_rate_card:
        logger.info("Patched rate card templates: %s", ", ".join(patched_rate_card))
    if patched_procurement:
        logger.info(
            "Patched procurement validation/retrieval: %s",
            ", ".join(patched_procurement),
        )
