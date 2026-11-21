"""Local IEEE 830-1998 SRS Word-document export; this module never calls an LLM."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

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
    document.add_paragraph(f"The scope of this software is {project.functionality}.")
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
    document.add_heading("Appendix A. Review Notes", level=1)
    document.add_paragraph("Requirements with Draft or Needs review status are not an approved baseline. Review the associated source evidence before approval.")

    output = BytesIO()
    document.save(output)
    return output.getvalue()
