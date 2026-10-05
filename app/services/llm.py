from __future__ import annotations

import json
import os
import ssl
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import certifi

from app.schemas import Category, Evidence, Requirement
from app.services.rag import _api_key, provider_configured


PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def enabled() -> bool:
    return provider_configured()

def _post_chat(prompt: str) -> dict:
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    api_key = _api_key()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    print("========== GROQ DEBUG ==========")
    print("URL:", f"{base_url}/chat/completions")
    print("MODEL:", model)
    print("API KEY PRESENT:", bool(api_key))
    print("API KEY PREFIX:", api_key[:8] if api_key else "NONE")
    print("PROMPT TOKENS APPROX:", len(prompt) // 4)
    print("================================")

    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "FinReq-Studio/1.0",
        },
        method="POST",
    )

    try:
        with urlopen(
            request,
            timeout=35,
            context=TLS_CONTEXT
        ) as response:
            raw = response.read().decode("utf-8")

        print("========== GROQ RESPONSE ==========")
        print(raw)
        print("===================================")

        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]

        return json.loads(content)

    except Exception as exc:
        print("========== GROQ ACTUAL ERROR ==========")
        print(repr(exc))

        if hasattr(exc, "read"):
            try:
                print("BODY:", exc.read().decode("utf-8"))
            except Exception:
                pass

        print("=======================================")

        raise RuntimeError(f"Groq request failed: {exc}") from exc



def generate_requirements(functionality: str, chunks: list[dict]) -> list[Requirement]:
    """Generate source-bound requirements from an operator-configured OpenAI-compatible API."""
    prompt = (PROMPTS / "requirement_generation.txt").read_text(encoding="utf-8")
    evidence = [{"chunk_id": f"{item['document_id']}:{item['id']}", "document": item["document_name"], "text": item["text"]} for item in chunks]
    schema_hint = {
        "requirements": [{
            "statement": "string", "categories": ["Functional"], "evidence_chunk_ids": ["chunk-001"],
            "business_justification": "string", "priority": "Must|Should|Could", "dependencies": ["string"],
            "assumptions": ["string"], "acceptance_criteria": ["string"], "applicable_policy": None,
            "risk_level": "Low|Medium|High", "confidence": 0.0, "reasoning": "string"
        }]
    }
    response = _post_chat(f"{prompt}\n\nFunctionality: {functionality}\n\nEvidence: {json.dumps(evidence)}\n\nReturn only this JSON shape: {json.dumps(schema_hint)}")
    by_chunk = {f"{item['document_id']}:{item['id']}": item for item in chunks}
    requirements: list[Requirement] = []
    for index, item in enumerate(response.get("requirements", [])[:12], start=1):
        source_ids = [source_id for source_id in item.get("evidence_chunk_ids", []) if source_id in by_chunk]
        if not source_ids:
            continue
        linked = [by_chunk[source_id] for source_id in source_ids]
        requirements.append(Requirement(
            id=f"REQ-{index:03d}", statement=item["statement"],
            categories=[Category(value) for value in item.get("categories", ["Functional"])],
            evidence=[Evidence(document_id=source["document_id"], document_name=source["document_name"], chunk_id=source["id"], excerpt=source["text"][:500], relevance=source["relevance"], source_url=source.get("source_url"), source_version=source.get("source_version"), effective_date=source.get("effective_date")) for source in linked],
            business_justification=item["business_justification"], priority=item.get("priority", "Should"), dependencies=item.get("dependencies", []),
            assumptions=item.get("assumptions", []), acceptance_criteria=item.get("acceptance_criteria", []),
            applicable_policy=item.get("applicable_policy"), risk_level=item.get("risk_level", "Medium"),
            confidence=max(0, min(1, float(item.get("confidence", 0.5)))), reasoning=item["reasoning"], approval_status="Needs review"
        ))
    if not requirements:
        raise RuntimeError("The LLM response included no requirements with valid evidence references.")
    return requirements


def select_interview_question(
    functionality: str,
    answers: dict[str, str],
    candidates: list[dict[str, str]]
) -> dict:
    """Ask the configured LLM to select one unasked interview topic and question."""

    prompt = (
        "Choose the next stakeholder interview topic.\n"
        "Return ONLY valid JSON with exactly these fields:\n"
        '{"key":"candidate key","topic":"topic","prompt":"question"}\n'
        "The key must exactly match a candidate key.\n"
    )

    recent_answer = ""

    if answers:
        recent_key = list(answers.keys())[-1]
        recent_answer = answers[recent_key].strip()[:400]

    candidate_info = [
        {
            "key": candidate["key"],
            "topic": candidate["topic"]
        }
        for candidate in candidates
    ]

    response = _post_chat(
        f"{prompt}"
        f"Functionality: {functionality[:300]}\n"
        f"Latest answer: {recent_answer}\n"
        f"Candidates: {json.dumps(candidate_info)}"
    )

    allowed_keys = {candidate["key"] for candidate in candidates}

    key = response.get("key")
    topic = response.get("topic")
    question = response.get("prompt")

    if (
        key not in allowed_keys
        or not isinstance(topic, str)
        or not isinstance(question, str)
        or len(question.strip()) < 10
    ):
        raise RuntimeError(
            "The configured LLM returned an invalid interview question."
        )

    return {
        "key": key,
        "topic": topic.strip()[:80],
        "prompt": question.strip()[:500]
    }