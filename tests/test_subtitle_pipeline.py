from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from llm_translate.config import Settings
from llm_translate.domain import ChunkStatus
from llm_translate.formats.subtitle import SrtFormatAdapter, VttFormatAdapter
from llm_translate.llm import MockLLMProvider
from llm_translate.service import TranslationService


SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,000
Agent opens the document.

2
00:00:04,000 --> 00:00:06,000
Tool Call returns a result.
"""

SAMPLE_VTT = """WEBVTT

NOTE keep this metadata

cue-1
00:00:01.000 --> 00:00:03.000
Agent opens the document.

00:00:04.000 --> 00:00:06.000
Tool Call returns a result.
"""


class SubtitlePipelineTest(unittest.TestCase):
    def test_srt_parser_extracts_cues(self) -> None:
        adapter = SrtFormatAdapter()
        blocks = adapter._parse_blocks("p1", SAMPLE_SRT)

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].metadata["timing"], "00:00:01,000 --> 00:00:03,000")
        self.assertEqual(blocks[1].source_text, "Tool Call returns a result.")

    def test_vtt_parser_extracts_cues_and_skips_note(self) -> None:
        adapter = VttFormatAdapter()
        blocks = adapter._parse_blocks("p1", SAMPLE_VTT)

        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].metadata["identifier"], "cue-1")
        self.assertFalse(any("NOTE" in block.source_text for block in blocks))

    def test_end_to_end_mock_pipeline_exports_srt(self) -> None:
        self._run_pipeline("sample.srt", SAMPLE_SRT, "srt")

    def test_end_to_end_mock_pipeline_exports_vtt(self) -> None:
        self._run_pipeline("sample.vtt", SAMPLE_VTT, "vtt")

    def _run_pipeline(self, filename: str, source_text: str, artifact_key: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / filename
            source.write_text(source_text, encoding="utf-8")
            glossary = root / "glossary.csv"
            glossary.write_text(
                "source_term,target_term\nAgent,Intelligent Agent\nTool Call,Tool Invocation\n",
                encoding="utf-8",
            )

            settings = Settings(database_path=root / "translate.db", workspace_path=root / "workspace")
            service = TranslationService(settings)
            project, artifacts = service.run(source, f"{artifact_key}-test", MockLLMProvider(), glossary_path=glossary)

            self.assertEqual(project.input_format, artifact_key)
            chunks = service.store.list_chunks(project.id)
            self.assertTrue(all(chunk.status == ChunkStatus.DONE for chunk in chunks))
            translated = artifacts[artifact_key].read_text(encoding="utf-8")
            self.assertIn("Intelligent Agent opens the document.", translated)
            self.assertIn("Tool Invocation returns a result.", translated)
            self.assertIn("-->", translated)
            if artifact_key == "vtt":
                self.assertTrue(translated.startswith("WEBVTT"))


if __name__ == "__main__":
    unittest.main()

