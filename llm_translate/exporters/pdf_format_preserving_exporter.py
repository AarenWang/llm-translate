"""Format-preserving PDF exporter that maintains original layout."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..domain import TranslationProject, TranslationChunk, ValidationReport
from ..formats.base import FormatContext


class FormatPreservingPdfExporter:
    """Export translated content while preserving original PDF formatting."""

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[Any],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> Path:
        """Export as format-preserved PDF."""
        output_path = self._writable_output_path(
            context.artifact_dir / f"{project.name}_format_preserved.pdf"
        )

        # Ensure artifacts directory exists
        context.artifact_dir.mkdir(parents=True, exist_ok=True)

        try:
            import pymupdf  # PyMuPDF

            # Open original PDF
            original_pdf_path = context.source_path
            doc = pymupdf.open(original_pdf_path)

            # Create mapping from original layout blocks to translated text.
            block_translation_map = self._build_block_translation_map(blocks, chunks)
            source_translation_map = self._build_translation_map(blocks, chunks)
            font_file = self._find_cjk_font()

            # Process each page
            for page_num in range(len(doc)):
                page = doc[page_num]
                self._translate_page(
                    page=page,
                    blocks=blocks,
                    block_translation_map=block_translation_map,
                    source_translation_map=source_translation_map,
                    page_num=page_num,
                    font_file=font_file,
                )

            # Save the modified PDF
            doc.save(str(output_path), garbage=4, deflate=True)
            doc.close()

        except ImportError:
            # Fallback to PyPDF2/PyPDF if PyMuPDF is not available
            try:
                import pypdf

                self._export_with_pypdf(
                    original_pdf_path=context.source_path,
                    output_path=output_path,
                    translation_map=self._build_translation_map(blocks, chunks),
                )
            except ImportError:
                raise ImportError(
                    "Neither PyMuPDF nor PyPDF is available for PDF format preservation. "
                    "Install PyMuPDF with: pip install pymupdf"
                )

        return output_path

    def _writable_output_path(self, preferred: Path) -> Path:
        if not preferred.exists():
            return preferred
        try:
            preferred.unlink()
            return preferred
        except OSError:
            for index in range(1, 100):
                candidate = preferred.with_name(f"{preferred.stem}_{index}{preferred.suffix}")
                if not candidate.exists():
                    return candidate
            raise

    def _build_block_translation_map(
        self, blocks: list[Any], chunks: list[TranslationChunk]
    ) -> dict[str, str]:
        """Map each DocumentBlock id to the corresponding translated paragraph."""
        translations: dict[str, str] = {}
        block_by_id = {
            block.id: block
            for block in blocks
            if hasattr(block, "id") and getattr(block, "source_text", "").strip()
        }

        for chunk in chunks:
            translated = (chunk.restored_text or chunk.target_text or "").strip()
            if not translated:
                continue

            chunk_blocks = [block_by_id[block_id] for block_id in chunk.block_ids if block_id in block_by_id]
            if not chunk_blocks:
                continue

            target_parts = self._split_translated_blocks(translated)
            if len(target_parts) == len(chunk_blocks):
                for block, target_text in zip(chunk_blocks, target_parts):
                    translations[block.id] = self._clean_translated_text(target_text)
                continue

            if len(chunk_blocks) == 1:
                translations[chunk_blocks[0].id] = self._clean_translated_text(translated)
                continue

            # Best-effort fallback: keep deterministic order and avoid dropping text.
            for block, target_text in zip(chunk_blocks, target_parts):
                translations[block.id] = self._clean_translated_text(target_text)

        return translations

    def _build_translation_map(
        self, blocks: list[Any], chunks: list[TranslationChunk]
    ) -> dict[str, str]:
        """Build mapping from source text to translated text."""
        translation_map = {}

        # Build map from DocumentBlocks
        for block in blocks:
            if hasattr(block, "source_text") and hasattr(block, "target_text"):
                source_text = block.source_text.strip()
                target_text = block.target_text.strip() if block.target_text else ""
                if source_text and target_text:
                    # Use first 100 chars as key for longer texts
                    key = source_text[:100] if len(source_text) > 100 else source_text
                    translation_map[source_text] = target_text

        # Also build map from chunks
        for chunk in chunks:
            if chunk.source_text and chunk.restored_text:
                # Split into paragraphs
                source_paragraphs = chunk.source_text.split('\n\n')
                target_paragraphs = chunk.restored_text.split('\n\n')

                for src, tgt in zip(source_paragraphs, target_paragraphs):
                    src, tgt = src.strip(), tgt.strip()
                    if src and tgt:
                        translation_map[src] = tgt

        return translation_map

    def _translate_page(
        self,
        page: Any,
        blocks: list[Any],
        block_translation_map: dict[str, str],
        source_translation_map: dict[str, str],
        page_num: int,
        font_file: str | None,
    ) -> None:
        """Translate text on a single page while preserving formatting."""
        try:
            import pymupdf

            page_blocks = [
                block
                for block in blocks
                if getattr(block, "metadata", {}).get("format") == "pdf"
                and getattr(block, "metadata", {}).get("page_index") == page_num
            ]

            replacements = []
            for block in page_blocks:
                source_text = getattr(block, "source_text", "").strip()
                if not source_text:
                    continue

                translated_text = block_translation_map.get(block.id)
                if not translated_text:
                    translated_text = self._find_translation(source_text, source_translation_map)
                if not translated_text or translated_text == source_text:
                    continue

                rect_values = block.metadata.get("rect")
                if not rect_values or len(rect_values) != 4:
                    continue

                rect = pymupdf.Rect(*rect_values)
                rect = self._expand_rect(rect, page.rect, margin=1.5)
                font_size = self._fit_font_size(page, rect, source_text, translated_text, font_file)
                replacements.append((rect, translated_text, font_size))

            if not replacements:
                return

            for rect, _translated_text, _font_size in replacements:
                page.add_redact_annot(rect, fill=(1, 1, 1))

            page.apply_redactions(images=0, graphics=0, text=0)

            for rect, translated_text, font_size in replacements:
                self._insert_textbox(page, rect, translated_text, font_size, font_file)

        except Exception as e:
            print(f"[PDF_TRANSLATE_WARN] Page {page_num} translation failed: {e}")

    def _split_translated_blocks(self, text: str) -> list[str]:
        parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        return parts or ([text.strip()] if text.strip() else [])

    def _clean_translated_text(self, text: str) -> str:
        """Remove common Markdown wrappers that LLMs may add around plain PDF text."""
        cleaned_lines = []
        for line in text.splitlines():
            line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
            line = re.sub(r"^\s*[-*]\s+", "", line)
            line = line.replace("**", "").replace("__", "")
            cleaned_lines.append(line.strip())
        return "\n".join(line for line in cleaned_lines if line)

    def _expand_rect(self, rect: Any, page_rect: Any, margin: float) -> Any:
        import pymupdf

        return pymupdf.Rect(
            max(page_rect.x0, rect.x0 - margin),
            max(page_rect.y0, rect.y0 - margin),
            min(page_rect.x1, rect.x1 + margin),
            min(page_rect.y1, rect.y1 + margin),
        )

    def _fit_font_size(
        self,
        page: Any,
        rect: Any,
        original_text: str,
        translated_text: str,
        font_file: str | None,
    ) -> float:
        original_lines = [line for line in original_text.splitlines() if line.strip()]
        line_height = rect.height / max(1, len(original_lines))
        base_size = max(5.0, min(12.0, line_height * 0.72))

        # Chinese translations can be denser than English, but still need room
        # for wrapping inside fixed PDF rectangles.
        length_ratio = len(original_text) / max(1, len(translated_text))
        size = max(4.5, min(base_size, base_size * max(0.55, min(1.1, length_ratio))))

        while size >= 4.5:
            if self._estimated_text_fits(rect, translated_text, size):
                return size
            size -= 0.5

        return 4.5

    def _estimated_text_fits(self, rect: Any, text: str, font_size: float) -> bool:
        average_char_width = font_size * 0.58
        chars_per_line = max(1, int(rect.width / max(1, average_char_width)))
        line_count = 0
        for raw_line in text.splitlines() or [text]:
            stripped = raw_line.strip()
            if not stripped:
                line_count += 1
                continue
            line_count += max(1, (len(stripped) + chars_per_line - 1) // chars_per_line)
        return line_count * font_size * 1.2 <= rect.height

    def _insert_textbox(
        self, page: Any, rect: Any, translated_text: str, font_size: float, font_file: str | None
    ) -> None:
        page.insert_textbox(
            rect,
            translated_text,
            fontsize=font_size,
            fontname="msyh" if font_file else "helv",
            fontfile=font_file,
            color=(0, 0, 0),
            overlay=True,
        )

    def _find_cjk_font(self) -> str | None:
        candidates = [
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/simsun.ttc"),
            Path("C:/Windows/Fonts/simhei.ttf"),
            Path("/System/Library/Fonts/PingFang.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _find_translation(
        self, source_text: str, translation_map: dict[str, str]
    ) -> str | None:
        """Find translation for source text with fuzzy matching."""
        # Direct match
        if source_text in translation_map:
            return translation_map[source_text]

        # Try partial matches for longer texts
        if len(source_text) > 50:
            # Try first half
            first_half = source_text[: len(source_text) // 2]
            for key, value in translation_map.items():
                if key.startswith(first_half):
                    return value

            # Try last half
            last_half = source_text[len(source_text) // 2:]
            for key, value in translation_map.items():
                if key.endswith(last_half):
                    return value

        # Try word-level matching
        source_words = source_text.split()[:5]  # First 5 words
        for key, value in translation_map.items():
            key_words = key.split()[:5]
            if source_words == key_words:
                return value

        return None

    def _estimate_font_size(
        self, x0: float, y0: float, x1: float, y1: float, original_text: str, translated_text: str
    ) -> float:
        """Estimate appropriate font size to fit translated text in original space."""
        # Calculate original area
        width = x1 - x0
        height = y1 - y0

        # Estimate original font size from height
        original_font_size = max(8, min(height, 12))

        # Calculate text length ratio
        original_len = len(original_text)
        translated_len = len(translated_text)

        if original_len > 0:
            ratio = original_len / max(1, translated_len)
            # Adjust font size based on text length ratio
            adjusted_size = original_font_size * ratio
            # Keep within reasonable bounds
            return max(6, min(adjusted_size, 14))

        return original_font_size

    def _export_with_pypdf(
        self, original_pdf_path: Path, output_path: Path, translation_map: dict[str, str]
    ) -> None:
        """Export using PyPDF when PyMuPDF is not available."""
        try:
            from pypdf import PdfReader, PdfWriter
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            import io

            # Read original PDF
            reader = PdfReader(original_pdf_path)
            writer = PdfWriter()

            # Process each page
            for page_num, page in enumerate(reader.pages):
                # Extract text from page
                try:
                    text = page.extract_text()
                    if text:
                        # Try to translate and update
                        # Note: PyPDF has limited text modification capabilities
                        # This is a simplified approach
                        pass
                except Exception as e:
                    print(f"[PYPDF_WARN] Page {page_num} processing failed: {e}")

                # Add original page (PyPDF can't easily modify text in place)
                writer.add_page(page)

            # Write the PDF (will be mostly unchanged due to PyPDF limitations)
            with open(output_path, "wb") as f:
                writer.write(f)

        except Exception as e:
            print(f"[PYPDF_ERROR] PDF format preservation failed: {e}")
            raise
