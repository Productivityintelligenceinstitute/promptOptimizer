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
    "Procurement Relationship Patterns",
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

# Capability matrix: comparison + evidence from KB / request (no web-search —
# public search invents wrong-entity facts that look cited).
CAPABILITY_TOOL_PERMISSIONS = [
    _perm("doc-reader", read_only=True),
    _perm("docx-generate", read_only=False),
    _perm("file-write", read_only=False),
]

# Onboarding checklist: stakeholder package, not contract analysis.
ONBOARDING_TOOL_PERMISSIONS = [
    _perm("doc-reader", read_only=True),
    _perm("docx-generate", read_only=False),
    _perm("file-write", read_only=False),
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
1. State an explicit renew / renegotiate / exit Decision before deep clause narrative
   (calendar reminders alone are not a decision).
2. Expiry date, contract term, and renewal timeline
3. Termination rights (for convenience, for cause, cure periods)
4. Liability cap, indemnification, and limitation of remedies
5. Data privacy, confidentiality, and cross-border transfer controls
6. AI use restrictions, training/data reuse, and model-output ownership
7. Subprocessors, flow-down obligations, and notification rights
8. Pricing, rate cards, escalation, and indexation mechanics
9. Renewal notice period, auto-renewal, and opt-out windows
10. After numbered amendment-ready recommendations, add ## Intent Behind the Edits.
    For EACH material recommendation, write approximately two thorough paragraphs (not a 2–4
    sentence blurb): (1) Buyer — why the current clause is a problem (policy, cash flow, ops,
    legal risk) and what the edit is trying to achieve; (2) Seller — how they can accept or
    counter without reopening the whole deal, including the commercial trade-off. Do not invent
    extra recommendations in this section — only explain the ones already listed."""

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

SUPPLIER_ASSESSMENT_RISK_RULES: list[dict[str, Any]] = [
    {
        "id": "proc_risk_threshold_supplier",
        "name": "Vendor risk tier threshold",
        "type": "procurement",
        "checker": "risk_threshold",
        "params": {"maxRiskTier": "high"},
        "severity": "warning",
        "enabled": True,
    },
]

ONBOARDING_RISK_RULES: list[dict[str, Any]] = [
    {
        "id": "proc_risk_threshold_onboarding",
        "name": "Onboarding risk tier threshold",
        "type": "procurement",
        "checker": "risk_threshold",
        "params": {"maxRiskTier": "medium"},
        "severity": "warning",
        "enabled": True,
    },
]

LEGACY_SPECIALTY_RULE_IDS = frozenset(
    {
        "proc_risk_threshold",
        "proc_rate_benchmark",
        "proc_mandatory_clauses",
        "proc_risk_threshold_supplier",
        "proc_risk_threshold_onboarding",
    }
)

CONTRACT_MANDATORY_CLAUSE_RULE: dict[str, Any] = {
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
}

CONTRACT_OUTPUT_FULL = """# Executive Summary
## Decision: Renew | Renegotiate | Exit
## Contract Overview
## Renewal Timeline Assessment
## Clause Analysis
## Vendor Risk Signals
## Commercial and Pricing Terms
## Data Privacy and AI Compliance
## Policy Alignment
## Evidence Gaps
## Recommended Next Actions
## Intent Behind the Edits"""

CONTRACT_OUTPUT_EXECUTIVE = """## Decision:
## Key Risks:
## Next Step:
## Negotiation Intent:"""

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
  },
  "evidenceGaps": [],
  "editIntent": [
    {
      "clause": "",
      "recommendation": "",
      "buyerIntent": "",
      "sellerTalkingPoint": ""
    }
  ]
}"""

CAPABILITY_OUTPUT_FULL = """# Executive Summary
## Comparison Purpose
## Evaluation Criteria (Weighted)
## Capability Comparison Matrix
## Differentiation Analysis
## Perception vs Evidence
## Me-Too Risk Flags
## Recommendation Scenarios
## Evidence Gaps"""

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
  "meTooRisks": [],
  "evidenceGaps": []
}"""

RATE_CARD_OUTPUT_FULL = """# Executive Summary
## Taxonomy Mapping Summary
## Normalized Rate Card Table
## Unmapped Roles
## Variance Flags (>15% Above Benchmark)
## Spend Concentration Insight
## Challenge List
## Evidence Gaps"""

RATE_CARD_OUTPUT_EXECUTIVE = """## Decision:
## Top Rate Variances:
## Concentration Risk:
## Next Step:"""

RATE_CARD_OUTPUT_SCORECARD = """{
  "normalizedRows": [],
  "unmappedTitles": [],
  "varianceFlags": [],
  "spendConcentration": [],
  "challengeList": []
}"""

