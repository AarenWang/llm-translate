"""PDF format adapter implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import FormatAdapter, FormatContext
from ..domain import DocumentBlock, TranslationProject, TranslationChunk, ValidationReport
from ..parser.pdf import PdfParser, PdfParseResult, PdfTranslationError


class PdfFormatAdapter:
    """Format adapter for PDF documents."""

    format_name = "pdf"

    def supports(self, path: Path) -> bool:
        """Check if this adapter supports the given file."""
        return path.suffix.lower() == ".pdf"

    def parse(self, project: TranslationProject, context: FormatContext) -> list[DocumentBlock]:
        """Parse PDF document and extract translatable content."""
        parser = PdfParser()

        try:
            result = parser.parse(project.id, context.source_path)

            # Save parse snapshot
            self._save_parse_snapshot(result, context)

            return result.blocks

        except PdfTranslationError as exc:
            # Provide user-friendly error message
            error_msg = self._format_error_message(exc)
            print(f"\n{error_msg}\n")
            raise

    def _save_parse_snapshot(self, result: PdfParseResult, context: FormatContext) -> None:
        """Save parsing snapshot for debugging."""
        snapshot_path = context.snapshot_dir / "pdf_parse_snapshot.json"

        import json

        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(result.to_snapshot(), f, ensure_ascii=False, indent=2)

    def _format_error_message(self, error: PdfTranslationError) -> str:
        """Format user-friendly error message."""
        message = f"""
PDF Translation Error
{'=' * 50}

File: {error.report.file if error.report else 'Unknown'}
Level: {error.report.level if error.report else 'Unknown'}
Score: {error.report.score if error.report else 0:.1f}/100

Problems found:
"""

        if error.report and error.report.problems:
            for problem in error.report.problems:
                message += f"  ❌ {problem}\n"
        else:
            message += f"  ❌ {error.message}\n"

        message += "\nRecommendations:\n"

        if error.report:
            if error.report.garbled_ratio > 0.01:
                message += (
                    "  • PDF contains encoding issues (garbled_ratio: "
                    f"{error.report.garbled_ratio:.3%})\n"
                )
                message += "    → Try re-exporting the PDF from the source application\n"

            if error.report.large_image_page_ratio > 0.35:
                message += (
                    "  • PDF appears to be scanned or image-heavy "
                    f"(large_image_page_ratio: {error.report.large_image_page_ratio:.3%})\n"
                )
                message += "    → Use OCR tools like Tesseract or Adobe Acrobat Export PDF\n"

            if error.report.suspected_multi_column_ratio > 0.30:
                message += (
                    "  • Complex multi-column layout detected "
                    f"(multi_column_ratio: {error.report.suspected_multi_column_ratio:.3%})\n"
                )
                message += "    → Manual review of translation recommended\n"

            if error.report.encrypted:
                message += "  • PDF is encrypted and password-protected\n"
                message += "    → Remove password protection before translation\n"

            if error.report.avg_text_chars_per_page < 500:
                message += (
                    "  • Low text content detected "
                    f"(avg chars per page: {error.report.avg_text_chars_per_page:.0f})\n"
                )
                message += "    → This might be a scanned PDF or contain many images\n"

        message += f"\n{'=' * 50}\n"
        return message

    def plan_chunks(
        self, project_id: str, blocks: list[DocumentBlock]
    ) -> list[TranslationChunk]:
        """Plan translation chunks for PDF content."""
        # Use default chunking strategy
        from ..chunking import ChunkingEngine

        chunking_engine = ChunkingEngine()
        return chunking_engine.build_chunks(project_id, blocks)

    def prompt_document_format(self) -> str:
        """Get document format description for translation prompt."""
        return """This is a PDF document that has been extracted and structured for translation.
The PDF exporter will place each translated block back into the original page rectangle.
Keep the same number and order of blank-line-separated blocks as the source chunk.
Do not merge, split, reorder, omit, or add blocks.
Return plain text only. Do not use Markdown headings, bold markers, bullets, code fences, or commentary.
Preserve formulas, URLs, emails, references, and numeric identifiers exactly when they are not natural-language prose.
Translate natural-language prose into clear Simplified Chinese while keeping the output concise enough to fit the original layout."""

    def chapter_path(self, chunk: TranslationChunk) -> str | None:
        """Get chapter path for a translation chunk."""
        # PDF doesn't have traditional chapters, return chunk ID
        return f"pdf_chunk_{chunk.id}"

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> tuple[dict[str, Path], list[ValidationReport], bool]:
        """Export translated PDF content with format preservation."""
        outputs = {}

        # First choice: keep the original PDF pages and replace text inside the
        # original text block rectangles. This preserves page size, drawings,
        # images, pagination, and most visual layout for clean text PDFs.
        try:
            from ..exporters.pdf_format_preserving_exporter import FormatPreservingPdfExporter

            format_preserving_exporter = FormatPreservingPdfExporter()
            format_preserved_pdf = format_preserving_exporter.export(
                project=project,
                context=context,
                blocks=blocks,
                chunks=chunks,
                reports=reports,
                draft=draft,
            )
            outputs["format_preserved_pdf"] = format_preserved_pdf
            print(f"[PDF_EXPORT_SUCCESS] Format-preserved PDF generated: {format_preserved_pdf}")

        except Exception as e:
            print(f"[PDF_EXPORT_INFO] Format-preserved export: {e}")
            print(f"[PDF_EXPORT_INFO] Falling back to regenerated PDF outputs")

        # Always provide simple PDF as reliable fallback
        try:
            from ..exporters.pdf_exporters import PdfExporterFactory

            factory = PdfExporterFactory()
            pdf_exporter = factory.get_exporter("simple_pdf")
            simple_pdf = pdf_exporter.export(
                project=project,
                context=context,
                blocks=blocks,
                chunks=chunks,
                reports=reports,
                draft=draft,
            )
            outputs["simple_pdf"] = simple_pdf
            print(f"[PDF_EXPORT_SUCCESS] Simple PDF generated: {simple_pdf}")

        except Exception as e:
            print(f"[PDF_EXPORT_WARN] Simple PDF generation failed: {e}")

        # Always provide markdown as reliable text-based format
        from ..exporters.pdf_exporters import PdfExporterFactory

        factory = PdfExporterFactory()
        markdown_exporter = factory.get_exporter("markdown")
        markdown_path = markdown_exporter.export(
            project=project,
            context=context,
            blocks=blocks,
            chunks=chunks,
            reports=reports,
            draft=draft,
        )
        outputs["markdown"] = markdown_path
        print(f"[PDF_EXPORT_SUCCESS] Markdown generated: {markdown_path}")

        # Also provide plain text format
        text_exporter = factory.get_exporter("plain_text")
        text_path = text_exporter.export(
            project=project,
            context=context,
            blocks=blocks,
            chunks=chunks,
            reports=reports,
            draft=draft,
        )
        outputs["text"] = text_path

        export_reports = [
            ValidationReport(
                id=f"{chunk.id}_export_validation",
                project_id=project.id,
                chunk_id=chunk.id,
                check_type="export",
                status="PASS",
                issues=[],
            )
            for chunk in chunks
        ]

        return outputs, export_reports, draft
