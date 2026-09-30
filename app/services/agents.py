"""The two-agent workflow used by FinReq Studio.

The agents are deliberately narrow: the first creates traceable requirement
drafts, while the second assesses their governance implications and recommends
an SDLC.  Neither agent approves a requirement or makes a legal determination.
"""
from __future__ import annotations

from app.schemas import Project, Requirement, SdlcRecommendation
from app.services.generator import generate_evidence_drafts
from app.services.quality import analyse
from app.services.sdlc import recommend


class RequirementsAgent:
    """Extracts, classifies, and quality-checks evidence-grounded requirements."""

    name = "Requirements Agent"
    responsibility = "Requirement extraction, classification, traceability, and quality review"

    def run(self, project: Project, evidence: list[dict], requirements: list[Requirement] | None = None) -> list[Requirement]:
        project.requirements = requirements or generate_evidence_drafts(project.functionality, evidence)
        project.quality_issues = analyse(project.requirements)
        return project.requirements


class GovernanceSdlcAgent:
    """Assesses risk/control signals and produces a transparent SDLC advisory."""

    name = "Governance & SDLC Agent"
    responsibility = "Risk and control assessment, SDLC ranking, and approval-gate planning"

    def run(self, project: Project) -> SdlcRecommendation:
        project.sdlc = recommend(project.requirements)
        return project.sdlc
