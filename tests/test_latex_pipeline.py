from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from llm_translate.config import Settings
from llm_translate.domain import ChunkStatus
from llm_translate.formats.latex import LatexFormatAdapter
from llm_translate.llm import MockLLMProvider
from llm_translate.service import TranslationService


SAMPLE_LATEX = r"""\documentclass{article}
\title{Agent Notes}
\author{Example Author}

\begin{document}
\maketitle

\section{Introduction}
Agent writes notes about Tool Call behavior.

The equation $E = mc^2$ should stay untouched.

\begin{verbatim}
Tool Call inside code should not be translated.
\end{verbatim}

\caption{A small figure caption}
\end{document}
"""


class LatexPipelineTest(unittest.TestCase):
    def test_latex_parser_extracts_translatable_spans(self) -> None:
        adapter = LatexFormatAdapter()
        blocks = adapter._parse_blocks("p1", SAMPLE_LATEX)

        self.assertGreaterEqual(len(blocks), 4)
        self.assertIn("latex_command_arg", {block.block_type for block in blocks})
        self.assertIn("latex_paragraph", {block.block_type for block in blocks})
        self.assertFalse(any("inside code" in block.source_text for block in blocks))

    def test_end_to_end_mock_pipeline_exports_latex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.tex"
            source.write_text(SAMPLE_LATEX, encoding="utf-8")
            glossary = root / "glossary.csv"
            glossary.write_text(
                "source_term,target_term\nAgent,Intelligent Agent\nTool Call,Tool Invocation\n",
                encoding="utf-8",
            )

            settings = Settings(database_path=root / "translate.db", workspace_path=root / "workspace")
            service = TranslationService(settings)
            project, artifacts = service.run(source, "latex-test", MockLLMProvider(), glossary_path=glossary)

            self.assertEqual(project.input_format, "latex")
            chunks = service.store.list_chunks(project.id)
            self.assertTrue(chunks)
            self.assertTrue(all(chunk.status == ChunkStatus.DONE for chunk in chunks))
            self.assertIn("latex", artifacts)
            translated = artifacts["latex"].read_text(encoding="utf-8")
            self.assertIn(r"\documentclass{article}", translated)
            self.assertIn(r"$E = mc^2$", translated)
            self.assertIn("Intelligent Agent", translated)
            self.assertIn("Tool Call inside code should not be translated.", translated)
            self.assertIn(r"\end{document}", translated)


if __name__ == "__main__":
    unittest.main()
