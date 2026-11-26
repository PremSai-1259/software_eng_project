# Finance Helper — Version 2

Finance Helper turns one project brief into evidence-linked financial software requirements, review findings, SDLC guidance, and an IEEE 830-1998 SRS Word document. This version has no interview flow: submit the brief once. Supporting documents are optional.

## Setup and run (PowerShell)

Run these commands from the project folder:

```powershell
cd C:\Users\nikhi\OneDrive\Desktop\PROJECTS\SE\version_2
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

In `.env`, configure `GROQ_API_KEY` and `OPENAI_API_KEY`. Groq is tried first; if it fails after transient retries, the app automatically retries the request through OpenAI using `OPENAI_MODEL`. The brief and retrieved source excerpts are sent to the available provider for requirement generation and semantic SDLC scoring. Keep `.env` private. If both providers fail, generation reports an error instead of substituting a local-only answer.

Start the app:

```powershell
py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Open <http://127.0.0.1:8001>. API documentation is at <http://127.0.0.1:8001/docs>. Stop the server with **Ctrl+C**.

## Workflow

1. Enter one project brief and optionally attach source files.
2. The Requirements Agent retrieves evidence, drafts requirements, and runs quality and compliance checks.
3. The Governance & SDLC Agent sends the brief, source evidence, and generated requirements to Groq for semantic comparison of all lifecycle models, then automatically tries OpenAI if Groq fails or returns incomplete model scores. It combines the successful provider's assessment with explicit cues and project factors. If both providers fail, it reports the error instead of showing a local-only ranking.
4. The separate SRS Generation Agent creates a Word document using the brief, requirements, and SDLC decision.
5. Review the results in the existing left-sidebar sections and use **Download SRS**.

Requirement generation targets at least six distinct draft requirements, including for short briefs. When the source does not specify enough detail, any added items are low-confidence assumptions linked to the brief and marked for human review. The generated requirements and SRS remain drafts until reviewed by a person. The SRS uses IEEE 830-1998 sections, retains requirement evidence traceability, and includes direct, editable monospaced use case, sequence, and state diagrams derived from the brief and functional requirements (not table layouts).

## Agents

- **Requirements Agent** — gathers and classifies requirements from the single brief and retrieved source evidence, then records quality and compliance findings.
- **SRS Generation Agent** — independently composes the IEEE 830-1998 Word document from the saved project baseline.
- **Governance & SDLC Agent** — provides the SDLC advisory shown in the existing workflow.

Project records, ChromaDB vectors, and generated exports are stored under `data/` in this version_2 folder.
