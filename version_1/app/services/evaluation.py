"""Transparent prototype-quality metrics, not a substitute for a formal study."""
from __future__ import annotations

from app.schemas import EvaluationMetrics, Project


def measure(project: Project) -> EvaluationMetrics:
    requirements = project.requirements
    total = len(requirements)
    ratio = lambda count: round(count / total, 2) if total else 0.0
    measurable = sum(bool(item.acceptance_criteria) and not any("reviewer" in criterion.lower() for criterion in item.acceptance_criteria) for item in requirements)
    reviewed = sum(item.approval_status in {"Approved", "Rejected"} for item in requirements)
    metrics = EvaluationMetrics(
        requirements_count=total,
        citation_coverage=ratio(sum(bool(item.evidence) for item in requirements)),
        measurable_acceptance_coverage=ratio(measurable),
        rbi_control_coverage=ratio(sum(bool(item.compliance_mappings) for item in requirements)),
        open_high_issues=sum(item.severity == "High" for item in project.quality_issues),
        open_risks=sum(item.status == "Open" for item in project.risks),
        human_review_coverage=ratio(reviewed),
    )
    if not total:
        metrics.notes.append("No requirements have been generated.")
    if metrics.citation_coverage < 1:
        metrics.notes.append("Do not baseline uncited requirements.")
    if metrics.open_high_issues:
        metrics.notes.append("Resolve high-severity quality issues before approval.")
    if metrics.human_review_coverage < 1:
        metrics.notes.append("Human review is incomplete.")
    return metrics
