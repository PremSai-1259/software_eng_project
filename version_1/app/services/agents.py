"""The staged multi-agent workflow used by FinReq Studio.

Specialised agents extract requirements, assess compliance/risk, derive
artefacts, and recommend an SDLC. They never approve requirements or make a
legal determination; those decisions remain with human reviewers.
"""
from __future__ import annotations

from app.schemas import Project, Requirement, SdlcRecommendation
from app.services.generator import generate_evidence_drafts
from app.services.quality import analyse, clarification_questions
from app.services.sdlc import recommend
from app.services.compliance import analyse as analyse_compliance
from app.services.artefacts import build as build_artefacts
from app.services.evaluation import measure


class RequirementsAgent:
    """Extracts, classifies, and quality-checks evidence-grounded requirements."""

    name = "Requirements Agent"
    responsibility = "Requirement extraction, classification, traceability, and quality review"

    def run(self, project: Project, evidence: list[dict], requirements: list[Requirement] | None = None) -> list[Requirement]:
        project.requirements = requirements or generate_evidence_drafts(project.functionality, evidence)
        project.quality_issues = analyse(project.requirements)
        project.clarification_questions = clarification_questions(project.quality_issues)
        return project.requirements


class ComplianceRiskAgent:
    """Maps prototype RBI controls and raises reviewable risk entries."""

    name = "Compliance & Risk Agent"
    responsibility = "RBI control mapping, risk register generation, and traceability"

    def run(self, project: Project) -> None:
        project.risks, project.traceability = analyse_compliance(project.requirements)


class DocumentationAgent:
    """Produces derived artefacts without inventing uncited requirements."""

    name = "Documentation Agent"
    responsibility = "SRS, user-story, use-case, traceability, risk, and open-issue artefacts"

    def run(self, project: Project) -> None:
        project.evaluation = measure(project)
        project.artefacts = build_artefacts(project)


class GovernanceSdlcAgent:
    """Assesses risk/control signals and produces a transparent SDLC advisory."""

    name = "Governance & SDLC Agent"
    responsibility = "Risk and control assessment, SDLC ranking, and approval-gate planning"

    def run(self, project: Project) -> SdlcRecommendation:
        # Requirements are retrieved from the most relevant chunks, while SDLC
        # evidence (for example delivery gates and test strategy) can be in a
        # different stakeholder-answer chunk. Include the complete masked
        # project evidence without inventing any new project facts.
        project_context = " ".join(
            chunk.get("text", "")
            for document in project.documents
            for chunk in document.get("chunks", [])
        )
        project.sdlc = recommend(project.requirements, project_context)
        return project.sdlc
