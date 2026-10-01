import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ingest import chunk_text
from app.embeddings import format_e5_inputs
from app.rag import RetrievedChunk, ensure_collection, format_citations, format_context, search_chunks


class RagFormattingTests(unittest.TestCase):
    def test_collection_ensures_document_id_keyword_index(self):
        from qdrant_client.models import PayloadSchemaType

        client = MagicMock()
        client.collection_exists.return_value = False
        settings = SimpleNamespace(
            qdrant_collection="knowledge",
            embedding_dimensions=384,
        )

        ensure_collection(settings, client)

        client.create_payload_index.assert_called_once_with(
            collection_name="knowledge",
            field_name="document_id",
            field_schema=PayloadSchemaType.KEYWORD,
            wait=True,
        )

    def test_search_chunks_uses_query_points(self):
        point = SimpleNamespace(
            payload={"title": "Brewing guide", "source": "guide.md", "text": "Use warm water."},
            score=0.8,
        )
        client = MagicMock()
        client.query_points.return_value.points = [point]
        settings = SimpleNamespace(
            qdrant_url="https://qdrant.example",
            qdrant_api_key="",
            qdrant_collection="knowledge",
            rag_top_k=3,
            rag_min_score=0.35,
        )

        with patch("app.rag._qdrant_client", return_value=client):
            chunks = search_chunks(settings, [0.1, 0.2])

        self.assertEqual(chunks, [RetrievedChunk("Brewing guide", "guide.md", "Use warm water.", 0.8)])
        client.query_points.assert_called_once_with(
            collection_name="knowledge",
            query=[0.1, 0.2],
            limit=3,
            score_threshold=0.35,
            with_payload=True,
        )

    def test_local_e5_embeddings_use_query_and_passage_prefixes(self):
        self.assertEqual(
            format_e5_inputs(["find this"], "RETRIEVAL_QUERY"),
            ["query: find this"],
        )
        self.assertEqual(
            format_e5_inputs(["document text"], "RETRIEVAL_DOCUMENT"),
            ["passage: document text"],
        )

    def test_chunk_text_applies_overlap_and_covers_source(self):
        text = "alpha beta gamma delta epsilon zeta eta theta"
        chunks = chunk_text(text, chunk_size=20, overlap=5)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 20 for chunk in chunks))
        self.assertIn("alpha", chunks[0])
        self.assertTrue(any("theta" in chunk for chunk in chunks))
        self.assertTrue(any(set(first.split()) & set(second.split()) for first, second in zip(chunks, chunks[1:])))

    def test_context_and_citations_share_the_same_source_numbers(self):
        chunks = [
            RetrievedChunk(
                title="Brewing guide",
                source="guide.md",
                text="Use warm water.",
                score=0.8,
            )
        ]

        context = format_context(chunks, max_chars=500)
        citations = format_citations(chunks)
        self.assertIn("[1] Brewing guide (guide.md)", context)
        self.assertIn("[1] Brewing guide - guide.md", citations)

    def test_context_respects_character_budget(self):
        chunks = [RetrievedChunk("Guide", "guide.md", "x" * 200, 0.9)]
        self.assertEqual(len(format_context(chunks, max_chars=40)), 40)


if __name__ == "__main__":
    unittest.main()