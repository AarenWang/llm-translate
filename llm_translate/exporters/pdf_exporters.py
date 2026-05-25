"""PDF exporters for translated content."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from abc import ABC, abstractmethod

from ..domain import TranslationProject, TranslationChunk, ValidationReport
from ..formats.base import FormatContext


class PdfExporter(ABC):
    """Base class for PDF exporters."""

    @abstractmethod
    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[Any],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> Path:
        """Export translated content."""
        pass


class MarkdownPdfExporter(PdfExporter):
    """Export translated PDF content as Markdown."""

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[Any],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> Path:
        """Export as Markdown format."""
        output_path = context.artifact_dir / f"{project.name}_translated.md"

        # Ensure artifacts directory exists
        context.artifact_dir.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            # Write document header
            f.write(f"# {project.name}\n\n")

            # Write metadata if available from original blocks
            if blocks and hasattr(blocks[0], "metadata"):
                metadata = blocks[0].metadata
                if metadata and "original_metadata" in metadata:
                    original_meta = metadata["original_metadata"]
                    if isinstance(original_meta, dict):
                        if original_meta.get("title"):
                            f.write(f"**Original Title:** {original_meta['title']}\n\n")
                        if original_meta.get("author"):
                            f.write(f"**Author:** {original_meta['author']}\n\n")

            f.write("---\n\n")

            # Write translated content from chunks
            for chunk in chunks:
                # Use restored_text if available, otherwise use target_text
                text = chunk.restored_text or chunk.target_text or ""
                if text:
                    # Add chunk separator if multiple chunks
                    if len(chunks) > 1:
                        f.write(f"## Chunk {chunk.chunk_order + 1}\n\n")
                    f.write(f"{text}\n\n")

        return output_path


class SimplePdfExporter(PdfExporter):
    """Export translated content as a simple PDF using reportlab."""

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[Any],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> Path:
        """Export as simple PDF format."""
        output_path = context.artifact_dir / f"{project.name}_translated.pdf"

        # Ensure artifacts directory exists
        context.artifact_dir.mkdir(parents=True, exist_ok=True)

        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import (
                SimpleDocTemplate,
                Paragraph,
                Spacer,
            )
            from reportlab.lib.units import inch
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

            # Try to register Chinese fonts
            chinese_font = "Helvetica"
            chinese_bold_font = "Helvetica-Bold"
            font_registered = False

            # Common Chinese fonts to try
            chinese_fonts = [
                ("msyh.ttc", "Microsoft YaHei"),
                ("simsun.ttc", "SimSun"),
                ("simhei.ttf", "SimHei"),
                ("STHeiti Light.ttc", "STHeiti"),
            ]

            for font_path, font_name in chinese_fonts:
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    chinese_font = font_name
                    chinese_bold_font = font_name
                    font_registered = True
                    break
                except:
                    continue

            # Create PDF document
            doc = SimpleDocTemplate(
                str(output_path),
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72,
            )

            # Build story
            story = []
            styles = getSampleStyleSheet()

            # Custom styles
            title_style = ParagraphStyle(
                "CustomTitle",
                parent=styles["Heading1"],
                fontName=chinese_bold_font,
                fontSize=20,
                alignment=TA_CENTER,
                spaceAfter=20,
                textColor="#000000",
            )

            author_style = ParagraphStyle(
                "CustomAuthor",
                parent=styles["Normal"],
                fontName=chinese_font,
                fontSize=12,
                alignment=TA_CENTER,
                spaceAfter=30,
                textColor="#333333",
            )

            # Add title and metadata
            story.append(Paragraph(project.name, title_style))
            story.append(Spacer(1, 12))

            # Add metadata if available from original blocks
            if blocks and hasattr(blocks[0], "metadata"):
                metadata = blocks[0].metadata
                if metadata and "original_metadata" in metadata:
                    original_meta = metadata["original_metadata"]
                    if isinstance(original_meta, dict):
                        if original_meta.get("author"):
                            story.append(Paragraph(f"作者: {original_meta['author']}", author_style))
                        if original_meta.get("title"):
                            story.append(Paragraph(f"原标题: {original_meta['title']}", author_style))

            story.append(Spacer(1, 20))

            # Body text style
            body_style = ParagraphStyle(
                "BodyText",
                parent=styles["BodyText"],
                fontName=chinese_font,
                fontSize=11,
                leading=16,
                alignment=TA_JUSTIFY,
                spaceAfter=12,
                textColor="#000000",
            )

            # Chunk heading style
            chunk_style = ParagraphStyle(
                "ChunkHeading",
                parent=styles["Heading2"],
                fontName=chinese_bold_font,
                fontSize=14,
                spaceAfter=10,
                spaceBefore=15,
                textColor="#333333",
            )

            # Process content from chunks
            for i, chunk in enumerate(chunks):
                text = chunk.restored_text or chunk.target_text or ""
                if text:
                    # Add chunk separator if multiple chunks
                    if len(chunks) > 1:
                        chunk_title = f"第 {i + 1} 部分" if font_registered else f"Part {i + 1}"
                        story.append(Paragraph(chunk_title, chunk_style))

                    # Split text into paragraphs and add to story
                    paragraphs = text.split('\n\n')
                    for para in paragraphs:
                        para = para.strip()
                        if para:
                            # Simple heading detection
                            if len(para) < 100 and para.split('\n')[0] == para:
                                # Check if it looks like a heading
                                words = para.split()
                                if words and words[0][0].isupper() and len(words) < 10 and not para.endswith('.'):
                                    heading_level = min(len(words), 6)
                                    heading_style = ParagraphStyle(
                                        f"Heading{heading_level}",
                                        parent=styles[f"Heading{heading_level}"],
                                        fontName=chinese_bold_font,
                                        fontSize=max(12, 16 - heading_level),
                                        spaceAfter=10,
                                        spaceBefore=10,
                                    )
                                    story.append(Paragraph(para, heading_style))
                                else:
                                    story.append(Paragraph(para, body_style))
                            else:
                                story.append(Paragraph(para, body_style))

                    story.append(Spacer(1, 12))

            # Build PDF
            doc.build(story)

        except ImportError as e:
            raise ImportError(
                f"reportlab is required for PDF generation. Install with: pip install reportlab\n"
                f"Fallback error: {e}"
            )
        except Exception as e:
            # If PDF generation fails, fall back to markdown
            print(f"[PDF_EXPORT_ERROR] Failed to generate PDF: {e}")
            print(f"[PDF_EXPORT_ERROR] Falling back to markdown format")
            fallback_exporter = MarkdownPdfExporter()
            return fallback_exporter.export(
                project, context, blocks, chunks, reports, draft
            )

        return output_path


class PlainTextPdfExporter(PdfExporter):
    """Export translated content as plain text."""

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[Any],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> Path:
        """Export as plain text format."""
        output_path = context.artifact_dir / f"{project.name}_translated.txt"

        # Ensure artifacts directory exists
        context.artifact_dir.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            # Write header
            f.write(f"{project.name}\n")
            f.write("=" * len(project.name) + "\n\n")

            # Write content from chunks
            for i, chunk in enumerate(chunks):
                text = chunk.restored_text or chunk.target_text or ""
                if text:
                    # Add chunk separator if multiple chunks
                    if len(chunks) > 1:
                        f.write(f"\n--- Chunk {i + 1} ---\n\n")
                    f.write(f"{text}\n\n")

        return output_path


class PdfExporterFactory:
    """Factory for creating PDF exporters."""

    def __init__(self):
        self._exporters = {
            "markdown": MarkdownPdfExporter(),
            "simple_pdf": SimplePdfExporter(),
            "plain_text": PlainTextPdfExporter(),
        }

    def get_exporter(self, format_type: str = "markdown") -> PdfExporter:
        """Get exporter by format type."""
        exporter = self._exporters.get(format_type)
        if not exporter:
            raise ValueError(f"Unknown export format: {format_type}")
        return exporter

    def list_formats(self) -> list[str]:
        """List available export formats."""
        return list(self._exporters.keys())
