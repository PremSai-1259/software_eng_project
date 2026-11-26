from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import ApprovalDecision, AgentRun, Project, RequirementUpdate
from app.services.agents import ComplianceRiskAgent, DocumentationAgent, GovernanceSdlcAgent, RequirementsAgent
from app.services.compliance import catalogue as rbi_catalogue
from app.services.documents import chunk_text, extract_text, mask_sensitive
from app.services.knowledge import approved_documents
from app.services.llm import enabled as llm_enabled, provider_mode
from app.services.quality import analyse
from app.services.rag import RagConfigurationError, VectorStore, embedding_provider_configured, provider_configured
from app.services.sdlc import recommend
from app.services.storage import ProjectStore

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env")
# Version 2 can use its own .env, while retaining the existing SE-level Groq
# configuration when the version-specific file has not been created yet.
load_dotenv(ROOT.parent.parent / ".env")
store = ProjectStore()
vector_store = VectorStore()
requirements_agent = RequirementsAgent()
compliance_risk_agent = ComplianceRiskAgent()
documentation_agent = DocumentationAgent()
governance_sdlc_agent = GovernanceSdlcAgent()
FINANCE_SCOPE = re.compile(r"\b(finance|financial|fintech|bank(?:ing)?|credit|debit|loan|lending|mortgage|payment|payroll|insurance|investment|investing|wealth|brokerage|trading|securities|portfolio|accounting|ledger|treasury|remittance|money transfer|fund transfer|wallet|merchant|invoice|billing|reconciliation|underwriting|kyc|aml|deposit|withdrawal|interest rate|forex|currency exchange|tax reporting|financial crime|fraud detection|capital market|financial statement)\b", re.I)
def is_finance_project(text: str) -> bool:
    return bool(FINANCE_SCOPE.search(text))



@asynccontextmanager
async def lifespan(_: FastAPI):
    print("\n" + "=" * 56)
    print("  Finance Helper is running")
    app_port = os.getenv("APP_PORT", "8001")
    print(f"  App:      http://127.0.0.1:{app_port}")
    print("  API docs: http://127.0.0.1:8000/docs")
    print(f"  Generation: {provider_mode()}")
    print("  RAG:      ChromaDB + OpenAI-compatible embeddings")
    print("  Storage:  local JSON project data and ChromaDB vectors")
    print("  Stop:     press Ctrl+C")
    print("=" * 56 + "\n")
    yield
    print("Finance Helper stopped.")


app = FastAPI(title="Finance Helper", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def retrieve_project_evidence(project: Project, query: str) -> list[dict]:
    try:
        return vector_store.retrieve(project.id, query)
    except RagConfigurationError as exc:
        if "vector collection is unavailable" not in str(exc):
            raise
        indexed = vector_store.index(project.id, project.documents)
        store.save(project)
        return vector_store.retrieve(project.id, query)




def audit(project: Project, action: str, detail: str) -> None:
    project.audit_log.append({"at": datetime.now(timezone.utc).isoformat(), "action": action, "detail": detail})


def record_agent_run(project: Project, agent: str, responsibility: str, status: str, output: str) -> None:
    project.agent_runs.append(AgentRun(agent=agent, responsibility=responsibility, status=status, output=output, at=datetime.now(timezone.utc)))
    audit(project, "agent_completed", f"{agent}: {output}")


@app.get("/")
def home() -> HTMLResponse:
    stylesheet = ROOT / "static" / "styles.css"
    script = ROOT / "static" / "app.js"
    asset_version = max(stylesheet.stat().st_mtime_ns, script.stat().st_mtime_ns)
    page = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    page = page.replace("/static/styles.css", f"/static/styles.css?v={asset_version}")
    page = page.replace("/static/app.js", f"/static/app.js?v={asset_version}")
    return HTMLResponse(
        content=page,
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/api/rag/status")
def rag_status() -> JSONResponse:
    return JSONResponse({
        **vector_store.configuration(),
        "embedding_provider_configured": embedding_provider_configured(),
        "generation_provider_configured": provider_configured(),
        "generation_mode": f"{provider_mode()} with evidence validation" if llm_enabled() else "Configure GROQ_API_KEY and/or OPENAI_API_KEY",
        "evidence_policy": "Retrieved content is untrusted evidence; regulatory conclusions require human review.",
    })


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "Finance Helper", "version": app.version})


