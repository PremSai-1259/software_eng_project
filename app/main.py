from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import AgentRun, Project
from app.services.agents import GovernanceSdlcAgent, RequirementsAgent
from app.services.documents import chunk_text, extract_text, mask_sensitive
from app.services.generator import generate_evidence_drafts
from app.services.llm import enabled as llm_enabled, generate_requirements as generate_llm_requirements
from app.services.rag import RagConfigurationError, VectorStore, provider_configured
from app.services.storage import ProjectStore

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env")
store = ProjectStore()
vector_store = VectorStore()
requirements_agent = RequirementsAgent()
governance_sdlc_agent = GovernanceSdlcAgent()


@asynccontextmanager
async def lifespan(_: FastAPI):
    print("\n" + "=" * 56)
    print("  FinReq Studio is running")
    print("  App:      http://127.0.0.1:8000")
    print("  API docs: http://127.0.0.1:8000/docs")
    print("  RAG:      ChromaDB + OpenAI-compatible embeddings")
    print("  Storage:  local JSON project data and ChromaDB vectors")
    print("  Stop:     press Ctrl+C")
    print("=" * 56 + "\n")
    yield
    print("FinReq Studio stopped.")


app = FastAPI(title="FinReq Studio", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def audit(project: Project, action: str, detail: str) -> None:
    project.audit_log.append({"at": datetime.now(timezone.utc).isoformat(), "action": action, "detail": detail})


def record_agent_run(project: Project, agent: str, responsibility: str, status: str, output: str) -> None:
    project.agent_runs.append(AgentRun(
        agent=agent, responsibility=responsibility, status=status, output=output,
        at=datetime.now(timezone.utc),
    ))
    audit(project, "agent_completed", f"{agent}: {output}")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(ROOT / "templates" / "index.html")


@app.get("/api/rag/status")
def rag_status() -> JSONResponse:
    return JSONResponse({
        **vector_store.configuration(),
        "embedding_provider_configured": provider_configured(),
        "generation_mode": "LLM generation with citation validation" if llm_enabled() else "Evidence-only drafts until LLM_API_KEY is configured",
    })


@app.post("/api/projects")
async def create_project(
    functionality: str = Form(...),
    stakeholder_input: str = Form("{}"),
    files: list[UploadFile] = File(default=[]),
) -> JSONResponse:
    functionality = functionality.strip()
    if len(functionality) < 3:
        raise HTTPException(422, "Enter a financial functionality of at least three characters.")
    try:
        answers = json.loads(stakeholder_input)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, "Stakeholder answers could not be processed.") from exc
    if not isinstance(answers, dict):
        raise HTTPException(422, "Stakeholder answers must be a structured set of responses.")
    answers = {str(question): str(answer).strip() for question, answer in answers.items() if str(answer).strip()}
    uploads = [upload for upload in files if upload.filename]
    if not answers and not uploads:
        raise HTTPException(422, "Answer at least one stakeholder question or upload a supporting document.")
    documents = []
    if answers:
        interview_text = "\n".join(f"{question}: {answer}" for question, answer in answers.items())
        masked_text = mask_sensitive(interview_text)
        documents.append({"id": "DOC-001", "name": "Stakeholder interview", "chunks": [chunk.__dict__ for chunk in chunk_text(masked_text)]})
    for upload in uploads:
        content = await upload.read()
        if len(content) > 5_000_000:
            raise HTTPException(413, f"{upload.filename} exceeds the 5 MB prototype limit.")
        try:
            text = mask_sensitive(extract_text(upload.filename, content))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not text.strip():
            raise HTTPException(422, f"{upload.filename} contains no extractable text.")
        doc_id = f"DOC-{len(documents)+1:03d}"
        documents.append({"id": doc_id, "name": upload.filename, "chunks": [chunk.__dict__ for chunk in chunk_text(text)]})
    project = Project(id=uuid4().hex[:12], functionality=functionality, created_at=datetime.now(timezone.utc), documents=documents)
    try:
        indexed_chunks = vector_store.index(project.id, documents)
    except RagConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    audit(project, "sources_recorded", f"Stored {len(documents)} masked source(s): {len(answers)} stakeholder response(s) and {len(uploads)} uploaded document(s).")
    audit(project, "rag_indexed", f"Indexed {indexed_chunks} source chunk(s) in ChromaDB.")
    store.save(project)
    return JSONResponse({
        "project_id": project.id,
        "documents": [{"id": doc["id"], "name": doc["name"], "chunks": len(doc["chunks"])} for doc in documents],
        "rag": {**vector_store.configuration(), "indexed_chunks": indexed_chunks},
    })


