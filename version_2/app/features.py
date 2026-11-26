"""Finance Helper Version 2 governance, evaluation, and SRS endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.schemas import AgentRun
from app.services.agents import SrsGenerationAgent
from app.services.compliance import catalogue as rbi_catalogue
from app.services.storage import ProjectStore

router = APIRouter()
store = ProjectStore()
ROOT = Path(__file__).resolve().parent
srs_agent = SrsGenerationAgent()


def _project(project_id: str):
    try:
        return store.get(project_id)
    except KeyError as exc:
        raise HTTPException(404, "Project not found.") from exc


@router.get("/api/knowledge-base/rbi")
def rbi_knowledge_base() -> JSONResponse:
    return JSONResponse({
        "jurisdiction": "India",
        "authority": "Reserve Bank of India",
        "sources": rbi_catalogue(),
        "notice": "Source applicability and legal interpretation require authorised compliance review.",
    })


@router.post("/api/projects/{project_id}/srs")
def generate_srs(project_id: str) -> JSONResponse:
    project = _project(project_id)
    if not project.requirements:
        raise HTTPException(422, "Generate requirements before creating the SRS.")
    output_dir = store.root / "exports" / project.id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "ieee-830-1998-srs.docx"
    output_path.write_bytes(srs_agent.run(project))
    project.agent_runs.append(AgentRun(
        agent=srs_agent.name,
        responsibility=srs_agent.responsibility,
        status="Completed",
        output="Generated a traceable IEEE 830-1998 SRS draft for human review.",
        at=datetime.now(timezone.utc),
    ))
    store.save(project)
    return JSONResponse({"download_url": f"/api/projects/{project.id}/srs/download"})


@router.get("/api/projects/{project_id}/srs/download")
def download_srs(project_id: str) -> FileResponse:
    project = _project(project_id)
    path = store.root / "exports" / project.id / "ieee-830-1998-srs.docx"
    if not path.is_file():
        raise HTTPException(404, "Generate the SRS before downloading it.")
    return FileResponse(path, filename=f"srs-{project.id}.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/api/projects/{project_id}/artefacts")
def get_artefacts(project_id: str) -> JSONResponse:
    project = _project(project_id)
    return JSONResponse(project.artefacts)


@router.get("/api/projects/{project_id}/evaluation")
def get_evaluation(project_id: str) -> JSONResponse:
    project = _project(project_id)
    if project.evaluation is None:
        raise HTTPException(404, "Generate requirements before retrieving evaluation metrics.")
    return JSONResponse(project.evaluation.model_dump(mode="json"))


@router.get("/api/projects/{project_id}/agent-runs")
def get_agent_runs(project_id: str) -> JSONResponse:
    return JSONResponse([item.model_dump(mode="json") for item in _project(project_id).agent_runs])
