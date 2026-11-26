"""Local IEEE 830-1998 SRS Word-document export; this module never calls an LLM."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
import re
import textwrap

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from app.schemas import Project, Requirement


def _add_requirement(document: Document, requirement: Requirement) -> None:
    document.add_heading(f"{requirement.id} — {requirement.statement}", level=3)
    document.add_paragraph(f"Priority: {requirement.priority} | Status: {requirement.approval_status} | Risk: {requirement.risk_level}")
    document.add_paragraph(f"Rationale: {requirement.business_justification}")
    if requirement.acceptance_criteria:
        document.add_paragraph("Acceptance criteria:")
        for criterion in requirement.acceptance_criteria:
            document.add_paragraph(criterion, style="List Bullet")
    if requirement.assumptions:
        document.add_paragraph(f"Assumptions: {'; '.join(requirement.assumptions)}")
    if requirement.dependencies:
        document.add_paragraph(f"Dependencies: {'; '.join(requirement.dependencies)}")
    sources = sorted({f"{item.document_name} / {item.chunk_id}" for item in requirement.evidence})
    if sources:
        document.add_paragraph(f"Source traceability: {'; '.join(sources)}")


def _add_group(document: Document, requirements: list[Requirement], empty_message: str) -> None:
    if requirements:
        for requirement in requirements:
            _add_requirement(document, requirement)
    else:
        document.add_paragraph(empty_message)


def _short(text: str, limit: int = 76) -> str:
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if len(text) <= limit:
        return text
    return text[: limit - 3].rsplit(" ", 1)[0] + "..."


def _use_case_label(statement: str, limit: int = 32) -> str:
    text = re.sub(r"\s+", " ", statement).strip().rstrip(".")
    text = re.sub(r"^(?:the\s+)?(?:system|application|platform)\s+(?:shall|must|should|will)\s+(?:allow|enable)\s+.*?\bto\s+", "", text, flags=re.I)
    text = re.sub(
        r"^(?:the\s+)?(?:system|application|platform)\s+(?:shall|must|should|will)\s+let\s+.*?\b(submit|review|record|update|view|manage|approve|reject|track|create|upload|download|search|generate|receive|process|check|verify|maintain|transfer|pay|apply|open|close|delete|edit)\s+",
        r"\1 ", text, flags=re.I,
    )
    text = re.sub(r"^(?:the\s+)?(?:system|application|platform)\s+(?:shall|must|should|will)\s+", "", text, flags=re.I)
    text = text[:1].upper() + text[1:] if text else "Use the system"
    return _short(text, limit)


def _add_diagram(document: Document, lines: list[str]) -> None:
    """Render one tidy, editable monospaced UML figure directly in Word."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    paragraph = document.add_paragraph()
    paragraph.paragraph_format.left_indent = Inches(0.08)
    paragraph.paragraph_format.right_indent = Inches(0.08)
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(10)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.keep_together = True
    p_pr = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), "F4F8F6")
    p_pr.append(shading)
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "left", "bottom", "right"):
        border = OxmlElement(f"w:{edge}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "6")
        border.set(qn("w:space"), "5")
        border.set(qn("w:color"), "B8CEC5")
        borders.append(border)
    p_pr.append(borders)

    for index, line in enumerate(lines):
        if index:
            paragraph.add_run().add_break()
        run = paragraph.add_run(line or " ")
        run.font.name = "Courier New"
        run.font.size = Pt(8.5)
        run.font.color.rgb = RGBColor(28, 63, 55)
        text_node = run._r.find(qn("w:t"))
        if text_node is not None:
            text_node.set(qn("xml:space"), "preserve")


def _add_uml_diagrams(document: Document, project: Project, functional: list[Requirement]) -> None:
    """Add compact, editable Word-native UML views derived from saved project data."""
    document.add_heading("4. UML Diagrams", level=1)
    document.add_paragraph(
        "These diagrams are draft models generated from the project brief, user roles, and functional requirements. "
        "Where the source does not define actors, interactions, or states, the diagram labels that flow as conceptual and it must be validated by stakeholders."
    )

    # Use case view: actors are outside the system boundary and each use case
    # is drawn as an oval, using plain Word text rather than a table.
    actors = [part.strip() for part in re.split(r"[,;\n/]+", project.users_and_roles or "") if part.strip()]
    actors = actors[:3] or ["Project user (confirm role)"]
    use_cases = [_short(item.statement) for item in functional[:6]]
    if not use_cases:
        use_cases = [_short(project.functionality or project.project_brief or "Use the application")]
    document.add_heading("4.1 Use case diagram", level=2)
    actor_labels = [f"<<actor>> {_short(actor, 20)}" for actor in actors]
    box_indent = 40
    box_width = 42
    lines = [f"Use case diagram - {_short(project.functionality or 'Project system', 48)}", ""]
    lines.append(" " * box_indent + "+" + "-" * box_width + "+")
    lines.append(" " * box_indent + "|" + f"  SYSTEM: {_short(project.functionality or 'Project system', 30)}".ljust(box_width) + "|")
    lines.append(" " * box_indent + "|" + " " * box_width + "|")
    lines.extend(f"{label:<30}--+" for label in actor_labels)
    lines.append(" " * 32 + "|")
    for case in use_cases:
        use_case_label = f"  (( {_use_case_label(case, 32)} ))"
        lines.append(" " * 32 + "+------>|" + use_case_label.ljust(box_width) + "|")
    lines.append(" " * box_indent + "+" + "-" * box_width + "+")
    _add_diagram(document, lines)
    document.add_paragraph("Use cases come from functional requirements; confirm which roles may perform each action.")

    # A concise sequence view. It shows the user-to-system interaction pattern
    # and uses requirement statements for the operation labels.
    document.add_heading("4.2 Sequence diagram", level=2)
    primary_actor = _short(actors[0], 36)
    system = _short(project.functionality or "Project system", 48)
    operation = _use_case_label(functional[0].statement, 32) if functional else f"Request: {_short(project.functionality or 'use the system', 25)}"
    line_width = 83
    left_lifeline = 12
    right_lifeline = 54
    request_prefix = "|--- " + _short(operation, 32) + " "
    request_padding = right_lifeline - left_lifeline + 1 - len(request_prefix) - 3
    request_line = " " * left_lifeline + request_prefix + "-" * max(1, request_padding) + "->|"
    response_label = " result / status "
    response_padding = right_lifeline - left_lifeline + 1 - 3 - len(response_label) - 1
    response_line = " " * left_lifeline + "|<-" + "-" * max(1, response_padding) + response_label + "|"
    lines = [
        "Sequence diagram - conceptual request interaction",
        f"{primary_actor[:25]:^25}{system[:25]:^58}",
        " " * left_lifeline + "|" + " " * (right_lifeline - left_lifeline - 1) + "|",
        " " * left_lifeline + "|" + " " * (right_lifeline - left_lifeline - 1) + "|",
        request_line[:line_width],
        " " * left_lifeline + "|" + " " * (right_lifeline - left_lifeline - 1) + "|",
        response_line[:line_width],
        " " * left_lifeline + "|" + " " * (right_lifeline - left_lifeline - 1) + "|",
    ]
    _add_diagram(document, lines)
    document.add_paragraph("Conceptual interaction: service calls, external systems, and error paths were not specified unless listed in the requirements.")

    # State view is explicitly a conceptual lifecycle because the brief may not
    # specify domain states. Keep paths editable in the generated document.
    document.add_heading("4.3 State diagram", level=2)
    lines = [
        "State diagram - conceptual request lifecycle",
        "",
        "[*] --> [Draft] --> [Submitted] --> [In progress] --> [Completed] --> [*]",
        "                                      |",
        "                                      +--> [Rejected] --> [*]",
        "                                      +--> [Needs correction] --> [Draft]",
    ]
    _add_diagram(document, lines)
    document.add_paragraph("Conceptual state flow for a submitted project request. Confirm state names, transitions, and failure handling with stakeholders.")


def create_ieee_830_document(project: Project) -> bytes:
    """Create an IEEE 830-1998-formatted draft from saved, non-rejected requirements."""
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(10)

    title = document.add_heading("Software Requirements Specification", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle = document.add_paragraph(project.functionality)
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].bold = True
    note = document.add_paragraph("IEEE 830-1998 format — Draft for human review")
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    document.add_paragraph(f"Generated: {datetime.now().strftime('%d %B %Y')}")

    active = [item for item in project.requirements if item.approval_status != "Rejected"]
    functional = [item for item in active if any(str(category) == "Functional" for category in item.categories)]
    interfaces = [item for item in active if any(str(category) == "Integration" for category in item.categories)]
    performance = [item for item in active if any(str(category) in {"Performance", "Availability / reliability"} for category in item.categories)]
    constraints = [item for item in active if any(str(category) == "Regulatory" for category in item.categories)]
    allocated_ids = {item.id for item in functional + interfaces + performance + constraints}
    attributes = [item for item in active if item.id not in allocated_ids]
    references = sorted({item.document_name for requirement in active for item in requirement.evidence})

    document.add_heading("1. Introduction", level=1)
    document.add_heading("1.1 Purpose", level=2)
    document.add_paragraph(f"This SRS specifies the recorded requirements for {project.functionality}. It is a generated draft and requires human review before approval.")
    document.add_heading("1.2 Scope", level=2)
    document.add_paragraph(project.project_brief or f"The scope of this software is {project.functionality}.")
    document.add_heading("1.3 Definitions, Acronyms, and Abbreviations", level=2)
    document.add_paragraph("SRS: Software Requirements Specification. RBI: Reserve Bank of India. KYC: Know Your Customer, where applicable.")
    document.add_heading("1.4 References", level=2)
    _add_group(document, [], "No source references were available.") if not references else [document.add_paragraph(reference, style="List Bullet") for reference in references]
    document.add_heading("1.5 Overview", level=2)
    document.add_paragraph("Section 2 describes the system context. Section 3 provides the specific requirements and their traceability.")

    document.add_heading("2. Overall Description", level=1)
    document.add_heading("2.1 Product Perspective", level=2)
    document.add_paragraph("The system is defined from stakeholder input and supplied project sources.")
    document.add_heading("2.2 Product Functions", level=2)
    selected_sdlc = project.sdlc.recommended_sdlc if project.sdlc else "Not selected"
    document.add_paragraph(f"The selected SDLC model is {selected_sdlc}. The system functions are specified in Section 3.")
    document.add_heading("2.3 User Characteristics", level=2)
    document.add_paragraph("User roles and characteristics are to be confirmed through stakeholder review.")
    document.add_heading("2.4 Constraints", level=2)
    document.add_paragraph("Regulatory, security, integration, and delivery constraints are documented in the specific requirements.")
    document.add_heading("2.5 Assumptions and Dependencies", level=2)
    document.add_paragraph("Requirement-level assumptions and dependencies are listed with the related requirement in Section 3.")

    document.add_heading("3. Specific Requirements", level=1)
    document.add_heading("3.1 Functional Requirements", level=2)
    _add_group(document, functional, "No functional requirements are currently recorded.")
    document.add_heading("3.2 External Interface Requirements", level=2)
    _add_group(document, interfaces, "No external interface requirements are currently recorded.")
    document.add_heading("3.3 Performance Requirements", level=2)
    _add_group(document, performance, "No performance or reliability requirements are currently recorded.")
    document.add_heading("3.4 Design Constraints", level=2)
    _add_group(document, constraints, "No design constraints are currently recorded.")
    document.add_heading("3.5 Software System Attributes", level=2)
    _add_group(document, attributes, "No additional quality, security, privacy, audit, or operational requirements are currently recorded.")
    _add_uml_diagrams(document, project, functional)
    document.add_heading("Appendix A. Review Notes", level=1)
    document.add_paragraph("Requirements with Draft or Needs review status are not an approved baseline. Review the associated source evidence before approval.")

    output = BytesIO()
    document.save(output)
    return output.getvalue()
