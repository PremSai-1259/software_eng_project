# FinReq Studio

A small, local-first Software Engineering project prototype for financial-sector requirement generation, quality review, and SDLC identification. It implements the two evaluated flows in the supplied problem statement without pretending that unverified drafts or legal interpretations are final decisions.

## What it demonstrates

1. Begin an adaptive stakeholder interview with the financial functionality, business objective, and users/roles.
2. Answer one contextual follow-up at a time. The interview selects financial-domain questions for onboarding, payments, loans, fraud, insurance, and reporting, then covers workflow, controls, exceptions, and SDLC context.
3. Optionally upload `.txt`, `.md`, `.csv`, `.pdf`, or `.docx` policies or existing requirements as supporting evidence.
4. Mask common account/card, tax-ID, and national-ID-like patterns before local processing.
5. Retrieve source chunks by keyword overlap and generate evidence-linked requirement drafts.
6. Classify requirements across functional and non-functional categories.
7. Run deterministic checks for ambiguity, testability, evidence gaps, duplication, and missing security/compliance review.
8. Rank SDLC options using factors inferred from the generated requirements, then show a project-specific workflow and approval gates.
9. Record stakeholder input, uploads, generated drafts, approvals, and SDLC analysis in a local audit log. Export the complete project as JSON.

## Architecture

```text
Adaptive stakeholder interview + documents -> processing/masking -> retrieval -> requirement drafts
         -> quality checks -> SDLC factor scoring -> ranked recommendation
         -> local JSON store, audit log, export
```

The modules are intentionally independent:

- `app/services/documents.py`: extraction, masking, chunking, retrieval
- `app/services/generator.py`: evidence-backed requirement drafting and classification
- `app/services/quality.py`: requirement quality rules
- `app/services/sdlc.py`: transparent SDLC factor scoring and workflow construction
- `app/services/storage.py`: local project persistence
- `app/prompts/`: separate LLM prompt templates ready for a future structured-output adapter

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. Start with the stakeholder questionnaire for `digital customer onboarding and KYC`; `sample_data/digital_onboarding_policy.txt` is optional supporting evidence.

Run the automated checks with:

```bash
pytest
```

## LLM and evidence policy

This prototype runs without an API key. The default generator extracts only source-supported draft statements and attaches the relevant source excerpt. It intentionally labels those drafts `Needs review` and uses conservative confidence scores.

`.env.example` configures an OpenAI-compatible structured-output adapter. When `LLM_API_KEY` is set in the environment, requirement generation sends the selected functionality plus retrieved source chunks to that adapter. The response is rejected unless it points to valid source chunk IDs. If the provider is unavailable or returns invalid JSON, the app records the fallback in the audit log and uses local evidence-only drafting instead. No remote model is called by default. Any adapter must preserve the evidence requirement, distinguish inference from explicit source content, reject unsupported regulations/policies, and retain the human approval checkpoint.

## Scope and extensions

The prototype supports document-led requirement elicitation, not autonomous stakeholder conversations or live regulation retrieval. In production, add role-based authentication, encrypted durable storage, source versioning, a vetted regulatory knowledge base, semantic retrieval, prompt-injection controls, configurable data-retention rules, human editing/regeneration, and an approved structured-output LLM adapter. Compliance mappings remain advisory until approved by authorised compliance or legal personnel.
=======

