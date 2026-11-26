from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from xml.etree import ElementTree

from pypdf import PdfReader


SENSITIVE_PATTERNS = [
    (re.compile(r"\b\d{12,19}\b"), "[MASKED_ACCOUNT_OR_CARD]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[MASKED_TAX_ID]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[MASKED_ID]"),
]


@dataclass
class Chunk:
    id: str
    text: str


def mask_sensitive(text: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def extract_text(filename: str, content: bytes) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else "txt"
    if suffix in {"txt", "md", "csv"}:
        return content.decode("utf-8", errors="replace")
    if suffix == "pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
    if suffix == "docx":
        with zipfile.ZipFile(BytesIO(content)) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        return "\n".join(node.text or "" for node in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
    raise ValueError("Supported formats are .txt, .md, .csv, .pdf, and .docx")


def chunk_text(text: str, size: int = 700) -> list[Chunk]:
    normalized = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    chunks: list[Chunk] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > size:
            chunks.append(Chunk(id=f"chunk-{len(chunks) + 1:03d}", text=current))
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(Chunk(id=f"chunk-{len(chunks) + 1:03d}", text=current))
    return chunks


def retrieve(query: str, documents: list[dict], limit: int = 6) -> list[dict]:
    terms = {term.lower() for term in re.findall(r"[a-zA-Z]{3,}", query)}
    ranked: list[tuple[float, dict]] = []
    for document in documents:
        for chunk in document.get("chunks", []):
            words = set(re.findall(r"[a-zA-Z]{3,}", chunk["text"].lower()))
            overlap = len(terms & words)
            score = overlap / max(1, len(terms))
            ranked.append((score, {**chunk, "document_id": document["id"], "document_name": document["name"], "relevance": round(score, 2)}))
    return [item for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:limit]]
