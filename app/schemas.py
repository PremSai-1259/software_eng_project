from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Category(StrEnum):
    BUSINESS = "Business"
    STAKEHOLDER = "Stakeholder"
    FUNCTIONAL = "Functional"
    SECURITY = "Security"
    PRIVACY = "Privacy"
    REGULATORY = "Regulatory"
    PERFORMANCE = "Performance"
    AVAILABILITY = "Availability / reliability"
    USABILITY = "Usability"
    DATA = "Data management"
    INTEGRATION = "Integration"
    AUDIT = "Audit / reporting"
    OPERATIONAL = "Operational / maintenance"


class Evidence(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str
    excerpt: str
    relevance: float = Field(ge=0, le=1)


class ComplianceMapping(BaseModel):
    """A reviewable control suggestion, never a legal determination."""

    control_id: str
    source_title: str
    source_url: str
    jurisdiction: str = "India"
    applicability: str
    rationale: str
    human_approval_required: bool = True


class RiskEntry(BaseModel):
    id: str
    requirement_id: str
    title: str
    category: Literal["Security", "Privacy", "Compliance", "Operational", "Integration"]
    level: Literal["Low", "Medium", "High"]
    rationale: str
    mitigation: str
    owner_role: str
    status: Literal["Open", "Accepted", "Mitigated"] = "Open"


class TraceabilityRecord(BaseModel):
    requirement_id: str
    source_document: str
    source_chunk_id: str
    control_ids: list[str] = Field(default_factory=list)
    risk_ids: list[str] = Field(default_factory=list)


class ApprovalDecision(BaseModel):
    id: str
    subject_type: Literal["Requirement", "SDLC", "Compliance mapping", "Release"]
    subject_id: str
    decision: Literal["Approved", "Rejected", "Needs review"]
    reviewer: str
    reviewer_role: str
    rationale: str = ""
    at: datetime


class EvaluationMetrics(BaseModel):
    requirements_count: int = 0
    citation_coverage: float = Field(ge=0, le=1)
    measurable_acceptance_coverage: float = Field(ge=0, le=1)
    rbi_control_coverage: float = Field(ge=0, le=1)
    open_high_issues: int = 0
    open_risks: int = 0
    human_review_coverage: float = Field(ge=0, le=1)
    notes: list[str] = Field(default_factory=list)


class Requirement(BaseModel):
    id: str
    statement: str
    categories: list[Category]
    evidence: list[Evidence] = Field(default_factory=list)
    business_justification: str
    priority: Literal["Must", "Should", "Could"] = "Should"
    dependencies: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    applicable_policy: str | None = None
    compliance_mappings: list[ComplianceMapping] = Field(default_factory=list)
    risk_level: Literal["Low", "Medium", "High"] = "Medium"
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    approval_status: Literal["Draft", "Approved", "Rejected", "Needs review"] = "Draft"


class QualityIssue(BaseModel):
    id: str
    requirement_id: str | None = None
    check: str
    severity: Literal["Low", "Medium", "High"]
    message: str
    recommendation: str


class SdlcFactor(BaseModel):
    name: str
    value: str
    score: int = Field(ge=1, le=5)
    rationale: str
    requirement_ids: list[str] = Field(default_factory=list)


class SdlcOption(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)
    suitability: str


class WorkflowPhase(BaseModel):
    phase: str
    activities: list[str]
    roles: list[str]
    deliverables: list[str]
    gate: str


class SdlcRecommendation(BaseModel):
    recommended_sdlc: str
    factors: list[SdlcFactor]
    options: list[SdlcOption]
    justification: str
    workflow: list[WorkflowPhase]
    human_approval_required: bool = True


class AgentRun(BaseModel):
    agent: str
    responsibility: str
    status: Literal["Completed", "Waiting for human review"]
    output: str
    at: datetime


class Project(BaseModel):
    id: str
    functionality: str
    created_at: datetime
    documents: list[dict] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    quality_issues: list[QualityIssue] = Field(default_factory=list)
    risks: list[RiskEntry] = Field(default_factory=list)
    traceability: list[TraceabilityRecord] = Field(default_factory=list)
    artefacts: dict = Field(default_factory=dict)
    clarification_questions: list[str] = Field(default_factory=list)
    approvals: list[ApprovalDecision] = Field(default_factory=list)
    evaluation: EvaluationMetrics | None = None
    sdlc: SdlcRecommendation | None = None
    agent_runs: list[AgentRun] = Field(default_factory=list)
    audit_log: list[dict] = Field(default_factory=list)
