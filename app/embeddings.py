from functools import lru_cache
from typing import Any

from app.config import Settings


@lru_cache(maxsize=4)
def _vertex_client(project: str, location: str) -> Any:
    from google import genai
    from google.genai.types import HttpOptions

    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=HttpOptions(api_version="v1"),
    )


def embed_texts(
    settings: Settings,
    texts: list[str],
    task_type: str,
) -> list[list[float]]:
    if not texts:
        return []

    from google.genai import types

    client = _vertex_client(
        settings.google_cloud_project,
        settings.google_cloud_location,
    )
    response = client.models.embed_content(
        model=settings.embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=settings.embedding_dimensions,
        ),
    )
    vectors = [list(item.values or []) for item in response.embeddings or []]
    if len(vectors) != len(texts):
        raise RuntimeError("Embedding provider returned an unexpected number of vectors.")
    if any(len(vector) != settings.embedding_dimensions for vector in vectors):
        raise RuntimeError("Embedding provider returned a vector with an unexpected dimension.")
    return vectors