@app.get("/api/projects/{project_id}/retrieval")
def retrieve_evidence(project_id: str, query: str | None = None) -> JSONResponse:
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    search_query = (query or project.functionality).strip()
    if len(search_query) < 3:
        raise HTTPException(422, "Enter a retrieval query of at least three characters.")
    try:
        evidence = vector_store.retrieve(project.id, search_query)
    except RagConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    return JSONResponse({"query": search_query, "matches": evidence, "count": len(evidence)})


@app.post("/api/projects/{project_id}/requirements")
def generate_requirements(project_id: str) -> JSONResponse:
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    try:
        evidence = vector_store.retrieve(project.id, project.functionality)
    except RagConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not evidence:
        raise HTTPException(422, "No retrievable evidence was found in the uploaded documents.")
    generation_mode = "evidence-only"
    if llm_enabled():
        try:
            generated_requirements = generate_llm_requirements(project.functionality, evidence)
            generation_mode = "LLM-assisted"
        except (RuntimeError, ValueError) as exc:
            generated_requirements = generate_evidence_drafts(project.functionality, evidence)
            audit(project, "llm_fallback", str(exc))
    else:
        generated_requirements = generate_evidence_drafts(project.functionality, evidence)
    project.requirements = requirements_agent.run(project, evidence, generated_requirements)
    record_agent_run(
        project, requirements_agent.name, requirements_agent.responsibility, "Waiting for human review",
        f"Generated {len(project.requirements)} {generation_mode} RAG-grounded draft requirement(s) and found {len(project.quality_issues)} quality issue(s).",
    )
    store.save(project)
    return JSONResponse(project.model_dump(mode="json"))


@app.post("/api/projects/{project_id}/requirements/{requirement_id}/approval")
def update_approval(project_id: str, requirement_id: str, status: str = Form(...)) -> JSONResponse:
    if status not in {"Approved", "Rejected", "Needs review", "Draft"}:
        raise HTTPException(422, "Invalid approval status.")
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    requirement = next((item for item in project.requirements if item.id == requirement_id), None)
    if not requirement:
        raise HTTPException(404, "Requirement not found.")
    requirement.approval_status = status
    audit(project, "requirement_approval_updated", f"{requirement_id} marked {status}.")
    store.save(project)
    return JSONResponse(requirement.model_dump(mode="json"))


@app.post("/api/projects/{project_id}/sdlc")
def sdlc_analysis(project_id: str) -> JSONResponse:
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    if not project.requirements:
        raise HTTPException(422, "Generate requirements before SDLC analysis.")
    project.sdlc = governance_sdlc_agent.run(project)
    record_agent_run(
        project, governance_sdlc_agent.name, governance_sdlc_agent.responsibility, "Waiting for human review",
        f"Recommended {project.sdlc.recommended_sdlc}; human approval remains required.",
    )
    store.save(project)
    return JSONResponse(project.sdlc.model_dump(mode="json"))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> JSONResponse:
    try:
        return JSONResponse(store.get(project_id).model_dump(mode="json"))
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc


@app.get("/api/projects/{project_id}/export")
def export_project(project_id: str) -> JSONResponse:
    try:
        return JSONResponse(store.export(store.get(project_id)), headers={"Content-Disposition": f'attachment; filename="finreq-{project_id}.json"'})
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
