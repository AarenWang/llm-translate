from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from llm_translate.config import Settings
from llm_translate.domain import ChunkStatus
from llm_translate.formats.plain_text import PlainTextFormatAdapter
from llm_translate.llm import MockLLMProvider
from llm_translate.service import TranslationService


SAMPLE_TEXT = """Agent writes notes with `inline_code`.
Visit https://example.com/docs for Tool Call details.

Second paragraph keeps its own boundary.
"""


class PlainTextPipelineTest(unittest.TestCase):
    def test_plain_text_parser_splits_paragraphs(self) -> None:
        adapter = PlainTextFormatAdapter()
        blocks = adapter._parse_paragraphs("p1", SAMPLE_TEXT)

        self.assertEqual(len(blocks), 2)
        self.assertEqual([block.block_type for block in blocks], ["plain_paragraph", "plain_paragraph"])
        self.assertEqual(blocks[0].metadata["format"], "plain_text")
        self.assertIn("Tool Call", blocks[0].source_text)

    def test_end_to_end_mock_pipeline_exports_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.txt"
            source.write_text(SAMPLE_TEXT, encoding="utf-8")
            glossary = root / "glossary.csv"
            glossary.write_text(
                "source_term,target_term\nAgent,Intelligent Agent\nTool Call,Tool Invocation\n",
                encoding="utf-8",
            )

            settings = Settings(database_path=root / "translate.db", workspace_path=root / "workspace")
            service = TranslationService(settings)
            project, artifacts = service.run(
                source,
                "plain-text",
                MockLLMProvider(),
                glossary_path=glossary,
            )

            self.assertEqual(project.input_format, "plain_text")
            chunks = service.store.list_chunks(project.id)
            self.assertTrue(chunks)
            self.assertTrue(all(chunk.status == ChunkStatus.DONE for chunk in chunks))
            self.assertIn("text", artifacts)
            self.assertTrue(artifacts["text"].exists())

            translated_text = artifacts["text"].read_text(encoding="utf-8")
            translated_md = artifacts["translated"].read_text(encoding="utf-8")
            self.assertIn("Intelligent Agent", translated_text)
            self.assertIn("Tool Invocation", translated_text)
            self.assertIn("`inline_code`", translated_text)
            self.assertIn("https://example.com/docs", translated_text)
            self.assertIn("\n\nSecond paragraph", translated_text)
            self.assertEqual(translated_text, translated_md)


if __name__ == "__main__":
    unittest.main()
