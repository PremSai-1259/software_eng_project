from app.schemas import Category
from app.services.documents import chunk_text, mask_sensitive, retrieve
from app.services.generator import generate_evidence_drafts
from app.services.quality import analyse
from app.services.sdlc import recommend


def test_pipeline_creates_grounded_requirements_and_recommendation():
    text = "The system shall encrypt personal data. The system must record audit events for every decision."
    chunks = [chunk.__dict__ for chunk in chunk_text(mask_sensitive(text))]
    documents = [{"id": "DOC-001", "name": "policy.txt", "chunks": chunks}]
    evidence = retrieve("personal data and audit", documents)

    requirements = generate_evidence_drafts("customer onboarding", evidence)

    assert requirements
    assert all(requirement.evidence for requirement in requirements)
    assert Category.SECURITY in requirements[0].categories or Category.PRIVACY in requirements[0].categories
    assert isinstance(analyse(requirements), list)
    recommendation = recommend(requirements)
    assert recommendation.options[0].score >= recommendation.options[-1].score
    assert {option.name for option in recommendation.options} == {"Waterfall", "V-Shape", "Prototyping", "RAD", "Spiral", "Incremental", "Agile"}
    assert {factor.name for factor in recommendation.factors} == {"Requirement stability", "Requirement clarity", "Risk", "Complexity", "Need for early prototype", "Time constraints", "Customer involvement", "Frequency of changes", "Need for iterative development", "Need for risk analysis"}


def test_masking_replaces_account_like_values():
    assert "1234567890123456" not in mask_sensitive("Account 1234567890123456 must be protected.")
