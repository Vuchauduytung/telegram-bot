import unittest

from app.ingest import chunk_text
from app.rag import RetrievedChunk, format_citations, format_context


class RagFormattingTests(unittest.TestCase):
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