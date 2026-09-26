# FinReq Studio

FinReq Studio is a financial requirements engineering prototype built around a complete Retrieval-Augmented Generation (RAG) workflow. It turns stakeholder responses and supporting documents into traceable draft requirements, highlights quality risks, and recommends an SDLC approach for human review.

## Highlights

- Adaptive stakeholder interview for onboarding, payments, loans, fraud, insurance, and reporting workflows.
- Upload and process `.txt`, `.md`, `.csv`, `.pdf`, and `.docx` source documents.
- Mask common account/card, tax-ID, and national-ID-like patterns before indexing.
- Store embeddings in a persistent, per-project ChromaDB collection.
- Inspect retrieved evidence before generating requirements.
- Generate requirements with citations to the retrieved source chunks.
- Review deterministic quality findings and approve, reject, or return requirements for review.
- Produce a transparent SDLC recommendation and export the complete project audit trail as JSON.

## RAG Flow

```text
Stakeholder interview + uploaded documents
              |
       Mask sensitive patterns
              |
          Chunk sources
              |
     Create embeddings and index
              |
     ChromaDB semantic retrieval
              |
  LLM or evidence-only requirement drafts
              |
 Quality review + SDLC recommendation + export
```

Every requirement is linked to retrieved evidence. Requirements are drafts, begin in `Needs review`, and require human approval.

## Quick Start

Requires Python 3.10 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://127.0.0.1:8000.

To use a different port, replace `8000` in the start command, for example `--port 8080`, then open `http://127.0.0.1:8080`.

## LLM Configuration

The project works without an API key. In this local mode, it uses deterministic local embeddings for ChromaDB retrieval and creates evidence-only requirement drafts.

To enable OpenAI-compatible embeddings and LLM-generated requirements, create a `.env` file in the project root:

```text
LLM_API_KEY=your_new_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

APP_DATA_DIR=data
VECTOR_DB_PATH=data/chroma
```

`OPENAI_API_KEY` is also supported as an alternative to `LLM_API_KEY`. Restart the server after changing `.env`.

Keep API keys only in `.env`, which is ignored by Git. Never add a key to source code, JSON exports, screenshots, or documentation. If a key is exposed, revoke it and create a replacement immediately.

## Using the App

1. Enter the financial functionality, business objective, and users/roles.
2. Complete the adaptive interview and optionally attach policy or requirement documents.
3. Create the project. The app masks, chunks, and indexes the sources.
4. Review the retrieved evidence or use the evidence search field to query the vector index.
5. Generate evidence-grounded requirements and review their citations, confidence, risk, and acceptance criteria.
6. Record requirement approval decisions, run the SDLC analysis, and export the project JSON when ready.

Try the included [digital onboarding policy](sample_data/digital_onboarding_policy.txt) with the functionality `Digital customer onboarding and KYC`.

## API Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/rag/status` | Safe RAG configuration and provider status; never returns secrets. |
| `POST` | `/api/projects` | Create a project and index its source chunks. |
| `GET` | `/api/projects/{project_id}/retrieval?query=...` | Retrieve the highest-ranked ChromaDB evidence chunks. |
| `POST` | `/api/projects/{project_id}/requirements` | Generate evidence-grounded draft requirements. |
| `POST` | `/api/projects/{project_id}/sdlc` | Generate the SDLC recommendation. |
| `GET` | `/api/projects/{project_id}/export` | Download the project audit trail as JSON. |

Interactive API documentation is available at http://127.0.0.1:8000/docs while the server is running.

## Project Structure

```text
app/
  main.py                 FastAPI routes and application lifecycle
  services/documents.py   Extraction, masking, and chunking
  services/rag.py         Embeddings, ChromaDB indexing, and retrieval
  services/llm.py         OpenAI-compatible structured generation
  services/quality.py     Requirement quality checks
  services/sdlc.py        SDLC scoring and workflow recommendation
  services/storage.py     Local project JSON storage
  prompts/                Requirement-generation prompt templates
sample_data/              Example supporting document
tests/                    Automated checks
data/                     Local JSON projects and ChromaDB data
```

## Tests

Run the automated test suite from the project root:

```bash
.venv/bin/python -m pytest -q
```

## Troubleshooting

| Problem | Resolution |
| --- | --- |
| `Address already in use` | A server is already using the chosen port. Stop it with `Ctrl+C`, or start this app on another port. |
| `embedding_provider_configured: false` | Add a valid replacement key to `.env`, then restart the server. Local fallback mode still works without it. |
| The configured embedding provider rejects a request | The app automatically indexes with local embeddings so project creation remains available. Verify `LLM_BASE_URL`, `EMBEDDING_MODEL`, and the provider key before relying on remote embeddings. |
| `500` while creating a project | Stop the server, ensure the `data/` directory is writable, then restart. A fresh ChromaDB collection is created for each project. |
| Browser appears frozen | In DevTools, select Resume script execution if the page is paused in the debugger, then refresh. |

## Limitations

This is a local prototype, not a compliance or legal decision system. Before production use, add authentication, access controls, encrypted durable storage, source versioning, prompt-injection safeguards, retention policies, monitoring, and a formal compliance approval workflow.
