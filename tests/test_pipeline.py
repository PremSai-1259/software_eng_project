from app.schemas import Category
from app.services.documents import chunk_text, mask_sensitive, retrieve
from app.services.generator import generate_evidence_drafts
from app.services.quality import analyse
from io import BytesIO
from urllib.error import HTTPError

from app.services import rag
from app.services.rag import RagConfigurationError, VectorStore, _api_key, _embed, provider_configured
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


def test_rag_requires_explicit_provider_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    try:
        _api_key()
    except RagConfigurationError:
        return
    raise AssertionError("RAG must not run without an embedding-provider key")


def test_rag_configuration_never_exposes_api_key(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "not-for-the-client")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    configuration = VectorStore.configuration()

    assert configuration["vector_database"] == "ChromaDB"
    assert configuration["llm_model"] == "test-model"
    assert "not-for-the-client" not in str(configuration)


def test_rag_uses_local_embeddings_without_provider_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    vectors = _embed(["identity verification requires an audit record"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 384
    assert any(vectors[0])


def test_rag_falls_back_to_local_embeddings_when_provider_rejects_request(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    def rejected_request(*_args, **_kwargs):
        raise HTTPError("https://example.invalid/v1/embeddings", 404, "Not Found", {}, BytesIO())

    monkeypatch.setattr(rag, "urlopen", rejected_request)

    vectors = rag._embed(["Identity verification requires an audit record."])

    assert len(vectors) == 1
    assert len(vectors[0]) == 384
    assert any(vectors[0])


def test_openai_api_key_environment_variable_is_supported(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert provider_configured()
    assert _api_key() == "test-key"


def test_project_creation_works_without_provider_key(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.services.storage import ProjectStore

    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "projects"))
    from app import main

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(main, "vector_store", VectorStore())
    monkeypatch.setattr(main, "store", ProjectStore())
    client = TestClient(main.app)
    response = client.post(
        "/api/projects",
        data={"functionality": "Digital customer onboarding", "stakeholder_input": '{"identity": "Verify identity and record each decision."}'},
    )

    assert response.status_code == 200
    assert response.json()["rag"]["vector_database"] == "ChromaDB"
