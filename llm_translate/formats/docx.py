"""DOCX format adapter for translation."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import logging

from ..domain import DocumentBlock, TranslationChunk, TranslationProject, ValidationReport
from ..parser.docx import DocxParser
from ..protection import ProtectionEngine
from ..chunking import ChunkingEngine
from ..exporter_docx import DocxExporter
from .base import FormatContext


logger = logging.getLogger(__name__)

# Default token limits for chunking
DEFAULT_SOFT_TOKEN_LIMIT = 2200
DEFAULT_MAX_TOKEN_LIMIT = 3000


class DocxFormatAdapter:
    """Format adapter for DOCX files.

    This adapter handles parsing, translation, and export of DOCX files while
    preserving the original structure, formatting, and non-translatable content.
    """

    format_name = "docx"

    def __init__(self, soft_input_tokens: int = DEFAULT_SOFT_TOKEN_LIMIT, max_input_tokens: int = DEFAULT_MAX_TOKEN_LIMIT):
        self.parser = DocxParser()
        self.protection_engine = ProtectionEngine()
        self.chunking_engine = ChunkingEngine(
            soft_input_tokens=soft_input_tokens,
            max_input_tokens=max_input_tokens
        )
        self.exporter = DocxExporter()

    def supports(self, path: Path) -> bool:
        """Check if the format adapter supports the given file.

        Args:
            path: Path to the file to check

        Returns:
            True if the file is a DOCX file
        """
        return path.suffix.lower() == ".docx"

    def parse(self, project: TranslationProject, context: FormatContext) -> list[DocumentBlock]:
        """Parse DOCX file and extract translatable document blocks.

        Args:
            project: Translation project configuration
            context: Format context containing source path and snapshot directory

        Returns:
            List of DocumentBlock objects containing translatable content
        """
        result = self.parser.parse(project.id, context.source_path)

        # Save snapshot for debugging and verification
        context.snapshot_dir.mkdir(parents=True, exist_ok=True)
        (context.snapshot_dir / "docx.json").write_text(
            json.dumps(result.to_snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (context.snapshot_dir / "ast.json").write_text(
            json.dumps([asdict(block) for block in result.blocks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(f"Parsed {len(result.blocks)} blocks from DOCX file")
        return result.blocks

    def plan_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        """Plan translation chunks from document blocks.

        Groups related paragraphs together while respecting token limits.
        Headings serve as natural chapter boundaries.

        Args:
            project_id: Translation project identifier
            blocks: List of document blocks to convert to chunks

        Returns:
            List of TranslationChunk objects for translation
        """
        chunks = self.chunking_engine.build_chunks(project_id, blocks)

        # Apply protection to each chunk
        for chunk in chunks:
            protection_result = self.protection_engine.protect(
                project_id,
                chunk.id,
                chunk.source_text
            )
            # Update chunk with protected text and store spans in metadata
            chunk.source_text = protection_result.protected_text
            if not chunk.metadata:
                chunk.metadata = {}
            chunk.metadata["protected_spans"] = [asdict(span) for span in protection_result.spans]

        logger.info(f"Created {len(chunks)} chunks from {len(blocks)} blocks")
        return chunks

    def prompt_document_format(self) -> str:
        """Return format description for translation prompts.

        Returns:
            Description of the DOCX format for LLM context
        """
        return """This is a Microsoft Word document (.docx) containing formatted text with:
- Paragraphs with various styles (headings, normal, lists, etc.)
- Tables with structured data
- Document structure with heading levels
- Formatted elements like hyperlinks, images, and special styles

The text has been extracted from DOCX format while preserving:
- Paragraph structure and hierarchy
- Heading levels (H1-H6)
- Table cell content
- Basic text formatting

Non-translatable elements have been protected with placeholders."""

    def chapter_path(self, chunk: TranslationChunk) -> str | None:
        """Get chapter path for a chunk.

        Args:
            chunk: Translation chunk to get path for

        Returns:
            Chapter path or None if not applicable
        """
        # For DOCX, use heading-based chapter identification
        if chunk.metadata and "heading_level" in chunk.metadata:
            level = chunk.metadata["heading_level"]
            if level and level <= 2:
                return f"heading_{level}"

        return None

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> tuple[dict[str, Path], list[ValidationReport], bool]:
        """Export translated content back to DOCX format.

        Args:
            project: Translation project configuration
            context: Format context containing paths
            blocks: Original document blocks
            chunks: Translated chunks
            reports: Validation reports
            draft: Whether this is a draft export

        Returns:
            Tuple of (exported paths, validation reports, has_changes)
        """
        logger.info(f"Exporting translated DOCX content (draft={draft})")

        # Export using DOCX exporter
        exported_paths = self.exporter.export(
            artifact_dir=context.artifact_dir,
            source_docx_path=context.source_path,
            blocks=blocks,
            chunks=chunks,
            reports=reports,
            draft=draft
        )

        # Determine if there are meaningful changes
        has_changes = any(
            chunk.target_text and chunk.target_text != chunk.source_text
            for chunk in chunks
        )

        logger.info(f"DOCX export completed: {len(exported_paths)} files created")
        return exported_paths, reports, has_changes
