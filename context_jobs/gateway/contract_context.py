"""Helpers for passing complete contract text into contract-analyzer."""

from __future__ import annotations

import re

from context_jobs.text_sanitize import sanitize_db_text

_MAX_CONTRACT_ANALYZER_CHARS = 80_000

_RENEWAL_MARKERS = (
    "renewal notice",
    "non-renewal",
    "non renewal",
    "notice of non-renewal",
    "written notice of non-renewal",
    "automatic renewal",
)

_CONTRACT_SOURCE_MARKERS = (
    "msa",
    "master service agreement",
    "statement of work",
    "contract",
    "agreement",
)

_POLICY_PLACEHOLDER_MARKERS = (
    "customer policy placeholder",
    "policy placeholder",
)

_POLICY_CONTENT_MARKERS = (
    "procurement policy",
    "issued by:",
    "version:",
    "ai clause requirements",
    "renewal management",
    "contract register",
)

_BLOCK_SPLIT_RE = re.compile(r"\n\n---\n\n")
_SOURCE_LINE_RE = re.compile(r"^\[source:(.+?)\]\s*$", re.IGNORECASE)


def _split_retrieved_blocks(retrieved_context: str) -> list[str]:
    text = (retrieved_context or "").strip()
    if not text:
        return []
    return [block.strip() for block in _BLOCK_SPLIT_RE.split(text) if block.strip()]


def _source_name_from_block(block: str) -> str:
    lines = (block or "").splitlines()
    first_line = lines[0].strip() if lines else ""
    match = _SOURCE_LINE_RE.match(first_line)
    return (match.group(1).strip() if match else "").lower()


def _is_policy_placeholder_block(block: str) -> bool:
    source = _source_name_from_block(block)
    if not source:
        return False
    return any(marker in source for marker in _POLICY_PLACEHOLDER_MARKERS)


def _is_policy_content_block(block: str) -> bool:
    lower = (block or "").lower()
    return any(marker in lower for marker in _POLICY_CONTENT_MARKERS)


def _is_contract_source_block(block: str) -> bool:
    source = _source_name_from_block(block)
    if source and "policy" in source:
        return False
    if _is_policy_content_block(block):
        return False
    # Retrieved chunk names can be generic (e.g. doc_0-chunk-3), so treat any
    # non-policy block as contract-priority material for contract-analyzer.
    if source:
        return True
    return not _is_policy_content_block(block)


def _has_renewal_content(text: str) -> bool:
    lower = (text or "").lower()
    return any(marker in lower for marker in _RENEWAL_MARKERS)


def _normalize_for_overlap(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _block_already_covered(block: str, covered_text: str) -> bool:
    """True when this block's substantive text already appears in covered_text."""
    normalized_block = _normalize_for_overlap(block)
    normalized_covered = _normalize_for_overlap(covered_text)
    if not normalized_block:
        return True
    if normalized_block in normalized_covered:
        return True
    anchor = normalized_block[: min(120, len(normalized_block))]
    return len(anchor) >= 40 and anchor in normalized_covered


def _pack_blocks(blocks: list[str], max_chars: int) -> str:
    """Pack blocks while prioritizing contract renewal sections."""
    if not blocks:
        return ""

    priority_blocks = [
        b for b in blocks if _is_contract_source_block(b) and _has_renewal_content(b)
    ]
    other_blocks = [b for b in blocks if b not in priority_blocks]
    ordered = priority_blocks + other_blocks

    parts: list[str] = []
    total = 0
    separator = "\n\n---\n\n"

    for block in ordered:
        if not block:
            continue
        sep_len = len(separator) if parts else 0
        if total + sep_len + len(block) <= max_chars:
            parts.append(block)
            total += sep_len + len(block)
            continue
        if _is_contract_source_block(block) and _has_renewal_content(block):
            remaining = max_chars - total - sep_len
            if remaining > 200:
                parts.append(block[:remaining])
            break

    return separator.join(parts)[:max_chars]


def consolidate_contract_analyzer_text(agent_value: str, retrieved_context: str) -> str:
    """
    Merge agent-passed contract text with retrieved KB context.

    Policy placeholder blocks are excluded so contract-analyzer evaluates
    contract language rather than policy checklist text.
    """
    rag = (retrieved_context or "").strip()
    passed = (agent_value or "").strip()
    rag_blocks = [
        block for block in _split_retrieved_blocks(rag)
        if not _is_policy_placeholder_block(block) and not _is_policy_content_block(block)
    ]

    if not rag_blocks:
        return sanitize_db_text(passed)[:_MAX_CONTRACT_ANALYZER_CHARS]

    merged_blocks: list[str] = []
    covered = ""

    for block in rag_blocks:
        merged_blocks.append(block)
        covered = f"{covered}\n{block}" if covered else block

    if passed and not _block_already_covered(passed, covered):
        merged_blocks.append(sanitize_db_text(passed))

    return sanitize_db_text(_pack_blocks(merged_blocks, _MAX_CONTRACT_ANALYZER_CHARS))
