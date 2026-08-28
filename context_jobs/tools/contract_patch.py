"""Surgical contract patch tool.

LLM provides only the changed clause texts as a JSON diff.
The canonical source text is pre-seeded by the amendment service to disk;
the LLM never has to echo back the full contract, eliminating truncation.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from io import BytesIO
from typing import Any, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from context_jobs.tools.artifact_paths import resolve_artifact_path, run_artifact_dir
from context_jobs.tools.base import BaseTool

NAVY = RGBColor(0x1A, 0x3C, 0x6E)

# Filename where the amendment service pre-seeds the canonical contract text.
CANONICAL_SEED_FILENAME = "_canonical_source.txt"

# ── regex helpers ─────────────────────────────────────────────────────────────

# Top-level section start: "1. Service" / "13. Definitions"
_TOP_SECTION = re.compile(r"(?m)^(\d+)\.\s+[A-Za-z\"']")


# ── section splitter ──────────────────────────────────────────────────────────

def _section_spans(text: str) -> list[tuple[str, int, int]]:
    """Return [(id, start, end)] for every top-level section in the text."""
    matches = list(_TOP_SECTION.finditer(text))
    spans: list[tuple[str, int, int]] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        spans.append((m.group(1), m.start(), end))
    return spans


_LETTER_ID = re.compile(
    r"^(\d+(?:\.\d+)*)[\.\(]?([A-Za-z])\)?$",
)
# "5.5.b" / "5.5(b)" / "5.5.b." — numbered parent + lettered child
_LETTERED_CLAUSE = re.compile(
    r"^(\d+(?:\.\d+)*)\.([A-Za-z])$",
)


def _parse_clause_id(clause_id: str) -> tuple[str, str | None]:
    """Return (numeric_id, letter) e.g. ('5.5', 'b') or ('1.6', None)."""
    raw = clause_id.strip().rstrip(".")
    lettered = _LETTERED_CLAUSE.match(raw)
    if lettered:
        return lettered.group(1), lettered.group(2).lower()
    # "5.5(b)" form
    paren = re.match(r"^(\d+(?:\.\d+)*)\(([A-Za-z])\)$", raw)
    if paren:
        return paren.group(1), paren.group(2).lower()
    return raw, None


def _find_numeric_clause_span(text: str, numeric_id: str) -> tuple[int, int] | None:
    escaped = re.escape(numeric_id)
    pattern = re.compile(
        rf"(?m)^(\s*){escaped}\.?\s+[^\n]*(?:\n|$)",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if not m:
        return None

    clause_start = m.start()
    heading_end = m.end()
    depth = len(numeric_id.replace(".", " ").split())
    end_pattern = re.compile(
        r"(?m)^\s*(\d+(?:\.\d+){0,%d})\.?\s+[A-Za-z\"'(]" % (depth - 1),
    )
    next_m = end_pattern.search(text, heading_end)
    end_pos = next_m.start() if next_m else len(text)
    return clause_start, end_pos


def _find_lettered_item_span(
    text: str, parent_start: int, parent_end: int, letter: str
) -> tuple[int, int] | None:
    """Find 'b.' / '(b)' / 'b)' item inside a parent clause span."""
    chunk = text[parent_start:parent_end]
    pattern = re.compile(
        rf"(?m)^(\s*)(?:\(?{re.escape(letter)}\)|\(?{re.escape(letter)}\.)\s+",
        re.IGNORECASE,
    )
    m = pattern.search(chunk)
    if not m:
        return None
    item_start = parent_start + m.start()
    after = parent_start + m.end()
    next_item = re.compile(r"(?m)^\s*(?:\(?[A-Za-z]\)|\(?[A-Za-z]\.)\s+")
    n = next_item.search(text, after)
    item_end = n.start() if n and n.start() < parent_end else parent_end
    return item_start, item_end


def _find_clause_span(text: str, clause_id: str) -> tuple[int, int] | None:
    """Locate a numbered clause, or a lettered sub-item (e.g. 5.5.b)."""
    numeric_id, letter = _parse_clause_id(clause_id)
    parent = _find_numeric_clause_span(text, numeric_id)
    if parent is None:
        return None
    if letter is None:
        return parent
    return _find_lettered_item_span(text, parent[0], parent[1], letter)


def _heading_prefix(chunk: str, clause_id: str) -> str:
    """Keep indent + number + optional title ('Machine Learning.')."""
    numeric_id, letter = _parse_clause_id(clause_id)
    if letter:
        m = re.match(
            rf"^(\s*)(?:\(?{re.escape(letter)}\)|\(?{re.escape(letter)}\.)\s+",
            chunk,
            re.IGNORECASE,
        )
        return chunk[: m.end()] if m else f"{letter}. "
    m = re.match(
        rf"^(\s*){re.escape(numeric_id)}\.?\s+"
        rf"((?:[A-Z][A-Za-z0-9/&'’ -]{{0,80}}\.\s+)?)",
        chunk,
    )
    if m:
        return chunk[: m.end()]
    m2 = re.match(rf"^(\s*){re.escape(numeric_id)}\.?\s+", chunk)
    return chunk[: m2.end()] if m2 else f"{numeric_id}. "


def _replace_inside_clause(
    text: str, clause_id: str, find: str, replace: str
) -> tuple[str, bool, str]:
    """Surgical find/replace inside one clause. Returns (text, found, note)."""
    span = _find_clause_span(text, clause_id)
    if span is None:
        return text, False, f"clause {clause_id} not found"
    start, end = span
    chunk = text[start:end]
    if find not in chunk:
        # try case-insensitive
        idx = chunk.lower().find(find.lower())
        if idx < 0:
            return text, False, f"find-text not in clause {clause_id}"
        chunk = chunk[:idx] + replace + chunk[idx + len(find) :]
    else:
        chunk = chunk.replace(find, replace, 1)
    return text[:start] + chunk + text[end:], True, ""


def _replace_clause(text: str, clause_id: str, new_body: str) -> tuple[str, bool, str]:
    """Replace the body of a clause, keeping number and original title.

    Rejects replacements that shrink the clause by more than 40% so a stub
    cannot wipe a multi-paragraph Effect of Termination / invoicing clause.
    Returns (new_text, applied, note).
    """
    span = _find_clause_span(text, clause_id)
    if span is None:
        note = (
            f"\n\n[PATCH NOTE: clause {clause_id} not found in source; "
            "verify clause numbering]\n"
        )
        return text + note, False, f"clause {clause_id} not found"

    clause_start, clause_end = span
    chunk = text[clause_start:clause_end]
    prefix = _heading_prefix(chunk, clause_id)
    original_body = chunk[len(prefix) :].strip()
    orig_words = len(original_body.split()) if original_body else 0
    new_words = len(new_body.split())
    overlap = (
        SequenceMatcher(None, original_body.lower(), new_body.lower()).ratio()
        if original_body and new_body
        else 1.0
    )
    if orig_words >= 40 and (new_words < orig_words * 0.6 or overlap < 0.55):
        excerpt = original_body.strip()
        if len(excerpt) > 2500:
            excerpt = excerpt[:2500] + "\n[truncated]"
        return (
            text,
            False,
            (
                f"REJECTED clause {clause_id}: replacement is {new_words} words vs "
                f"original {orig_words} (overlap {overlap:.0%}). This looks like a rewrite, "
                f"not a redline. Use find/replace, or new_text copied from this original "
                f"with only the requested words changed:\n--- original {clause_id} ---\n{excerpt}\n---"
            ),
        )

    replacement = prefix + new_body.rstrip() + "\n\n"
    return text[:clause_start] + replacement + text[clause_end:], True, ""


def _patch_cover_field(text: str, field: str, new_value: str) -> str:
    """Replace a cover page field value on its own line."""
    pattern = re.compile(
        rf"(?m)^({re.escape(field)}\s*:\s*)[^\n]*$",
        re.IGNORECASE,
    )
    new_text, count = pattern.subn(rf"\g<1>{new_value}", text)
    if count == 0:
        inline = re.compile(
            rf"({re.escape(field)}\s*[:\-]\s*)([^,\n.;]+)",
            re.IGNORECASE,
        )
        new_text, _ = inline.subn(rf"\g<1>{new_value}", text)
    return new_text


# ── DOCX builder ──────────────────────────────────────────────────────────────

def _split_for_docx(text: str) -> list[tuple[str, str]]:
    """Split assembled text into (heading, body) pairs for top-level sections."""
    spans = _section_spans(text)
    if not spans:
        return [("Document", text.strip())]

    sections: list[tuple[str, str]] = []

    cover_text = text[: spans[0][1]].strip()
    if cover_text:
        # Skip duplicate title line: the first non-empty line of the cover is usually
        # the document title which is already rendered as the DOCX heading.
        cover_lines = cover_text.splitlines()
        if cover_lines:
            cover_lines = cover_lines[1:]  # drop first (title) line
        cover_body = "\n".join(cover_lines).strip()
        sections.append(("Cover Page", cover_body if cover_body else cover_text))

    for _sec_id, start, end in spans:
        chunk = text[start:end].strip()
        lines = chunk.splitlines()
        heading = lines[0].strip() if lines else ""
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        sections.append((heading, body))

    return sections


def _build_docx(title: str, sections: list[tuple[str, str]]) -> bytes:
    doc = Document()

    if title:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.bold = True
        r.font.size = Pt(18)
        r.font.color.rgb = NAVY

    for heading, body in sections:
        if heading:
            doc.add_heading(heading, level=2)
        if body:
            for para_block in body.split("\n\n"):
                stripped = para_block.strip()
                if not stripped:
                    continue
                # Render sub-items (indented lines) as separate paragraphs
                for line in stripped.splitlines():
                    ln = line.strip()
                    if ln:
                        doc.add_paragraph(ln)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── tool ──────────────────────────────────────────────────────────────────────

class ContractPatchTool(BaseTool):
    id = "contract-patch"
    name = "Contract Patch"
    description = (
        "Apply surgical edits to a contract and write a revised Word document. "
        "The original contract source is already loaded on the server — "
        "you do NOT need to pass source_text unless you want to override it. "
        "Provide ONLY the changed clauses in section_patches and any cover-page "
        "field changes in cover_patches. "
        "Every section not listed in patches is copied verbatim from the original. "
        "Use this instead of docx-generate for ALL contract amendments."
    )
    requires_external_key = False
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Output .docx path, e.g. revised-contract.docx",
            },
            "title": {
                "type": "string",
                "description": "Document title shown at top of Word file",
            },
            "source_text": {
                "type": "string",
                "description": (
                    "OPTIONAL. Full original contract text. "
                    "Leave blank — the server auto-loads the pre-seeded canonical source. "
                    "Only provide this if you have a specific source override."
                ),
            },
            "cover_patches": {
                "type": "array",
                "description": "Cover page field replacements.",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "description": "Exact cover page field name, e.g. 'General Cap Amount'",
                        },
                        "new_value": {
                            "type": "string",
                            "description": "New value for that field",
                        },
                    },
                    "required": ["field", "new_value"],
                },
            },
            "section_patches": {
                "type": "array",
                "description": (
                    "Surgical edits. Prefer find+replace inside a clause. "
                    "Use new_text only for a full-clause rewrite, and new_text MUST "
                    "contain the complete original clause (all a/b/c/d sub-items) "
                    "with only the requested words changed. "
                    "id may be '1.6', '5.5', or a lettered sub-item '5.5.b'."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Clause id e.g. '1.6' or lettered sub-item '5.5.b'",
                        },
                        "find": {
                            "type": "string",
                            "description": "Exact phrase in the original clause to replace (preferred for number swaps)",
                        },
                        "replace": {
                            "type": "string",
                            "description": "Replacement phrase",
                        },
                        "new_text": {
                            "type": "string",
                            "description": (
                                "Full replacement body for this clause, including every "
                                "original sub-paragraph. Exclude the clause number and title."
                            ),
                        },
                    },
                    "required": ["id"],
                },
            },
        },
        "required": ["path", "section_patches"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        api_key: Optional[str] = None,
        *,
        owner: str | None = None,
        run_id: str | None = None,
    ) -> str:
        if not owner or not run_id:
            raise ValueError("contract-patch requires run context (owner and run_id)")

        path_arg = str(arguments.get("path", "revised-contract.docx")).strip()
        if not path_arg.lower().endswith(".docx"):
            path_arg = path_arg + ".docx"

        # Load source — prefer seed file; fall back to inline argument
        source_text = str(arguments.get("source_text") or "").strip()
        if not source_text:
            seed_path = run_artifact_dir(owner, run_id) / CANONICAL_SEED_FILENAME
            if seed_path.exists():
                source_text = seed_path.read_text(encoding="utf-8").strip()
        if not source_text:
            raise ValueError(
                "contract-patch: no source text available. "
                "The canonical source seed file was not found; ensure the amendment "
                "service wrote it before calling this tool."
            )

        cover_patches: list[dict] = arguments.get("cover_patches") or []
        section_patches: list[dict] = arguments.get("section_patches") or []

        assembled = source_text

        # 1. Apply cover patches
        for cp in cover_patches:
            field = str(cp.get("field", "")).strip()
            new_value = str(cp.get("new_value", "")).strip()
            if field and new_value:
                assembled = _patch_cover_field(assembled, field, new_value)

        # 2. Apply section patches
        applied: list[str] = []
        failed: list[str] = []
        rejections: list[str] = []
        for sp in section_patches:
            clause_id = str(sp.get("id", "")).strip()
            if not clause_id:
                continue
            find = str(sp.get("find") or "").strip()
            replace = str(sp.get("replace") or "").strip()
            new_text = str(sp.get("new_text") or "").strip()
            if find and replace:
                assembled, found, note = _replace_inside_clause(
                    assembled, clause_id, find, replace
                )
                if found:
                    applied.append(f"{clause_id} (find/replace)")
                else:
                    failed.append(f"{clause_id}: {note}")
                continue
            if not new_text:
                failed.append(f"{clause_id}: need find/replace or new_text")
                continue
            assembled, found, note = _replace_clause(assembled, clause_id, new_text)
            if found:
                applied.append(clause_id)
            elif note.startswith("REJECTED"):
                rejections.append(note)
            else:
                failed.append(f"{clause_id}: {note}")

        # Never abort the document write. A stub patch is skipped (original kept)
        # and the LLM is told to retry with the original clause body.

        # 3. Build DOCX
        title = str(arguments.get("title", "Revised Contract")).strip()
        docx_sections = _split_for_docx(assembled)
        docx_bytes = _build_docx(title, docx_sections)

        # 4. Persist to run artifact dir
        target = resolve_artifact_path(owner, run_id, path_arg)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(docx_bytes)

        from context_jobs.artifacts.blob_store import persist_run_artifact_file
        persist_run_artifact_file(owner, run_id, path_arg, target, tool_id=self.id)

        summary_parts = [
            f"Contract patch complete → {path_arg}.",
            f"Document: {len(docx_sections)} top-level sections, "
            f"{len(assembled.split())} words total.",
        ]
        if applied:
            summary_parts.append(f"Patches applied to clauses: {', '.join(applied)}.")
        if rejections:
            summary_parts.append("STUB PATCHES SKIPPED (original clause kept): " + " | ".join(rejections))
        if failed:
            summary_parts.append(
                "WARNING — some patches did not apply: " + "; ".join(failed) + "."
            )
        cover_names = [cp.get("field", "") for cp in cover_patches if cp.get("field")]
        if cover_names:
            summary_parts.append(f"Cover fields updated: {', '.join(cover_names)}.")

        summary = " ".join(summary_parts)
        if rejections:
            raise ValueError(
                summary
                + " Retry contract-patch now using find/replace or the original clause bodies above."
            )
        return summary
