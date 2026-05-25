from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from llm_translate.config import Settings
from llm_translate.domain import ChunkStatus
from llm_translate.llm import MockLLMProvider
from llm_translate.service import TranslationService


class IpynbPipelineTest(unittest.TestCase):
    def test_end_to_end_mock_pipeline_exports_translated_notebook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Path("fixtures/sample.ipynb")
            glossary = root / "glossary.csv"
            glossary.write_text(
                "source_term,target_term\nAgent,Intelligent Agent\nTool Call,Tool Invocation\n",
                encoding="utf-8",
            )
            settings = Settings(database_path=root / "translate.db", workspace_path=root / "workspace")
            service = TranslationService(settings)
            project, artifacts = service.run(
                source,
                "sample-ipynb",
                MockLLMProvider(),
                glossary_path=glossary,
            )

            chunks = service.store.list_chunks(project.id)
            self.assertEqual(len(chunks), 2)
            self.assertTrue(all(chunk.status == ChunkStatus.DONE for chunk in chunks))

            exported = json.loads(artifacts["ipynb"].read_text(encoding="utf-8"))
            original = json.loads(source.read_text(encoding="utf-8"))
            self.assertEqual(len(exported["cells"]), len(original["cells"]))
            self.assertEqual(exported["nbformat"], original["nbformat"])
            self.assertEqual(exported["metadata"], original["metadata"])

            first_markdown = "".join(exported["cells"][0]["source"])
            self.assertIn("Intelligent Agent", first_markdown)
            self.assertIn("Tool Invocation", first_markdown)
            self.assertIn("https://example.com/docs", first_markdown)

            self.assertEqual(exported["cells"][1], original["cells"][1])
            second_markdown = exported["cells"][2]["source"]
            self.assertIsInstance(second_markdown, str)
            self.assertIn("`inline_code`", second_markdown)

            report = artifacts["validation_report_md"].read_text(encoding="utf-8")
            self.assertIn("NOTEBOOK_STRUCTURE", report)
            self.assertIn("NOTEBOOK_ARTIFACT", report)

    def test_long_markdown_cell_is_split_and_recombined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "long.ipynb"
            paragraphs = [
                f"Paragraph {index} mentions Agent and Tool Call in a long notebook cell."
                for index in range(20)
            ]
            notebook = {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "id": "long-md",
                        "metadata": {},
                        "source": "\n\n".join(paragraphs),
                    },
                    {
                        "cell_type": "code",
                        "execution_count": 7,
                        "id": "code-cell",
                        "metadata": {"trusted": True},
                        "outputs": [{"output_type": "execute_result", "data": {"text/plain": ["42"]}}],
                        "source": "answer = 42\nanswer",
                    },
                ],
                "metadata": {"kernelspec": {"name": "python3"}},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            source.write_text(json.dumps(notebook), encoding="utf-8")
            glossary = root / "glossary.csv"
            glossary.write_text(
                "source_term,target_term\nAgent,Intelligent Agent\nTool Call,Tool Invocation\n",
                encoding="utf-8",
            )
            settings = Settings(
                database_path=root / "translate.db",
                workspace_path=root / "workspace",
                soft_input_tokens=25,
                max_input_tokens=40,
            )
            service = TranslationService(settings)
            project, artifacts = service.run(
                source,
                "long-ipynb",
                MockLLMProvider(),
                glossary_path=glossary,
            )

            chunks = service.store.list_chunks(project.id)
            self.assertGreater(len(chunks), 1)
            self.assertTrue(all(chunk.metadata["cell_index"] == 0 for chunk in chunks))
            self.assertEqual({chunk.status for chunk in chunks}, {ChunkStatus.DONE})

            exported = json.loads(artifacts["ipynb"].read_text(encoding="utf-8"))
            self.assertEqual(exported["cells"][1], notebook["cells"][1])
            translated_cell = exported["cells"][0]["source"]
            self.assertIn("Paragraph 0", translated_cell)
            self.assertIn("Paragraph 19", translated_cell)
            self.assertIn("Intelligent Agent", translated_cell)
            self.assertIn("Tool Invocation", translated_cell)


if __name__ == "__main__":
    unittest.main()