@app.get("/api/projects")
def list_projects() -> JSONResponse:
    projects = store.list()
    return JSONResponse([{
        "id": project.id, "functionality": project.functionality, "created_at": project.created_at.isoformat(),
        "documents": len(project.documents), "requirements": len(project.requirements),
        "pending_approvals": sum(item.approval_status == "Needs review" for item in project.requirements),
    } for project in projects])


@app.post("/api/projects")
async def create_project(
    project_brief: str = Form(...),
    files: list[UploadFile] = File(default=[]),
) -> JSONResponse:
    project_brief = project_brief.strip()
    if len(project_brief) < 20:
        raise HTTPException(422, "Write a project brief with at least 20 characters.")
    if len(project_brief) > 20000:
        raise HTTPException(413, "The project brief exceeds the 20,000 character limit.")
    brief_text = mask_sensitive(project_brief)
    first_sentence = re.split(r"[.!?\n]", project_brief, maxsplit=1)[0].strip()
    project_title = (first_sentence or project_brief)[:160].strip()
    created_at = datetime.now(timezone.utc).isoformat()
    source_metadata = {
        "jurisdiction": None, "effective_date": None, "version": None,
        "applicability": project_title, "uploaded_by": None, "created_at": created_at,
    }
    documents = [{
        "id": "DOC-001", "name": "Project brief", "source": "Project brief",
        **source_metadata, "document_type": "Project brief",
        "chunks": [chunk.__dict__ for chunk in chunk_text(brief_text)],
    }]
    for upload in files:
        if not upload.filename:
            continue
        content = await upload.read(5_000_001)
        if len(content) > 5_000_000:
            raise HTTPException(413, f"{Path(upload.filename).name} exceeds the 5 MB prototype limit.")
        try:
            text = mask_sensitive(extract_text(upload.filename, content))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(422, f"{Path(upload.filename).name} could not be parsed as a valid document.") from exc
        if not text.strip():
            raise HTTPException(422, f"{Path(upload.filename).name} contains no extractable text.")
        doc_id = f"DOC-{len(documents)+1:03d}"
        documents.append({"id": doc_id, "name": Path(upload.filename).name, "source": Path(upload.filename).name, **source_metadata, "document_type": Path(upload.filename).suffix.lstrip(".").upper(), "chunks": [chunk.__dict__ for chunk in chunk_text(text)]})
    financial_context = " ".join([project_brief] + [chunk.get("text", "") for doc in documents for chunk in doc.get("chunks", [])])
    if not is_finance_project(financial_context):
        raise HTTPException(422, "Not suitable: Finance Helper only accepts projects related to finance or financial services.")
    for reference in approved_documents():
        reference["source"] = reference["name"]
        reference["document_type"] = "RBI reference summary"
        reference["applicability"] = project_title
        reference["uploaded_by"] = "Approved reference pack"
        documents.append(reference)
    project = Project(
        id=uuid4().hex[:12], functionality=project_title, project_brief=brief_text,
        created_at=datetime.now(timezone.utc), documents=documents,
    )
    try:
        indexed_chunks = vector_store.index(project.id, documents)
    except RagConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    store.save(project)
    return JSONResponse({
        "project_id": project.id,
        "documents": [{**{key: doc.get(key) for key in ("id", "name", "source", "jurisdiction", "effective_date", "version", "document_type", "applicability", "uploaded_by", "created_at")}, "chunks": len(doc["chunks"])} for doc in documents],
        "rag": {**vector_store.configuration(), "indexed_chunks": indexed_chunks},
    })

@app.get("/api/projects/{project_id}/retrieval")
def retrieve_evidence(project_id: str, query: str | None = None) -> JSONResponse:
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    search_query = (query or project.project_brief or project.functionality).strip()
    if len(search_query) < 3:
        raise HTTPException(422, "Enter a retrieval query of at least three characters.")
    try:
        evidence = retrieve_project_evidence(project, search_query)
    except RagConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    strongest = max((item["relevance"] for item in evidence), default=0)
    return JSONResponse({"query": search_query, "matches": evidence, "count": len(evidence), "confidence": strongest, "evidence_sufficient": strongest >= 0.12})