ONBOARDING_OUTPUT_FULL = """# Executive Summary
## Stakeholder Checklist
## Capability Summary
## Commercial Summary
## Risk Flags
## Required Approvals
## Open Items
## Go / No-Go Recommendation"""

ONBOARDING_OUTPUT_EXECUTIVE = """## Decision:
## Risk Tier:
## Open Items Summary:
## Next Step:"""

ONBOARDING_OUTPUT_SCORECARD = """{
  "goNoGo": "go|no_go|conditional",
  "riskTier": "low|medium|high|critical",
  "openItemCount": 0,
  "stakeholderCompletionPercent": 0,
  "topRisks": [],
  "requiredApprovals": []
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
            "contract_review": [p["toolId"] for p in REVIEW_TOOL_PERMISSIONS],
            "supplier_assessment": [p["toolId"] for p in CAPABILITY_TOOL_PERMISSIONS],
            "procurement": [p["toolId"] for p in ONBOARDING_TOOL_PERMISSIONS],
            "analysis": [p["toolId"] for p in RATE_CARD_TOOL_PERMISSIONS],
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


def _relationship_pattern_content() -> dict[str, Any]:
    return {
        "patterns": [
            {
                "id": "vendor_holds_msa",
                "fromTerm": "vendor",
                "relation": "holds",
                "toTerm": "MSA",
            },
            {
                "id": "msa_governs_sow",
                "fromTerm": "MSA",
                "relation": "governs",
                "toTerm": "SOW",
            },
            {
                "id": "rate_card_prices_role",
                "fromTerm": "rate card",
                "relation": "prices",
                "toTerm": "job taxonomy",
            },
            {
                "id": "vendor_engages_subprocessor",
                "fromTerm": "vendor",
                "relation": "engages",
                "toTerm": "subprocessor",
            },
            {
                "id": "msa_auto_renews_unless",
                "fromTerm": "MSA",
                "relation": "auto_renews_unless",
                "toTerm": "renewal notice period",
            },
        ]
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


def _contract_role_full() -> str:
    return (
        "You are a senior procurement contract analyst preparing an audit-ready renewal pack. "
        "Review supplier agreements for renewal risk, commercial exposure, and compliance gaps. "
        "In the Decision section, state an explicit renew / renegotiate / exit recommendation "
        "with a one-line rationale before detailed clause analysis. "
        "Cite evidence from contract text and trusted sources. Escalate high-risk clauses clearly "
        "with clause-level findings and actionable next steps. After numbered recommendations, "
        "write approximately two thorough paragraphs of intent for each material edit so Buyer "
        "and Seller can discuss it."
    )


def _contract_role_executive() -> str:
    return (
        "You are a procurement advisor briefing an executive decision-maker. "
        "Lead with a clear renew / renegotiate / exit decision, then the top risks and one next step. "
        "Keep the brief concise (target ≤400 words). Do not dump full clause tables—surface only "
        "decision-critical findings with evidence references. Close with Negotiation Intent: "
        "approximately two thorough paragraphs per material edit so Buyer and Seller can talk "
        "through why the change exists and how to accept or counter it. Negotiation Intent does "
        "not count against the 400-word brief cap."
    )


def _contract_role_scorecard() -> str:
    return (
        "You are a procurement risk scorer for a review committee. "
        "Return only structured JSON matching the output template. Score clause health and renewal "
        "urgency with short notes; prefer measurable status values over narrative prose. Fill "
        "editIntent for each material recommendation with approximately two thorough paragraphs: "
        "buyerIntent (paragraph 1) and sellerTalkingPoint (paragraph 2)."
    )


def _capability_role_full() -> str:
    return (
        "You are a strategic sourcing analyst building a defensible supplier capability comparison. "
        "Emphasize differentiation over feature parity, flag me-too positioning, weight evaluation "
        "criteria, and separate perception from cited evidence for every material claim. "
        "Use documented risk tiers from profile text and [meta:riskTier=...] in risk posture cells; "
        "never mark those tiers as missing when present."
    )


def _capability_role_executive() -> str:
    return (
        "You are a sourcing advisor briefing leadership on supplier selection. "
        "Lead with a recommendation, top differentiators, me-too risks, and one next step. "
        "Keep the brief concise (target ≤400 words) and evidence-backed. "
        "State documented risk tiers and category fit when present in Retrieved Context. "
        "Only list evidence gaps for facts truly absent from Retrieved Context."
    )


def _capability_role_scorecard() -> str:
    return (
        "You are a supplier scorecard analyst. Return only structured JSON matching the output "
        "template with dimension scores (prefer integers 1-5), ranking, me-too risks, and evidence gaps. "
        "All dimension scores are quality/fitness scores where HIGHER is better. "
        "riskPosture is NOT a risk severity number: safer vendors must score higher. "
        "When profile risk tiers / [meta:riskTier=...] is present, map approximately: "
        "low → 4 or 5, medium → 2 or 3, high/critical → 1. "
        "Never give a low-risk vendor a lower riskPosture than a medium/high-risk vendor. "
        "Weight technicalCapability and overallRanking by fit to the requested category/use case "
        "in the User request, not only incumbent spend or MSA linkage. "
        "evidenceGaps may only list facts missing from Retrieved Context. Never mark as missing: "
        "risk tier, capability/category tags, certifications named in profiles, MSA/contract status, "
        "annual spend, or renewal complexity when those values appear in Retrieved Context. "
        "meTooRisks must not deny a supplier's documented distinct strengths "
        "(certifications, category specialization, residency packaging)."
    )


def _rate_card_role_full() -> str:
    return (
        "You are a procurement rate-benchmarking analyst producing an audit-ready normalization pack. "
        "Use rate card data from retrieved context (and the user request), build one consolidated CSV "
        "with vendor/title/level/rate, and call spend-analyzer exactly once. Do not use doc-reader, "
        "file-write, or code-exec."
    )


def _rate_card_role_executive() -> str:
    return (
        "You are a procurement rate advisor briefing an executive on pricing risk. "
        "After spend-analyzer runs, lead with decision, top variances, concentration risk, and one "
        "next step in ≤400 words. Do not use doc-reader, file-write, or code-exec."
    )


def _rate_card_role_scorecard() -> str:
    return (
        "You are a rate-card scorecard producer. Call spend-analyzer exactly once and return only "
        "structured JSON matching the output template. Do not use doc-reader, file-write, or code-exec."
    )


def _onboarding_role_full() -> str:
    return (
        "You are a supplier onboarding lead coordinating stakeholders, commercial review, and risk "
        "acceptance. Produce an actionable checklist with owners, approvals, open items, and a clear "
        "go / no-go / conditional recommendation before go-live."
    )


def _onboarding_role_executive() -> str:
    return (
        "You are an onboarding advisor briefing leadership on go / no-go. "
        "Lead with decision, risk tier, open-items summary, and one next step in ≤400 words."
    )


def _onboarding_role_scorecard() -> str:
    return (
        "You are an onboarding scorecard producer. Return only structured JSON matching the output "
        "template with go/no-go, risk tier, completion metrics, risks, and required approvals."
    )


# Backward-compatible aliases used by legacy patches.
def _contract_role() -> str:
    return _contract_role_full()


def _capability_role() -> str:
    return _capability_role_full()


def _rate_card_role() -> str:
    return _rate_card_role_full()


def _onboarding_role() -> str:
    return _onboarding_role_full()


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

CAPABILITY_STABLE_INSTRUCTIONS = (
    "Build a supplier capability matrix focused on differentiation, not feature parity.\n"
    "- Define weighted evaluation criteria before scoring\n"
    "- Require cited evidence for every material capability claim\n"
    "- Separate marketing perception from verified evidence\n"
    "- Flag me-too risk when suppliers lack distinct strengths\n"
    "- Compare delivery, technical depth, commercial fit, and risk posture\n"
    "- Offer recommendation scenarios (award / shortlist / eliminate) with evidence gaps that "
    "block a confident decision\n"
    "- Prefer vendor profiles, RFP responses, and capability evidence in Retrieved Context "
    "over contract clause extraction\n"
    "- Grounding (mandatory): use ONLY facts present in Retrieved Context or the User request. "
    "Do NOT invent uptime %, SLA breaches, data breaches, certifications, pricing flexibility, "
    "or risk incidents.\n"
    "- If a fact is missing, write 'Not available in retrieved vector context' (or Evidence Gaps) — "
    "never invent filler to complete a matrix cell.\n"
    "- A [source:…] citation does not justify adding details that are not in that source.\n"
    "- Preserve profile risk tiers and category tags when present (including [meta:riskTier=...] "
    "and 'Risk tier:' lines); do not invert or invent them.\n"
    "- Evidence Gaps rules: list ONLY facts absent from Retrieved Context. Do NOT claim "
    "risk posture/tier, capability tags/categories, certifications, contract/MSA status, spend, or "
    "renewal complexity are missing when those fields appear in retrieved profiles or meta lines.\n"
    "- Ranking / technical fit: weigh fit to the User request category or use case; do not rank "
    "solely by incumbent spend or linked MSA when another supplier better matches the requested category.\n"
    "- Me-too flags: do not deny distinct strengths that are explicitly documented in Retrieved Context "
    "(for example certifications, category specialization, or residency packaging).\n"
    "- Scorecard riskPosture: quality score where HIGHER is better (safer). When profile risk "
    "tiers / [meta:riskTier=...] is present, map low→4-5, medium→2-3, high→1. Never invert."
)

ONBOARDING_STABLE_INSTRUCTIONS = (
    "Produce a supplier onboarding package covering stakeholders, capability validation, "
    "commercial terms, risk acceptance, and open items.\n"
    "- Confirm required internal approvals and accountable owners\n"
    "- Summarize capability and commercial posture from submitted materials\n"
    "- Flag compliance, security, and continuity risks before onboarding\n"
    "- Cite material capability, commercial, and risk claims with [source:…] from Retrieved Context\n"
    "- Preserve documented risk tiers from profiles / [meta:riskTier=...] when present\n"
    "- Close with an explicit go / no-go / conditional recommendation and blockers\n"
    "- Do not perform full MSA clause extraction unless contract text is explicitly provided "
    "as onboarding evidence"
)

CONTRACT_REVIEW_SETUP_NOTE = (
    "Setup: ingest contract and policy on the job page (Jet KB or external vector DB), or supply "
    "contract via User request (public URL or pasted text — contract-analyzer fetches URLs when "
    "the agent uses them). Optional run context: vendor, expiry, spend. For production, ingest "
    "your org policy into the job KB; until then the job uses generic template policy from config."
)

_RATE_CARD_JOB_NAMES = (
    "Rate Card Normalization",
    "Rate Card Normalization (Executive)",
    "Rate Card Normalization (Scorecard)",
)


def _shared_base_rules(*, citation: bool, format_severity: str, high_risk_description: str) -> list[dict[str, Any]]:
    """Persona-aware copies of validation-contract style rules (seeded onto jobs directly)."""
    rules: list[dict[str, Any]] = []
    if citation:
        rules.append(
            {
                "id": "proc_citation",
                "name": "Citation coverage",
                "type": "citation",
                "severity": "warning",
                "enabled": True,
                "description": "Material claims must include [source:] citations.",
            }
        )
    rules.append(
        {
            "id": "proc_format",
            "name": "Output format compliance",
            "type": "format",
            "severity": format_severity,
            "enabled": True,
            "description": "Output must match the job output template structure.",
        }
    )
    rules.append(
        {
            "id": "proc_high_risk",
            "name": "High-risk flag warning",
            "type": "custom",
            "severity": "warning",
            "enabled": True,
            "description": high_risk_description,
        }
    )
    return rules


def _job_definitions() -> list[dict[str, Any]]:
    contract_risk = (
        "Explicitly flag material contractual, commercial, and renewal risks "
        "(auto-renewal traps, weak liability, missing AI/data controls, notice gaps)."
    )
    capability_risk = (
        "Explicitly flag me-too risk, unsupported capability claims, and evidence gaps "
        "that would make a supplier selection indefensible."
    )
    rate_risk = (
        "Explicitly flag material rate variance (>15% above benchmark) and spend concentration risk."
    )
    onboarding_risk = (
        "Explicitly flag onboarding blockers: missing approvals, compliance/security gaps, "
        "and unresolved open items before go-live."
    )

    return [
        {
            "name": "Contract Review & Renewal",
            "description": (
                "Audit-ready renewal assessment for an active supplier contract. Surfaces clause gaps, "
                "commercial exposure, policy alignment, evidence gaps, and a clear next action. "
                "Best for category managers and legal partners preparing renewals. "
                f"{CONTRACT_REVIEW_SETUP_NOTE}"
            ),
            "workflow_type": "contract_review",
            "goal": "Review an active supplier contract for renewal risk and produce a structured assessment.",
            "role_configuration": _contract_role_full(),
            "stable_instructions": CONTRACT_CLAUSE_CHECKLIST,
            "output_template": CONTRACT_OUTPUT_FULL,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=True, format_severity="error", high_risk_description=contract_risk
            )
            + [dict(CONTRACT_MANDATORY_CLAUSE_RULE)],
            "persona": "full",
            "family": "contract_review",
        },
        {
            "name": "Contract Review & Renewal (Executive)",
            "description": (
                "Executive renewal decision brief: renew / renegotiate / exit, top risks, and one next step. "
                "Same underlying clause review discipline, decision-first packaging. "
                f"{CONTRACT_REVIEW_SETUP_NOTE}"
            ),
            "workflow_type": "contract_review",
            "goal": "Deliver a concise executive decision brief on contract renewal risk.",
            "role_configuration": _contract_role_executive(),
            "stable_instructions": CONTRACT_CLAUSE_CHECKLIST,
            "output_template": CONTRACT_OUTPUT_EXECUTIVE,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=False, format_severity="error", high_risk_description=contract_risk
            )
            + [dict(CONTRACT_MANDATORY_CLAUSE_RULE)],
            "persona": "executive",
            "family": "contract_review",
        },
        {
            "name": "Contract Review & Renewal (Scorecard)",
            "description": (
                "Committee-ready JSON scorecard of clause health and renewal urgency. "
                "Use when downstream systems or steering committees need structured scores. "
                f"{CONTRACT_REVIEW_SETUP_NOTE}"
            ),
            "workflow_type": "contract_review",
            "goal": "Score contract renewal risk and clause health as structured JSON.",
            "role_configuration": _contract_role_scorecard(),
            "stable_instructions": CONTRACT_CLAUSE_CHECKLIST,
            "output_template": CONTRACT_OUTPUT_SCORECARD,
            "tool_permissions": REVIEW_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=False, format_severity="error", high_risk_description=contract_risk
            )
            + [dict(CONTRACT_MANDATORY_CLAUSE_RULE)],
            "persona": "scorecard",
            "family": "contract_review",
        },
        {
            "name": "Supplier Capability Matrix",
            "description": (
                "Defensible multi-supplier comparison that rewards differentiation and cited evidence—not "
                "price-only or me-too feature lists. Weighted criteria, perception-vs-evidence, and "
                "recommendation scenarios. Needs: 2–5 supplier names plus RFP responses / vendor profiles in request or KB."
            ),
            "workflow_type": "supplier_assessment",
            "goal": "Compare supplier capabilities with emphasis on differentiation and evidence quality.",
            "role_configuration": _capability_role_full(),
            "stable_instructions": CAPABILITY_STABLE_INSTRUCTIONS,
            "output_template": CAPABILITY_OUTPUT_FULL,
            "tool_permissions": CAPABILITY_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=True, format_severity="error", high_risk_description=capability_risk
            )
            + [dict(r) for r in SUPPLIER_ASSESSMENT_RISK_RULES],
            "persona": "full",
            "family": "supplier_capability",
        },
        {
            "name": "Supplier Capability Matrix (Executive)",
            "description": (
                "Executive supplier selection brief: recommendation, differentiators, me-too risks, next step. "
                "Needs: supplier names and capability evidence in request or KB."
            ),
            "workflow_type": "supplier_assessment",
            "goal": "Deliver a concise executive supplier selection brief.",
            "role_configuration": _capability_role_executive(),
            "stable_instructions": CAPABILITY_STABLE_INSTRUCTIONS,
            "output_template": CAPABILITY_OUTPUT_EXECUTIVE,
            "tool_permissions": CAPABILITY_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=False, format_severity="error", high_risk_description=capability_risk
            )
            + [dict(r) for r in SUPPLIER_ASSESSMENT_RISK_RULES],
            "persona": "executive",
            "family": "supplier_capability",
        },
        {
            "name": "Supplier Capability Matrix (Scorecard)",
            "description": (
                "Structured JSON dimension scores and ranking for supplier shortlists. "
                "Needs: supplier names and capability evidence in request or KB."
            ),
            "workflow_type": "supplier_assessment",
            "goal": "Return structured supplier dimension scores as JSON.",
            "role_configuration": _capability_role_scorecard(),
            "stable_instructions": CAPABILITY_STABLE_INSTRUCTIONS,
            "output_template": CAPABILITY_OUTPUT_SCORECARD,
            "tool_permissions": CAPABILITY_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=False, format_severity="error", high_risk_description=capability_risk
            )
            + [dict(r) for r in SUPPLIER_ASSESSMENT_RISK_RULES],
            "persona": "scorecard",
            "family": "supplier_capability",
        },
        {
            "name": "Rate Card Normalization",
            "description": (
                "Normalize heterogeneous vendor rate cards onto a job taxonomy, flag >15% variance, and "
                "surface spend concentration. Flagship substance workflow for professional-services pricing. "
                "Needs: rate card CSV/text in request or rate_card docs in Jet KB."
            ),
            "workflow_type": "analysis",
            "goal": "Normalize vendor rate cards, flag variance, and summarize spend concentration.",
            "role_configuration": _rate_card_role_full(),
            "stable_instructions": RATE_CARD_STABLE_INSTRUCTIONS,
            "output_template": RATE_CARD_OUTPUT_FULL,
            "tool_permissions": RATE_CARD_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=True, format_severity="error", high_risk_description=rate_risk
            )
            + [dict(r) for r in ANALYSIS_PROCUREMENT_VALIDATION_RULES],
            "persona": "full",
            "family": "rate_card",
            **_rate_card_job_fields(),
        },
        {
            "name": "Rate Card Normalization (Executive)",
            "description": (
                "Executive brief on rate-card findings: decision, top variances, concentration risk, next step. "
                "Needs: rate card data in request or KB."
            ),
            "workflow_type": "analysis",
            "goal": "Deliver a concise executive brief on rate card normalization findings.",
            "role_configuration": _rate_card_role_executive(),
            "stable_instructions": RATE_CARD_STABLE_INSTRUCTIONS,
            "output_template": RATE_CARD_OUTPUT_EXECUTIVE,
            "tool_permissions": RATE_CARD_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=False, format_severity="error", high_risk_description=rate_risk
            )
            + [dict(r) for r in ANALYSIS_PROCUREMENT_VALIDATION_RULES],
            "persona": "executive",
            "family": "rate_card",
            **_rate_card_job_fields(),
        },
        {
            "name": "Rate Card Normalization (Scorecard)",
            "description": (
                "Machine-readable spend-analyzer JSON for normalized rates, unmapped titles, and variance flags. "
                "Needs: rate card data in request or KB."
            ),
            "workflow_type": "analysis",
            "goal": "Return spend-analyzer structured JSON for normalized rate card analysis.",
            "role_configuration": _rate_card_role_scorecard(),
            "stable_instructions": RATE_CARD_STABLE_INSTRUCTIONS,
            "output_template": RATE_CARD_OUTPUT_SCORECARD,
            "tool_permissions": RATE_CARD_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=False, format_severity="error", high_risk_description=rate_risk
            )
            + [dict(r) for r in ANALYSIS_PROCUREMENT_VALIDATION_RULES],
            "persona": "scorecard",
            "family": "rate_card",
            **_rate_card_job_fields(),
        },
        {
            "name": "Supplier Onboarding Checklist",
            "description": (
                "Stakeholder onboarding package with capability/commercial summaries, risk flags, required "
                "approvals, open items, and go/no-go. Lite onboarding memo (full multi-step is the chained path). "
                "Needs: supplier packet / vendor profile materials in request or KB."
            ),
            "workflow_type": "procurement",
            "goal": "Build a stakeholder onboarding checklist with capability, commercial, and risk summaries.",
            "role_configuration": _onboarding_role_full(),
            "stable_instructions": ONBOARDING_STABLE_INSTRUCTIONS,
            "output_template": ONBOARDING_OUTPUT_FULL,
            "tool_permissions": ONBOARDING_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=True, format_severity="error", high_risk_description=onboarding_risk
            )
            + [dict(r) for r in ONBOARDING_RISK_RULES],
            "persona": "full",
            "family": "supplier_onboarding",
        },
        {
            "name": "Supplier Onboarding Checklist (Executive)",
            "description": (
                "Executive go/no-go onboarding brief: decision, risk tier, open items, next step. "
                "Needs: supplier onboarding materials in request or KB."
            ),
            "workflow_type": "procurement",
            "goal": "Deliver a concise executive onboarding go/no-go brief.",
            "role_configuration": _onboarding_role_executive(),
            "stable_instructions": ONBOARDING_STABLE_INSTRUCTIONS,
            "output_template": ONBOARDING_OUTPUT_EXECUTIVE,
            "tool_permissions": ONBOARDING_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=False, format_severity="error", high_risk_description=onboarding_risk
            )
            + [dict(r) for r in ONBOARDING_RISK_RULES],
            "persona": "executive",
            "family": "supplier_onboarding",
        },
        {
            "name": "Supplier Onboarding Checklist (Scorecard)",
            "description": (
                "Structured onboarding scorecard JSON for go/no-go governance and tracking. "
                "Needs: supplier onboarding materials in request or KB."
            ),
            "workflow_type": "procurement",
            "goal": "Return structured onboarding scorecard JSON.",
            "role_configuration": _onboarding_role_scorecard(),
            "stable_instructions": ONBOARDING_STABLE_INSTRUCTIONS,
            "output_template": ONBOARDING_OUTPUT_SCORECARD,
            "tool_permissions": ONBOARDING_TOOL_PERMISSIONS,
            "validation_rules": _shared_base_rules(
                citation=False, format_severity="error", high_risk_description=onboarding_risk
            )
            + [dict(r) for r in ONBOARDING_RISK_RULES],
            "persona": "scorecard",
            "family": "supplier_onboarding",
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
        (
            "Procurement Relationship Patterns",
            "relationship_pattern",
            "Common procurement entity relationships for grounding and retrieval.",
            _relationship_pattern_content(),
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

    # Preserve policy_* rules from Policy Placeholder, then apply the authoritative
    # per-template validation pack (persona-aware) from the job definition.
    policy_rules = [
        rule
        for rule in (job.validation_rules or [])
        if isinstance(rule, dict) and str(rule.get("id") or "").startswith("policy_")
    ]
    if job_validation_rules is not None:
        job.validation_rules = [dict(r) for r in job_validation_rules if isinstance(r, dict)] + policy_rules
    else:
        workflow = (job.workflow_type or "").lower()
        if workflow == "analysis":
            _merge_validation_rules(job, ANALYSIS_PROCUREMENT_VALIDATION_RULES)
        elif workflow == "supplier_assessment":
            _merge_validation_rules(job, SUPPLIER_ASSESSMENT_RISK_RULES)
        elif workflow == "procurement":
            _merge_validation_rules(job, ONBOARDING_RISK_RULES)
    job.tool_permissions = [dict(p) for p in workflow_tools]
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
            description=str(job_def.get("description") or f"System procurement template: {name}"),
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
    """Sync rate card system templates in DB (instructions, tools, budget, turns, persona roles)."""
    updated: list[str] = []
    defs_by_name = {d["name"]: d for d in _job_definitions() if d["name"] in _RATE_CARD_JOB_NAMES}
    target_instructions = RATE_CARD_STABLE_INSTRUCTIONS.strip()
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
        job_def = defs_by_name.get(name)
        target_role = str((job_def or {}).get("role_configuration") or _rate_card_role()).strip()

        changed = False
        if (job.stable_instructions or "").strip() != target_instructions:
            job.stable_instructions = RATE_CARD_STABLE_INSTRUCTIONS
            changed = True
        if (job.role_configuration or "").strip() != target_role:
            job.role_configuration = target_role
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
    """Keep contract retrieval settings aligned; specialty rules are owned by flagship sync."""
    updated: list[str] = []
    policy_asset = _find_asset(db, "Policy Placeholder")
    policy_asset_id = str(policy_asset.id) if policy_asset else None
    contract_retrieval = _contract_retrieval_config(policy_asset_id)
    target_instructions = CONTRACT_CLAUSE_CHECKLIST.strip()

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
            "Assess supplier capabilities based on the following contract review findings.\n\n"
            "{primaryResult}\n\n"
            "Add vendor profiles or RFP documents to this job's knowledge base before running, "
            "then refine this request with the specific suppliers you want to compare."
        ),
        "label": "Step 2: Supplier Capability Matrix",
    },
    {
        "name": "Supplier Capability Matrix",
        "workflow_type": "supplier_assessment",
        "child_name": "Supplier Onboarding Checklist",
        "user_request": (
            "Produce a supplier onboarding checklist based on the following capability assessment.\n\n"
            "{primaryResult}\n\n"
            "Add the supplier onboarding packet or any approval owner details before running."
        ),
        "label": "Step 3: Supplier Onboarding Checklist",
    },
]


def patch_procurement_chain_configs(db: Session) -> list[str]:
    """Patch chain_config onto standard Full templates (opt-in: triggerOnSuccess=False)."""
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

        child = _find_job(db, spec["child_name"])
        if not child:
            raise ValueError(f"System template not found: {spec['child_name']}")

        desired = {
            "triggerOnSuccess": False,
            "childJobId": str(child.id),
            "childTemplateName": spec["child_name"],
            "label": spec["label"],
            "inputMapping": {"userRequest": spec["user_request"]},
            "maxDepth": 3,
        }
        current = job.chain_config if isinstance(job.chain_config, dict) else {}
        # Preserve a user's/explicit True only if child id already matches; otherwise sync metadata.
        if (
            current.get("childJobId") == desired["childJobId"]
            and current.get("childTemplateName") == desired["childTemplateName"]
            and current.get("label") == desired["label"]
            and current.get("inputMapping") == desired["inputMapping"]
            and "triggerOnSuccess" in current
        ):
            continue

        merged = dict(desired)
        if current.get("childJobId") == desired["childJobId"] and current.get("triggerOnSuccess") is True:
            merged["triggerOnSuccess"] = True
        job.chain_config = merged
        db.add(job)
        updated.append(job.name)

    if updated:
        db.commit()
    return updated


def _replace_specialty_rules(existing: list[Any], specialty: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = [
        rule
        for rule in existing
        if not (
            isinstance(rule, dict)
            and str(rule.get("id") or "") in LEGACY_SPECIALTY_RULE_IDS
        )
    ]
    return kept + [dict(r) for r in specialty]


def _sync_flagship_system_templates(db: Session) -> list[str]:
    """
    Idempotently sync all __system__ flagship templates to the current catalog:
    description, roles, instructions, outputs, tools, validation, retrieval, budgets.
    """
    updated: list[str] = []
    policy_asset = _find_asset(db, "Policy Placeholder")
    policy_asset_id = str(policy_asset.id) if policy_asset else None
    assets_by_name = {
        name: asset
        for name in ASSET_NAMES
        if (asset := _find_asset(db, name)) is not None
    }

    for job_def in _job_definitions():
        job = _find_job(db, job_def["name"])
        if not job:
            continue

        changed = False
        target_description = str(job_def.get("description") or "")
        if (job.description or "").strip() != target_description.strip():
            job.description = target_description
            changed = True
        if (job.goal or "").strip() != str(job_def["goal"]).strip():
            job.goal = job_def["goal"]
            changed = True
        if (job.role_configuration or "").strip() != str(job_def["role_configuration"]).strip():
            job.role_configuration = job_def["role_configuration"]
            changed = True
        if (job.stable_instructions or "").strip() != str(job_def["stable_instructions"]).strip():
            job.stable_instructions = job_def["stable_instructions"]
            changed = True
        if (job.output_template or "").strip() != str(job_def["output_template"]).strip():
            job.output_template = job_def["output_template"]
            changed = True
        if (job.workflow_type or "") != job_def["workflow_type"]:
            job.workflow_type = job_def["workflow_type"]
            changed = True

        target_tools = [dict(p) for p in job_def["tool_permissions"]]
        if _tool_permission_ids(list(job.tool_permissions or [])) != _tool_permission_ids(target_tools):
            job.tool_permissions = target_tools
            changed = True

        if job_def["name"] in _RATE_CARD_JOB_NAMES:
            target_turns = RATE_CARD_MAX_AGENT_TURNS
            target_budget = dict(RATE_CARD_BUDGET_SETTINGS)
            target_retrieval = _rate_card_retrieval_config(policy_asset_id)
        elif job_def["workflow_type"] == "contract_review":
            target_turns = int(job_def.get("max_agent_turns") or 10)
            target_budget = job_def.get("budget_settings")
            target_retrieval = _contract_retrieval_config(policy_asset_id)
        else:
            target_turns = int(job_def.get("max_agent_turns") or 10)
            target_budget = job_def.get("budget_settings")
            target_retrieval = _base_retrieval_config(policy_asset_id)

        if int(job.max_agent_turns or 0) != target_turns:
            job.max_agent_turns = target_turns
            changed = True
        if target_budget is not None and dict(job.budget_settings or {}) != dict(target_budget):
            job.budget_settings = dict(target_budget)
            changed = True

        current_rc = dict(job.retrieval_config or {})
        if (
            int(current_rc.get("maxDocuments") or 0) != int(target_retrieval.get("maxDocuments") or 0)
            or bool(current_rc.get("queryRewriting")) != bool(target_retrieval.get("queryRewriting"))
        ):
            job.retrieval_config = {**current_rc, **target_retrieval}
            changed = True

        desired_rules = [dict(r) for r in (job_def.get("validation_rules") or []) if isinstance(r, dict)]
        policy_rules = [
            rule
            for rule in (job.validation_rules or [])
            if isinstance(rule, dict) and str(rule.get("id") or "").startswith("policy_")
        ]
        # Drop legacy shared specialty id collisions, then set authoritative pack.
        next_rules = desired_rules + policy_rules
        # Normalize: remove legacy proc_risk_threshold if new ids present
        has_new_risk = any(
            str(r.get("id")) in {"proc_risk_threshold_supplier", "proc_risk_threshold_onboarding"}
            for r in next_rules
        )
        if has_new_risk:
            next_rules = [r for r in next_rules if str(r.get("id") or "") != "proc_risk_threshold"]

        def _rule_sig(rules: list[Any]) -> list[tuple[Any, ...]]:
            sig: list[tuple[Any, ...]] = []
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                sig.append(
                    (
                        str(rule.get("id") or ""),
                        str(rule.get("type") or ""),
                        str(rule.get("severity") or ""),
                        str(rule.get("checker") or ""),
                        bool(rule.get("enabled", True)),
                        str(rule.get("description") or ""),
                        str(sorted((rule.get("params") or {}).items()) if isinstance(rule.get("params"), dict) else ""),
                    )
                )
            return sorted(sig)

        if _rule_sig(list(job.validation_rules or [])) != _rule_sig(next_rules):
            job.validation_rules = next_rules
            changed = True

        # Ensure glossary/tool profile imports exist for older templates.
        if assets_by_name and not (job.glossary_terms or []):
            _apply_imports(
                job,
                assets_by_name,
                target_tools,
                job_validation_rules=desired_rules,
            )
            changed = True

        if changed:
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

    # Keep tool profile asset content aligned with family tool packs.
    tool_profile = assets_by_name.get("Procurement Tool Profile")
    if tool_profile:
        desired_tool_profile = _tool_profile_content()
        if tool_profile.content != desired_tool_profile:
            tool_profile.content = desired_tool_profile
            db.add(tool_profile)
            db.commit()

    created_jobs, skipped_jobs = _seed_jobs(db, assets_by_name)
    patched_jobs = _patch_executive_output_templates(db)
    patched_rate_card = _patch_rate_card_templates(db)
    synced_flagship = _sync_flagship_system_templates(db)
    patched_procurement = _patch_procurement_validation_and_retrieval(db)
    patched_chains = patch_procurement_chain_configs(db)

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
    if synced_flagship:
        logger.info("Synced flagship system templates: %s", ", ".join(synced_flagship))
    if patched_procurement:
        logger.info(
            "Patched procurement validation/retrieval: %s",
            ", ".join(patched_procurement),
        )
    if patched_chains:
        logger.info("Patched procurement chain configs: %s", ", ".join(patched_chains))
