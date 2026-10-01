import argparse
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.embeddings import embed_texts
from app.rag import ensure_collection

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    if not normalized:
        return []

    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = max(
                normalized.rfind("\n", start + chunk_size // 2, end),
                normalized.rfind(" ", start + chunk_size // 2, end),
            )
            if boundary > start:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _document_identity(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _document_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        heading = re.match(r"^#\s+(.+?)\s*#*\s*$", line.strip())
        if heading:
            return heading.group(1)
    return path.stem.replace("_", " ").replace("-", " ").title()


def _delete_document(client, settings, document_id: str) -> None:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            ]
        ),
        wait=True,
    )


def ingest_directory(settings=None, directory: Path | None = None) -> tuple[int, int]:
    settings = settings or get_settings()
    directory = (directory or Path(settings.knowledge_dir)).resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Knowledge directory does not exist: {directory}")

    files = sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}
    )
    if not files:
        logger.warning("No Markdown or TXT documents found in %s", directory)
        return 0, 0

    client = ensure_collection(settings)
    succeeded = 0
    failed = 0
    for path in files:
        source = path.relative_to(directory).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
            if not chunks:
                logger.warning("Skipping empty document %s", source)
                continue

            vectors = embed_texts(settings, chunks, "RETRIEVAL_DOCUMENT")
            document_id = _document_identity(source)
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            now = datetime.now(timezone.utc).isoformat()

            from qdrant_client.models import PointStruct

            points = [
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{index}")),
                    vector=vector,
                    payload={
                        "document_id": document_id,
                        "chunk_id": f"{document_id}:{index}",
                        "source": source,
                        "title": _document_title(path, text),
                        "content_hash": content_hash,
                        "updated_at": now,
                        "chunk_index": index,
                        "text": chunk,
                    },
                )
                for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
            ]
            _delete_document(client, settings, document_id)
            client.upsert(
                collection_name=settings.qdrant_collection,
                points=points,
                wait=True,
            )
            succeeded += 1
            logger.info("Indexed %s (%d chunks)", source, len(points))
        except Exception:
            failed += 1
            logger.exception("Failed to index %s", source)
    return succeeded, failed


def delete_source(settings, source: str) -> None:
    client = ensure_collection(settings)
    source_path = Path(source)
    if source_path.is_absolute() or ".." in source_path.parts:
        raise ValueError("Source must be a relative path inside the knowledge directory.")
    normalized_source = source_path.as_posix()
    _delete_document(client, settings, _document_identity(normalized_source))
    logger.info("Deleted indexed source %s", normalized_source)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="Index or remove Markdown/TXT RAG sources.")
    parser.add_argument("--directory", type=Path, help="Document directory (defaults to KNOWLEDGE_DIR).")
    parser.add_argument("--delete-source", help="Remove an indexed relative source path.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    if args.delete_source:
        delete_source(settings, args.delete_source)
        return

    succeeded, failed = ingest_directory(settings, args.directory)
    print(f"Indexed documents: {succeeded}; failed: {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()