@app.post("/api/projects/{project_id}/requirements")
def generate_requirements(project_id: str) -> JSONResponse:
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    try:
        evidence = retrieve_project_evidence(project, project.project_brief or project.functionality)
    except RagConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not evidence:
        raise HTTPException(422, "No retrievable evidence was found in the uploaded documents.")
    if max((item["relevance"] for item in evidence), default=0) < 0.12:
        raise HTTPException(422, "The retrieved sources do not provide sufficient evidence. Add or select a more relevant source before generating requirements.")
    try:
        requirements_agent.run(project, evidence)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc
    compliance_risk_agent.run(project)
    documentation_agent.run(project)
    record_agent_run(project, requirements_agent.name, requirements_agent.responsibility, "Completed", f"Generated {len(project.requirements)} evidence-linked drafts ({requirements_agent.generation_mode}).")
    record_agent_run(project, compliance_risk_agent.name, compliance_risk_agent.responsibility, "Waiting for human review", f"Prepared {len(project.risks)} reviewable risks and {len(project.traceability)} traceability records.")
    record_agent_run(project, documentation_agent.name, documentation_agent.responsibility, "Completed", "Updated evaluation metrics and exportable requirements artefacts.")
    store.save(project)
    return JSONResponse(project.model_dump(mode="json"))


@app.post("/api/projects/{project_id}/sdlc")
def sdlc_analysis(project_id: str) -> JSONResponse:
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    if not project.requirements:
        raise HTTPException(422, "Generate requirements before SDLC analysis.")
    try:
        project.sdlc = governance_sdlc_agent.run(project)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    record_agent_run(project, governance_sdlc_agent.name, governance_sdlc_agent.responsibility, "Waiting for human review", f"Recommended {project.sdlc.recommended_sdlc}; approval remains with the project reviewer.")
    store.save(project)
    return JSONResponse(project.sdlc.model_dump(mode="json"))


@app.post("/api/projects/{project_id}/sdlc/approval")
def update_sdlc_approval(project_id: str, status: str = Form(...)) -> JSONResponse:
    if status not in {"Approved", "Rejected", "Needs review"}:
        raise HTTPException(422, "Invalid SDLC approval status.")
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    if not project.sdlc:
        raise HTTPException(422, "Run the SDLC analysis before recording an approval decision.")
    previous = project.sdlc.approval_status
    project.sdlc.approval_status = status
    project.approvals.append(ApprovalDecision(id=uuid4().hex[:12], subject_type="SDLC", subject_id=project_id, decision=status, reviewer="Local reviewer", reviewer_role="Project reviewer", rationale="", at=datetime.now(timezone.utc)))
    documentation_agent.run(project)
    audit(project, "sdlc_approval", f"{previous} -> {status}")
    store.save(project)
    return JSONResponse(project.sdlc.model_dump(mode="json"))


@app.get("/api/projects/{project_id}")
def get_project(project_id: str) -> JSONResponse:
    try:
        return JSONResponse(store.get(project_id).model_dump(mode="json"))
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc


@app.patch("/api/projects/{project_id}/requirements/{requirement_id}")
def edit_requirement(project_id: str, requirement_id: str, changes: RequirementUpdate) -> JSONResponse:
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    requirement = next((item for item in project.requirements if item.id == requirement_id), None)
    if not requirement:
        raise HTTPException(404, "Requirement not found.")
    updates = changes.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(422, "Provide at least one requirement field to update.")
    before = {key: getattr(requirement, key) for key in updates}
    for key, value in updates.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(requirement, key, value)
    if requirement.approval_status == "Approved":
        requirement.approval_status = "Needs review"
    project.quality_issues = analyse(project.requirements)
    compliance_risk_agent.run(project)
    documentation_agent.run(project)
    store.save(project)
    return JSONResponse(requirement.model_dump(mode="json"))


@app.post("/api/projects/{project_id}/requirements/{requirement_id}/clarification")
def request_clarification(project_id: str, requirement_id: str) -> JSONResponse:
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    requirement = next((item for item in project.requirements if item.id == requirement_id), None)
    if not requirement:
        raise HTTPException(404, "Requirement not found.")
    previous = requirement.approval_status
    requirement.approval_status = "Needs review"
    project.clarification_questions = [f"{requirement_id}: Confirm the expected behavior and measurable acceptance criteria."]
    documentation_agent.run(project)
    audit(project, "clarification_requested", requirement_id)
    store.save(project)
    return JSONResponse({"requirement_id": requirement_id, "status": requirement.approval_status})


@app.get("/api/projects/{project_id}/export")
def export_project(project_id: str) -> JSONResponse:
    try:
        payload = store.export(store.get(project_id))
        return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="finance-helper-{project_id}.json"'})
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc


