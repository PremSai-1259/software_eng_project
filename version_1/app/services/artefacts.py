"""Derived, exportable requirement-engineering artefacts."""
from __future__ import annotations

from app.schemas import Project


def build(project: Project) -> dict:
    requirements = project.requirements
    return {
        "srs": {"title": f"Software Requirements Specification: {project.functionality}", "requirements": [item.model_dump(mode="json") for item in requirements]},
        "user_stories": [{"id": f"US-{item.id.removeprefix('REQ-')}", "story": f"As a relevant stakeholder, I want {item.statement[0].lower() + item.statement[1:]} so that {item.business_justification}", "acceptance_criteria": item.acceptance_criteria, "requirement_id": item.id} for item in requirements],
        "use_cases": [{"id": f"UC-{item.id.removeprefix('REQ-')}", "name": item.statement[:100], "actors": "To be confirmed by stakeholder", "preconditions": item.assumptions, "success_criteria": item.acceptance_criteria, "requirement_id": item.id} for item in requirements],
        "risk_register": [item.model_dump(mode="json") for item in project.risks],
        "traceability_matrix": [item.model_dump(mode="json") for item in project.traceability],
        "assumptions_and_dependencies": [{"requirement_id": item.id, "assumptions": item.assumptions, "dependencies": item.dependencies} for item in requirements],
        "open_issues": [item.model_dump(mode="json") for item in project.quality_issues if item.severity in {"High", "Medium"}],
        "compliance_control_matrix": [{"requirement_id": item.id, "mappings": [mapping.model_dump(mode="json") for mapping in item.compliance_mappings]} for item in requirements],
        "clarification_queue": project.clarification_questions,
        "approval_register": [item.model_dump(mode="json") for item in project.approvals],
        "evaluation": project.evaluation.model_dump(mode="json") if project.evaluation else None,
    }
