from __future__ import annotations

import json
import os
import hashlib
import logging
import re
import ssl

import certifi
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import chromadb
from chromadb.errors import NotFoundError


logger = logging.getLogger(__name__)
TLS_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class RagConfigurationError(RuntimeError):
    """Raised when semantic retrieval cannot be configured or completed."""


def _api_key() -> str:
    base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    key = ((os.getenv("GROQ_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip())
           if "api.groq.com" in base_url
           else (os.getenv("LLM_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()))
    if not key:
        raise RagConfigurationError("Set GROQ_API_KEY and/or OPENAI_API_KEY in .env before using LLM generation.")
    return key


def provider_configured() -> bool:
    return bool(
        os.getenv("GROQ_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
    )


def _embedding_base_url() -> str:
    return os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def _embedding_api_key() -> str | None:
    return (os.getenv("EMBEDDING_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip()
            or (os.getenv("LLM_API_KEY", "").strip() if _embedding_base_url() == os.getenv("LLM_BASE_URL", "").rstrip("/") else ""))


def embedding_provider_configured() -> bool:
    """Return whether a remote embeddings model is explicitly configured."""
    return bool(_embedding_api_key() and os.getenv("EMBEDDING_MODEL", "").strip())


def _embed(texts: list[str]) -> list[list[float]]:
    """Embed with the configured provider, retaining local retrieval on provider failures."""
    if not texts:
        return []
    if not embedding_provider_configured():
        return [_local_embed(text) for text in texts]
    payload = {"model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"), "input": texts}
    base_url = _embedding_base_url()
    request = Request(
        f"{base_url}/embeddings",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {_embedding_api_key()}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=35, context=TLS_CONTEXT) as response:  # noqa: S310 - operator-configured API URL
            result = json.loads(response.read().decode("utf-8"))
        vectors = [item["embedding"] for item in sorted(result["data"], key=lambda item: item["index"])]
        if len(vectors) != len(texts) or not all(isinstance(vector, list) and vector for vector in vectors):
            raise ValueError("response contained incomplete embedding data")
        return vectors
    except (HTTPError, URLError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        # Project creation and evidence retrieval stay usable when a configured
        # provider rejects a model, credential, or request.
        logger.warning("Embedding provider unavailable; using local embeddings instead: %s", exc)
        return [_local_embed(text) for text in texts]


def _local_embed(text: str, dimensions: int = 384) -> list[float]:
    """Create stable local vectors so the prototype remains usable without a provider key."""
    vector = [0.0] * dimensions
    for token in re.findall(r"[a-z0-9]{2,}", text.lower()):
        bucket = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big") % dimensions
        vector[bucket] += 1.0
    magnitude = sum(value * value for value in vector) ** 0.5
    return [value / magnitude for value in vector] if magnitude else vector


class VectorStore:
    """Persistent ChromaDB store using vectors from an OpenAI-compatible embedding endpoint."""

    def __init__(self) -> None:
        root = Path(os.getenv("VECTOR_DB_PATH", Path(os.getenv("APP_DATA_DIR", "data")) / "chroma"))
        root.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(root))

    @staticmethod
    def _collection_name(project_id: str) -> str:
        return f"finreq_{project_id}"

    @staticmethod
    def configuration() -> dict[str, str]:
        """Return safe-to-display settings without exposing provider credentials."""
        return {
            "vector_database": "ChromaDB",
            "embedding_model": os.getenv("EMBEDDING_MODEL", "text-embedding-3-small") if embedding_provider_configured() else "Local hashed embeddings (384 dimensions)",
            "llm_model": (os.getenv("LLM_MODEL", "openai/gpt-oss-20b") if os.getenv("GROQ_API_KEY", "").strip()
                          else os.getenv("OPENAI_MODEL", "gpt-4o-mini")) if provider_configured() else "Not configured",
            "collection_scope": "One persistent collection per project",
        }

    def index(self, project_id: str, documents: list[dict]) -> int:
        ids: list[str] = []
        texts: list[str] = []
        metadata: list[dict[str, str]] = []
        for document in documents:
            for chunk in document.get("chunks", []):
                ids.append(f"{document['id']}:{chunk['id']}")
                texts.append(chunk["text"])
                metadata.append({
                    "document_id": document["id"], "document_name": document["name"], "chunk_id": chunk["id"],
                    "jurisdiction": str(document.get("jurisdiction") or ""),
                    "effective_date": str(document.get("effective_date") or ""),
                    "version": str(document.get("version") or ""),
                    "document_type": str(document.get("document_type") or ""),
                    "applicability": str(document.get("applicability") or ""),
                    "uploaded_by": str(document.get("uploaded_by") or ""),
                    "source_url": str(document.get("source_url") or ""),
                    "source_version": str(document.get("version") or document.get("source_version") or ""),
                    "created_at": str(document.get("created_at") or ""),
                })
        if not texts:
            raise RagConfigurationError("No text chunks were available for semantic indexing.")
        try:
            collection = self.client.get_or_create_collection(
                self._collection_name(project_id), metadata={"hnsw:space": "cosine"}
            )
            collection.upsert(ids=ids, documents=texts, metadatas=metadata, embeddings=_embed(texts))
        except RagConfigurationError:
            raise
        except Exception as exc:
            raise RagConfigurationError("The vector database could not index the project sources.") from exc
        return len(texts)

    def retrieve(self, project_id: str, query: str, limit: int = 6) -> list[dict]:
        try:
            collection = self.client.get_collection(self._collection_name(project_id))
        except NotFoundError as exc:
            raise RagConfigurationError("The project's vector collection is unavailable. Recreate the project to index its sources.") from exc
        try:
            result = collection.query(
                query_embeddings=_embed([query]),
                n_results=min(limit, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise RagConfigurationError("The vector database could not retrieve project evidence.") from exc
        documents = result.get("documents", [[]])[0]
        metadata = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        matches = [
            {
                "id": item["chunk_id"],
                "text": text,
                "document_id": item["document_id"],
                "document_name": item["document_name"],
                "jurisdiction": item.get("jurisdiction") or None,
                "effective_date": item.get("effective_date") or None,
                "version": item.get("version") or None,
                "document_type": item.get("document_type") or None,
                "applicability": item.get("applicability") or None,
                "uploaded_by": item.get("uploaded_by") or None,
                "created_at": item.get("created_at") or None,
                "source_url": item.get("source_url") or None,
                "source_version": item.get("source_version") or None,
                "vector_relevance": max(0.0, 1 - (distance / 2)),
            }
            for text, item, distance in zip(documents, metadata, distances, strict=True)
        ]
        # Chroma performs semantic vector retrieval; lexical overlap re-ranks ties and
        # improves exact terminology matches for policy/control language.
        query_terms = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
        for match in matches:
            text_terms = set(re.findall(r"[a-z0-9]{3,}", match["text"].lower()))
            lexical = len(query_terms & text_terms) / max(1, len(query_terms))
            match["relevance"] = round(0.7 * match["vector_relevance"] + 0.3 * lexical, 2)
            del match["vector_relevance"]
        return sorted(matches, key=lambda match: match["relevance"], reverse=True)