@app.get("/api/projects/{project_id}/artifacts")
def export_artifacts(project_id: str) -> PlainTextResponse:
    try:
        project = store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc
    if not project.requirements:
        raise HTTPException(422, "Generate requirements before exporting the SRS pack.")
    lines = [
        f"# Software Requirements Specification — {project.functionality}",
        "", "> Advisory draft. Regulatory applicability and all high-impact requirements require authorised human review.",
        "", "## 1. Purpose and scope", "",
        project.business_objective or f"Requirements for {project.functionality}.",
        "", "## 2. Stakeholders and sources", "",
        f"Users and roles: {project.users_and_roles or 'Not recorded; clarify with the project sponsor.'}", "",
    ]
    source_names = sorted({doc.get("name", "Unknown source") for doc in project.documents})
    lines.extend(f"- {name}" for name in source_names)
    lines.extend(["", "## 3. Requirements", ""])
    for requirement in project.requirements:
        citations = ", ".join(f"{item.document_name} ({item.document_id}:{item.chunk_id})" for item in requirement.evidence) or "No evidence linked"
        lines.extend([
            f"### {requirement.id} — {requirement.statement}", "",
            f"- Categories: {', '.join(category.value for category in requirement.categories)}",
            f"- Source stakeholder/document: {requirement.source_stakeholder or 'Not recorded'}",
            f"- Priority: {requirement.priority}; confidence: {requirement.confidence:.0%}",
            f"- Approval: {requirement.approval_status}",
            f"- Business justification: {requirement.business_justification}",
            f"- Applicable policy (unverified): {requirement.applicable_policy or 'Not specified'}",
            f"- Evidence: {citations}", "- Acceptance criteria:",
        ])
        lines.extend(f"  - {item}" for item in requirement.acceptance_criteria or ["Needs definition by the project team."])
        if requirement.assumptions:
            lines.append("- Assumptions: " + "; ".join(requirement.assumptions))
        if requirement.dependencies:
            lines.append("- Dependencies: " + "; ".join(requirement.dependencies))
        lines.append("")
    lines.extend(["## 4. User stories", ""])
    for requirement in project.requirements:
        source = project.users_and_roles or "project user"
        citations = ", ".join(f"{e.document_id}:{e.chunk_id}" for e in requirement.evidence) or "no citation"
        lines.extend([f"- **{requirement.id}:** As a {source}, I need {requirement.statement.rstrip('.')} so that {requirement.business_justification} _(Source: {citations})_", ""])
    lines.extend(["## 5. Use cases", ""])
    for index, requirement in enumerate(project.requirements, start=1):
        citations = ", ".join(f"{e.document_id}:{e.chunk_id}" for e in requirement.evidence) or "no citation"
        lines.extend([
            f"### UC-{index:03d} — {requirement.id}", "",
            f"- Primary actor: {project.users_and_roles or 'To be confirmed'}",
            f"- Goal: {requirement.statement}",
            "- Preconditions: To be confirmed during stakeholder review.",
            "- Main flow: Perform the requirement and validate its acceptance criteria.",
            "- Alternative/error flows: Clarify with stakeholders; no unsupported flow is assumed.",
            f"- Evidence: {citations}", "",
        ])
    lines.extend(["", "## 6. Open issues and assumptions", ""])
    lines.extend(f"- **{issue.severity} — {issue.check} ({issue.requirement_id or 'Project'}):** {issue.message} Suggested action: {issue.recommendation}" for issue in project.quality_issues)
    if not project.quality_issues:
        lines.append("- Run the quality review and confirm unresolved assumptions before baselining.")
    lines.extend(["", "## 7. Delivery approach", ""])
    if project.sdlc:
        lines.append(f"**{project.sdlc.recommended_sdlc} — {project.sdlc.approval_status}.** {project.sdlc.justification}")
        lines.extend(["", "### Project-specific workflow", ""])
        for phase in project.sdlc.workflow:
            lines.append(f"- **{phase.phase}:** {', '.join(phase.activities)} Roles: {', '.join(phase.roles)}. Deliverables: {', '.join(phase.deliverables)}. Gate: {phase.gate}.")
    else:
        lines.append("No SDLC recommendation has been run.")
    return PlainTextResponse("\n".join(lines), media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="finance-helper-srs-{project.id}.md"'})


from app.features import router as feature_router
app.include_router(feature_router)
