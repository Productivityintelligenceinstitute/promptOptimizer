"""Blank workflow-canvas workbook and the upload that fills job builder fields.

The sheet follows Gerald's Context Job Workflow Design Canvas. It is not a
knowledge-base ingest. Filled cells map onto the job fields a user would
otherwise type in the builder.
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

CANVAS_START = "<!-- workflow-canvas:start -->"
CANVAS_END = "<!-- workflow-canvas:end -->"

WORKFLOW_SHEET = "Workflow"
DECISION_SHEET = "Decision logic"
MEASURES_SHEET = "Baseline measures"
UAT_SHEET = "UAT questions"
HELP_SHEET = "How to use"

_MAX_WORKBOOK_BYTES = 2_000_000

_ESCALATION_VALUES = {
    "never": "never",
    "never escalate": "never",
    "on_failure": "on_failure",
    "on failure": "on_failure",
    "escalate on failure": "on_failure",
    "always_review": "always_review",
    "always review": "always_review",
    "always require review": "always_review",
}

_WORKFLOW_ROWS: tuple[tuple[str, str], ...] = (
    ("Job name", "Name. Leave blank to keep the current name."),
    ("Trigger", "Description. A filled cell replaces the current description."),
    ("Inputs", "Instructions. Documents, data, and signals that enter the workflow."),
    ("Current-state process", "Instructions. How the work is done today."),
    ("JET intervention", "Instructions. What JET should analyze, compare, or draft."),
    ("Human decision", "Instructions. The judgment that stays with a person, and who owns it."),
    ("Actions / outputs", "Instructions. Artifacts or downstream actions. This does not replace the output template."),
    (
        "Escalations / exceptions",
        "Instructions. If the cell is exactly never, on_failure, or always_review, it also sets Escalation policy.",
    ),
    ("Systems / integrations", "Instructions. Systems, vector databases, or repositories involved."),
    ("End state", "Goal. A filled cell replaces the current goal."),
    ("Role", "Role configuration. Leave blank to keep the current role."),
    (
        "Output template",
        "Output template. Leave blank to keep the current headings. Paste headings only when you mean to replace them.",
    ),
)

_MEASURES: tuple[str, ...] = (
    "Cycle time",
    "Expert/analyst hours",
    "Quality/consistency",
    "Risk/issue visibility",
    "Rework",
    "Decision confidence",
    "Adoption/repeat use",
    "Implementation friction",
)

_UAT_QUESTIONS: tuple[str, ...] = (
    "Does this job solve a recurring and consequential business problem?",
    "What does the user do today without JET?",
    "Where does the current process still depend on expert judgment or manual synthesis?",
    "What part of the workflow is differentiated versus Copilot, generic LLMs, CLM/procurement platforms, or other existing tools?",
    "What evidence would make a buyer pay for a bounded pilot?",
    "What would falsify the value proposition?",
    "What reusable IP or decision rule should be harvested from this implementation?",
    "Can the workflow be delivered repeatedly without Gerald or another expert compensating for weak design?",
)

_DECISION_HEADERS = (
    "Decision / issue",
    "Current state",
    "Target / benchmark",
    "Gap",
    "Why it matters",
    "Recommended action",
)

_HEADER_FILL = PatternFill("solid", fgColor="0F2E4E")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_LABEL_FONT = Font(bold=True, color="0F2E4E")
_WRAP = Alignment(wrap_text=True, vertical="top")


def _normalize_label(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"none", "n/a"}:
        return ""
    return text


def _style_header(sheet: Worksheet, column_count: int) -> None:
    for index in range(1, column_count + 1):
        cell = sheet.cell(1, index)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    sheet.auto_filter.ref = f"A1:{get_column_letter(column_count)}1"
    sheet.freeze_panes = "A2"
    sheet.row_dimensions[1].height = 22


def _set_widths(sheet: Worksheet, widths: tuple[int, ...]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def build_workflow_canvas_workbook() -> bytes:
    workbook = Workbook()
    help_sheet = workbook.active
    help_sheet.title = HELP_SHEET
    help_lines = [
        "JET workflow canvas",
        "",
        "Use this workbook to design a context job away from the screen, then upload it in the job builder.",
        "Fill the blue-header sheets. Do not rename the sheet tabs or the Field column.",
        "Empty response cells are ignored. Uploading again replaces the previous canvas block and does not delete the rest of the instructions.",
        "",
        "Workflow sheet",
        "Trigger replaces Description. End state replaces Goal.",
        "Inputs, current-state process, JET intervention, human decision, actions, escalations, and systems are written into Stable instructions.",
        "Role and Output template change only when those cells are filled.",
        "Escalation policy changes only when Escalations / exceptions is exactly never, on_failure, or always_review.",
        "",
        "Decision logic, Baseline measures, and UAT questions",
        "Filled rows are added to the same instructions block so the job can use them at run time.",
        "",
        "This file does not ingest documents into the knowledge base. Contracts, policies, and rate cards still go through ingest or the user request.",
    ]
    for row_index, line in enumerate(help_lines, start=1):
        help_sheet.cell(row_index, 1, line)
    help_sheet.column_dimensions["A"].width = 120
    for row in help_sheet.iter_rows(min_row=1, max_row=len(help_lines), max_col=1):
        row[0].alignment = _WRAP

    workflow = workbook.create_sheet(WORKFLOW_SHEET)
    workflow.append(("Field", "Your response", "Where this goes"))
    for label, hint in _WORKFLOW_ROWS:
        workflow.append((label, "", hint))
    _style_header(workflow, 3)
    _set_widths(workflow, (28, 72, 72))
    for row in workflow.iter_rows(min_row=2, max_row=1 + len(_WORKFLOW_ROWS), max_col=3):
        row[0].font = _LABEL_FONT
        row[0].alignment = _WRAP
        row[1].alignment = _WRAP
        row[2].alignment = _WRAP
        workflow.row_dimensions[row[0].row].height = 36

    decisions = workbook.create_sheet(DECISION_SHEET)
    decisions.append(_DECISION_HEADERS)
    for _ in range(8):
        decisions.append(("", "", "", "", "", ""))
    _style_header(decisions, len(_DECISION_HEADERS))
    _set_widths(decisions, (24, 28, 28, 28, 28, 32))

    measures = workbook.create_sheet(MEASURES_SHEET)
    measures.append(("Measure", "Baseline", "Target", "Actual", "Evidence source"))
    for measure in _MEASURES:
        measures.append((measure, "", "", "", ""))
    _style_header(measures, 5)
    _set_widths(measures, (28, 36, 36, 24, 36))
    for row in measures.iter_rows(min_row=2, max_row=1 + len(_MEASURES), max_col=1):
        row[0].font = _LABEL_FONT

    uat = workbook.create_sheet(UAT_SHEET)
    uat.append(("Question", "Your answer"))
    for question in _UAT_QUESTIONS:
        uat.append((question, ""))
    _style_header(uat, 2)
    _set_widths(uat, (88, 72))
    for row in uat.iter_rows(min_row=2, max_row=1 + len(_UAT_QUESTIONS), max_col=2):
        row[0].alignment = _WRAP
        row[1].alignment = _WRAP
        uat.row_dimensions[row[0].row].height = 32

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _sheet_rows(workbook, title: str) -> list[tuple[object, ...]]:
    if title not in workbook.sheetnames:
        return []
    sheet = workbook[title]
    return [tuple(cell.value for cell in row) for row in sheet.iter_rows(values_only=False)]


def _workflow_responses(rows: list[tuple[object, ...]]) -> dict[str, str]:
    found: dict[str, str] = {}
    expected = {_normalize_label(label): label for label, _hint in _WORKFLOW_ROWS}
    for row in rows[1:]:
        if not row:
            continue
        label = _normalize_label(row[0] if len(row) else "")
        if label not in expected:
            continue
        response = _cell_text(row[1] if len(row) > 1 else "")
        if response:
            found[expected[label]] = response
    return found


def _table_rows(rows: list[tuple[object, ...]], min_cells: int) -> list[list[str]]:
    parsed: list[list[str]] = []
    for row in rows[1:]:
        cells = [_cell_text(value) for value in row[:min_cells]]
        if any(cells[1:]):
            parsed.append(cells)
    return parsed


def _markdown_table(headers: tuple[str, ...], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = len(headers)
    normalized = [(row + [""] * width)[:width] for row in rows]
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(cell.replace("|", "/") for cell in row) + " |" for row in normalized]
    return "\n".join([header, divider, *body])


def _canvas_block(responses: dict[str, str], decisions: list[list[str]], measures: list[list[str]], uat: list[tuple[str, str]]) -> str:
    sections: list[str] = ["## Workflow canvas"]
    narrative_labels = (
        "Trigger",
        "Inputs",
        "Current-state process",
        "JET intervention",
        "Human decision",
        "Actions / outputs",
        "Escalations / exceptions",
        "Systems / integrations",
        "End state",
    )
    for label in narrative_labels:
        text = responses.get(label, "")
        if text:
            sections.append(f"### {label}\n{text}")

    decision_table = _markdown_table(_DECISION_HEADERS, decisions)
    if decision_table:
        sections.append("### Decision intelligence\n" + decision_table)

    measure_table = _markdown_table(
        ("Measure", "Baseline", "Target", "Actual", "Evidence source"),
        measures,
    )
    if measure_table:
        sections.append("### Baseline and pilot measures\n" + measure_table)

    if uat:
        lines = [f"- **{question}** {answer}" for question, answer in uat]
        sections.append("### UAT answers\n" + "\n".join(lines))
    return "\n\n".join(sections)


def merge_canvas_instructions(existing: str, block: str) -> str:
    marked = f"{CANVAS_START}\n{block}\n{CANVAS_END}"
    text = existing or ""
    if CANVAS_START in text and CANVAS_END in text:
        before = text.split(CANVAS_START, 1)[0].rstrip()
        after = text.split(CANVAS_END, 1)[1].lstrip()
        parts = [part for part in (before, marked, after) if part]
        return "\n\n".join(parts)
    if not text.strip():
        return marked
    return f"{text.rstrip()}\n\n{marked}"


def parse_workflow_canvas(payload: bytes, current_stable_instructions: str = "") -> dict[str, Any]:
    if not payload:
        raise ValueError("Upload an .xlsx workflow canvas.")
    if len(payload) > _MAX_WORKBOOK_BYTES:
        raise ValueError("Workflow canvas must be 2 MB or smaller.")
    try:
        workbook = load_workbook(BytesIO(payload), data_only=True, read_only=True)
    except Exception as exc:
        raise ValueError("That file is not a readable .xlsx workbook.") from exc

    try:
        responses = _workflow_responses(_sheet_rows(workbook, WORKFLOW_SHEET))
        decisions = _table_rows(_sheet_rows(workbook, DECISION_SHEET), len(_DECISION_HEADERS))
        measure_rows = _table_rows(_sheet_rows(workbook, MEASURES_SHEET), 5)
        uat_rows = _sheet_rows(workbook, UAT_SHEET)
    finally:
        workbook.close()

    uat: list[tuple[str, str]] = []
    for row in uat_rows[1:]:
        question = _cell_text(row[0] if row else "")
        answer = _cell_text(row[1] if len(row) > 1 else "")
        if question and answer:
            uat.append((question, answer))

    block = _canvas_block(responses, decisions, measure_rows, uat)
    has_direct_fields = any(
        responses.get(label)
        for label in ("Job name", "Trigger", "End state", "Role", "Output template")
    )
    if block == "## Workflow canvas" and not has_direct_fields:
        raise ValueError("The workbook has no filled responses. Fill at least one cell and upload it again.")

    applied: dict[str, Any] = {}
    applied_fields: list[str] = []

    if responses.get("Job name"):
        applied["name"] = responses["Job name"]
        applied_fields.append("name")
    if responses.get("Trigger"):
        applied["description"] = responses["Trigger"]
        applied_fields.append("description")
    if responses.get("End state"):
        applied["goal"] = responses["End state"]
        applied_fields.append("goal")
    if responses.get("Role"):
        applied["roleConfiguration"] = responses["Role"]
        applied_fields.append("roleConfiguration")
    if responses.get("Output template"):
        applied["outputTemplate"] = responses["Output template"]
        applied_fields.append("outputTemplate")

    escalation = _ESCALATION_VALUES.get(_normalize_label(responses.get("Escalations / exceptions", "")))
    if escalation:
        applied["escalationPolicy"] = escalation
        applied_fields.append("escalationPolicy")

    if block != "## Workflow canvas":
        applied["stableInstructions"] = merge_canvas_instructions(current_stable_instructions, block)
        applied_fields.append("stableInstructions")

    applied["appliedFields"] = applied_fields
    return applied
