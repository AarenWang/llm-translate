"""HTML format adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import FormatAdapter, FormatContext
from ..chunking import ChunkingEngine
from ..domain import (
    DocumentBlock,
    TranslationChunk,
    TranslationProject,
    ValidationReport,
)
from ..exporter import MarkdownExporter
from ..parser.html import HTMLParser


class HTMLFormatAdapter(FormatAdapter):
    """HTML document format adapter.

    This adapter implements HTML document parsing, chunking, prompt generation,
    and export functionality, seamlessly integrating with the existing translation system.
    """

    format_name = "html"

    def __init__(
        self,
        soft_input_tokens: int = 2200,
        max_input_tokens: int = 3000,
        include_comments: bool = False,
        include_tables: bool = True,
        favor_precision: bool = True,
    ):
        """Initialize HTML format adapter.

        Args:
            soft_input_tokens: Soft input token limit
            max_input_tokens: Maximum input token limit
            include_comments: Whether to include comment content
            include_tables: Whether to include table content
            favor_precision: Whether to prioritize precision
        """
        self.parser = HTMLParser(
            include_comments=include_comments,
            include_tables=include_tables,
            favor_precision=favor_precision,
        )
        self.chunker = ChunkingEngine(soft_input_tokens, max_input_tokens)
        self.exporter = MarkdownExporter()

    def supports(self, path: Path) -> bool:
        """Determine if file path supports HTML format.

        Args:
            path: File path

        Returns:
            True if HTML file, False otherwise
        """
        return path.suffix.lower() in [".html", ".htm"]

    def parse(
        self, project: TranslationProject, context: FormatContext
    ) -> list[DocumentBlock]:
        """Parse HTML document.

        Args:
            project: Translation project
            context: Format context

        Returns:
            List of DocumentBlocks
        """
        html_path = str(context.source_path)
        return self.parser.parse(project.id, html_path)

    def plan_chunks(
        self, project_id: str, blocks: list[DocumentBlock]
    ) -> list[TranslationChunk]:
        """Plan translation chunks.

        Args:
            project_id: Project ID
            blocks: List of DocumentBlocks

        Returns:
            List of TranslationChunks
        """
        return self.chunker.build_chunks(project_id, blocks)

    def prompt_document_format(self) -> str:
        """Generate document format prompt.

        Returns:
            Prompt string describing HTML document format
        """
        return """The document is in HTML format with the following structure:
- Headings marked with # symbols (1-6 levels)
- Paragraphs as plain text
- Lists starting with -, *, +, or numbers followed by . or )
- Code blocks enclosed in triple backticks (```)

The HTML content has been extracted to remove navigation, footers, and other noise.
Preserve the heading hierarchy and markdown formatting in your translation."""

    def chapter_path(self, chunk: TranslationChunk) -> str | None:
        """Get chapter path.

        Args:
            chunk: Translation chunk

        Returns:
            Chapter path, HTML format doesn't use chapters, returns None
        """
        return chunk.chapter_id

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> tuple[dict[str, Path], list[ValidationReport], bool]:
        """Export translation results.

        HTML documents are exported as Markdown format by default to maintain
        consistency with the translation system.

        Args:
            project: Translation project
            context: Format context
            blocks: List of DocumentBlocks
            chunks: List of TranslationChunks
            reports: List of validation reports
            draft: Whether to use draft mode

        Returns:
            Tuple of (output file path dictionary, validation report list, success flag)
        """
        return self.exporter.export(context.artifact_dir, chunks, reports, draft=draft), reports, draft