"""Reviewable RBI control catalogue and deterministic requirement mapping.

This is intentionally a small, versioned catalogue for a digital-onboarding
prototype.  It is not a substitute for an institution's approved legal corpus
or a compliance/legal decision.
"""
from __future__ import annotations

from app.schemas import Category, ComplianceMapping, Requirement, RiskEntry, TraceabilityRecord


RBI_CONTROLS = [
    {
        "id": "RBI-KYC-CDD", "title": "RBI Master Direction – Know Your Customer (KYC), 2016",
        "url": "https://www.rbi.org.in/commonman/Upload/English/Notification/PDFs/MD18KYCF6E92C82E1E1419D87323E3869BC9F13.pdf",
        "version": "Updated 6 November 2024", "terms": ("kyc", "identity", "customer due diligence", "cdd", "onboarding", "verification"),
        "applicability": "Confirm applicability to the regulated entity and customer/onboarding flow.",
        "control": "Customer due diligence, KYC record handling, and required review/approval checkpoints.",
    },
    {
        "id": "RBI-ITG-2023", "title": "RBI IT Governance, Risk, Controls and Assurance Practices Directions, 2023",
        "url": "https://systemhealth.rbi.org.in/Scripts/BS_ViewMasDirections.aspx_id%3D12562%283%29.html",
        "version": "Effective 1 April 2024", "terms": ("audit", "availability", "recovery", "security", "access", "risk", "incident", "governance"),
        "applicability": "Confirm regulated-entity scope and the system's materiality classification.",
        "control": "IT governance, risk management, assurance, continuity, and audit evidence.",
    },
    {
        "id": "RBI-DPSC-2021", "title": "RBI Master Direction on Digital Payment Security Controls",
        "url": "https://systemhealth.rbi.org.in/Scripts/BS_ViewMasDirections.aspx_id%3D12032%283%29.html",
        "version": "18 February 2021", "terms": ("payment", "transaction", "authentication", "mfa", "fraud", "credential", "reconciliation"),
        "applicability": "Confirm that the product/channel is within the Direction's regulated-entity scope.",
        "control": "Authentication, fraud-risk management, application security lifecycle, and reconciliation controls.",
    },
]


def catalogue() -> list[dict]:
    """Safe metadata for the approved-source register displayed/exported by the app."""
    return [{key: item[key] for key in ("id", "title", "url", "version", "applicability", "control")} for item in RBI_CONTROLS]


def map_requirement(requirement: Requirement) -> list[ComplianceMapping]:
    haystack = " ".join([requirement.statement, *[category.value for category in requirement.categories]]).lower()
    mappings = []
    for control in RBI_CONTROLS:
        if any(term in haystack for term in control["terms"]):
            mappings.append(ComplianceMapping(
                control_id=control["id"], source_title=f"{control['title']} ({control['version']})",
                source_url=control["url"], applicability=control["applicability"], rationale=control["control"],
            ))
    return mappings


def analyse(requirements: list[Requirement]) -> tuple[list[RiskEntry], list[TraceabilityRecord]]:
    risks: list[RiskEntry] = []
    traceability: list[TraceabilityRecord] = []
    risk_categories = {
        Category.SECURITY: ("Security", "High", "Security controls require security-owner approval."),
        Category.PRIVACY: ("Privacy", "High", "Personal-data handling requires privacy and compliance review."),
        Category.REGULATORY: ("Compliance", "High", "Regulatory applicability must be confirmed by compliance."),
        Category.AUDIT: ("Compliance", "Medium", "Auditability and retained evidence require control-owner review."),
        Category.INTEGRATION: ("Integration", "Medium", "External or legacy interfaces require resilience and ownership review."),
    }
    for requirement in requirements:
        requirement.compliance_mappings = map_requirement(requirement)
        if requirement.compliance_mappings and not requirement.applicable_policy:
            requirement.applicable_policy = "; ".join(item.control_id for item in requirement.compliance_mappings)
        for category in requirement.categories:
            if category not in risk_categories:
                continue
            kind, level, rationale = risk_categories[category]
            risk_id = f"RISK-{len(risks) + 1:03d}"
            risks.append(RiskEntry(id=risk_id, requirement_id=requirement.id, title=f"{kind} risk for {requirement.id}", category=kind, level=level, rationale=rationale, mitigation="Define a measurable control, test evidence, accountable owner, and approval gate.", owner_role="Compliance officer" if kind in {"Compliance", "Privacy"} else "Security / technical owner"))
        for evidence in requirement.evidence:
            traceability.append(TraceabilityRecord(requirement_id=requirement.id, source_document=evidence.document_name, source_chunk_id=evidence.chunk_id, control_ids=[mapping.control_id for mapping in requirement.compliance_mappings], risk_ids=[risk.id for risk in risks if risk.requirement_id == requirement.id]))
    return risks, traceability
