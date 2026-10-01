import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.config import Settings
from app.embeddings import embed_texts


@dataclass(frozen=True)
class RetrievedChunk:
    title: str
    source: str
    text: str
    score: float


@lru_cache(maxsize=4)
def _qdrant_client(url: str, api_key: str = "") -> Any:
    from qdrant_client import QdrantClient

    return QdrantClient(url=url, api_key=api_key or None, timeout=10)


def ensure_collection(settings: Settings, client: Any | None = None) -> Any:
    from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

    client = client or _qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dimensions,
                distance=Distance.COSINE,
            ),
        )
    else:
        collection = client.get_collection(settings.qdrant_collection)
        vector_config = collection.config.params.vectors
        dimension = getattr(vector_config, "size", None)
        if dimension is not None and dimension != settings.embedding_dimensions:
            raise RuntimeError(
                f"Qdrant collection dimension is {dimension}; configured embedding dimension is "
                f"{settings.embedding_dimensions}. Recreate/re-index the collection after changing "
                "EMBEDDING_DIMENSIONS."
            )
    client.create_payload_index(
        collection_name=settings.qdrant_collection,
        field_name="document_id",
        field_schema=PayloadSchemaType.KEYWORD,
        wait=True,
    )
    return client


def search_chunks(settings: Settings, vector: list[float]) -> list[RetrievedChunk]:
    client = _qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    if not client.collection_exists(settings.qdrant_collection):
        return []

    response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        limit=settings.rag_top_k,
        score_threshold=settings.rag_min_score,
        with_payload=True,
    )
    results = []
    for point in response.points:
        payload = point.payload or {}
        text = payload.get("text")
        if not text:
            continue
        results.append(
            RetrievedChunk(
                title=str(payload.get("title") or payload.get("source") or "Untitled"),
                source=str(payload.get("source") or "unknown source"),
                text=str(text),
                score=float(point.score),
            )
        )
    return results


async def retrieve_chunks(settings: Settings, query: str) -> list[RetrievedChunk]:
    vector = (await asyncio.to_thread(embed_texts, settings, [query], "RETRIEVAL_QUERY"))[0]
    return await asyncio.to_thread(search_chunks, settings, vector)


def format_context(chunks: list[RetrievedChunk], max_chars: int) -> str:
    blocks = []
    used_chars = 0
    for index, chunk in enumerate(chunks, start=1):
        block = f"[{index}] {chunk.title} ({chunk.source})\n{chunk.text}"
        remaining = max_chars - used_chars
        if remaining <= 0:
            break
        if len(block) > remaining:
            block = block[:remaining]
        blocks.append(block)
        used_chars += len(block) + 2
    return "\n\n".join(blocks)


def format_citations(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return ""
    sources = "\n".join(
        f"[{index}] {chunk.title} - {chunk.source}"
        for index, chunk in enumerate(chunks, start=1)
    )
    return f"\n\nSources:\n{sources}"