from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from llm_translate.config import Settings
from llm_translate.domain import ChunkStatus
from llm_translate.llm import MockLLMProvider
from llm_translate.parser import MarkdownParser
from llm_translate.protection import ProtectionEngine
from llm_translate.service import TranslationService


SAMPLE = """# Title

Paragraph with `inline_code` and https://example.com.

## Chapter 1. Intro

See [Docs](https://example.com/docs).

| A | B |
|---|---|
| Agent | Tool Call |

```python
print("hello")
```
"""


class MarkdownParserTest(unittest.TestCase):
    def test_parser_detects_core_blocks(self) -> None:
        blocks = MarkdownParser().parse("p1", SAMPLE)
        types = [block.block_type for block in blocks]
        self.assertIn("heading", types)
        self.assertIn("paragraph", types)
        self.assertIn("table", types)
        self.assertIn("code_block", types)
        self.assertEqual([b.level for b in blocks if b.block_type == "heading"], [1, 2])


class ProtectionEngineTest(unittest.TestCase):
    def test_protects_non_translatable_spans(self) -> None:
        result = ProtectionEngine().protect("p1", "c1", SAMPLE)
        protected = result.protected_text
        self.assertIn("__LT_INLINE_CODE_000001__", protected)
        self.assertIn("__LT_URL_", protected)
        self.assertIn("__LT_CODE_BLOCK_", protected)
        restored = ProtectionEngine().restore(protected, result.spans)
        self.assertEqual(restored, SAMPLE)

    def test_html_block_does_not_swallow_markdown_code_fence(self) -> None:
        source = """Intro <memories>

```python
print("keep fenced")
```

</memories> outro
"""
        result = ProtectionEngine().protect("p1", "c1", source)
        self.assertEqual(result.protected_text.count("```"), 0)
        self.assertIn("__LT_CODE_BLOCK_", result.protected_text)
        self.assertEqual(ProtectionEngine().restore(result.protected_text, result.spans), source)


class PipelineTest(unittest.TestCase):
    def test_end_to_end_mock_pipeline_exports_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.md"
            source.write_text(SAMPLE, encoding="utf-8")
            glossary = root / "glossary.csv"
            glossary.write_text(
                "source_term,target_term\nAgent,Intelligent Agent\nTool Call,Tool Invocation\n",
                encoding="utf-8",
            )
            settings = Settings(database_path=root / "translate.db", workspace_path=root / "workspace")
            service = TranslationService(settings)
            project, artifacts = service.run(
                source,
                "sample",
                MockLLMProvider(),
                glossary_path=glossary,
            )

            chunks = service.store.list_chunks(project.id)
            self.assertTrue(chunks)
            self.assertTrue(all(chunk.status == ChunkStatus.DONE for chunk in chunks))
            translated = artifacts["translated"].read_text(encoding="utf-8")
            self.assertIn("# Title", translated)
            self.assertIn("## Chapter 1. Intro", translated)
            self.assertIn("Intelligent Agent", translated)
            self.assertIn("https://example.com/docs", translated)
            self.assertIn("```python", translated)
            self.assertTrue(artifacts["bilingual"].exists())


if __name__ == "__main__":
    unittest.main()
