"""PDF parser implementation."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from ..domain import DocumentBlock
from ..pdf_cleanliness import PdfCleanlinessChecker, PdfCleanlinessReport
from ..pdf_utils import (
    HeaderFooterFilter,
    ImageFilter,
    MultiColumnResolver,
    TableDetector,
    ContentFilter,
    CrossPageMerger,
    PageContent,
    ContentBlock,
    TextBlock,
    ImageRegion,
)


@dataclass(frozen=True)
class PdfParseResult:
    """Result of parsing a PDF document."""

    blocks: list[DocumentBlock]
    tables: list[dict[str, Any]]
    metadata: dict[str, Any]
    cleanliness_report: PdfCleanlinessReport
    page_contents: list[PageContent]

    def to_snapshot(self) -> dict[str, Any]:
        """Convert parse result to snapshot for saving."""
        return {
            "blocks": [asdict(block) for block in self.blocks],
            "tables": self.tables,
            "metadata": self.metadata,
            "cleanliness_report": asdict(self.cleanliness_report),
            "page_count": len(self.page_contents),
        }


class PdfTranslationError(Exception):
    """Exception raised when PDF is not suitable for translation."""

    def __init__(self, message: str, report: PdfCleanlinessReport | None = None):
        self.message = message
        self.report = report
        super().__init__(self.message)


class PdfParser:
    """Parse PDF documents and extract translatable content."""

    def __init__(self):
        self.cleanliness_checker = PdfCleanlinessChecker()
        self.multi_column_resolver = MultiColumnResolver()
        self.header_footer_filter = HeaderFooterFilter()
        self.image_filter = ImageFilter()
        self.table_detector = TableDetector()
        self.content_filter = ContentFilter()
        self.cross_page_merger = CrossPageMerger()

    def parse(self, project_id: str, pdf_path: Path) -> PdfParseResult:
        """
        Parse a PDF document and extract translatable content.

        Args:
            project_id: Translation project identifier
            pdf_path: Path to the PDF file

        Returns:
            PdfParseResult containing extracted content and metadata

        Raises:
            PdfTranslationError: If PDF is not suitable for translation
        """
        # Step 1: Check PDF cleanliness
        report = self.cleanliness_checker.check(pdf_path)

        if not report.can_translate_phase1:
            error_msg = f"PDF check failed: {report.problems}"
            raise PdfTranslationError(error_msg, report)

        # Step 2: Open PDF and extract content
        try:
            import pymupdf

            doc = pymupdf.open(pdf_path)
        except ImportError:
            try:
                import fitz as pymupdf

                doc = pymupdf.open(pdf_path)
            except ImportError as exc:
                raise PdfTranslationError(
                    "PyMuPDF is required for PDF parsing. "
                    "Install it with: pip install pymupdf"
                )
        except Exception as exc:
            raise PdfTranslationError(f"Failed to open PDF: {exc}")

        try:
            return self._parse_open_document(project_id, pdf_path, doc, report)
        finally:
            close = getattr(doc, "close", None)
            if callable(close):
                close()

    def _parse_open_document(
        self,
        project_id: str,
        pdf_path: Path,
        doc: Any,
        report: PdfCleanlinessReport,
    ) -> PdfParseResult:
        """Parse an already-open PDF document."""

        # Step 1: Extract content from all pages
        page_contents = self._extract_all_pages(doc)

        # Step 2: Apply layout resolution based on PDF quality
        if report.suspected_multi_column_ratio > 0.2:
            page_contents = self._resolve_multi_column_layouts(page_contents, doc)

        # Step 3: Filter headers and footers
        page_contents = self._filter_headers_footers(page_contents)

        # Step 4: Filter image-overlapped text
        page_contents = self._filter_image_overlapped_text(page_contents, doc)

        # Step 5: Extract tables (if enabled by quality report)
        tables = []
        if report.level in {"VERY_CLEAN", "CLEAN"}:
            tables = self._extract_tables(page_contents, doc)

        # Step 6: Apply content filters
        all_blocks = [block for page in page_contents for block in page.blocks]

        # Convert to TextBlock objects for filtering
        all_text_blocks = []
        for page_content in page_contents:
            for block_dict in page_content.blocks:
                all_text_blocks.append(
                    TextBlock(
                        x0=block_dict["x0"],
                        y0=block_dict["y0"],
                        x1=block_dict["x1"],
                        y1=block_dict["y1"],
                        text=block_dict["text"],
                        page_index=page_content.page_index,
                    )
                )

        filter_result = self.content_filter.filter_single_page(all_text_blocks)

        # Convert filtered TextBlocks back to dict format
        filtered_blocks = [
            {
                "x0": tb.x0,
                "y0": tb.y0,
                "x1": tb.x1,
                "y1": tb.y1,
                "text": tb.text,
                "block_no": i,
                "block_type": 0,
            }
            for i, tb in enumerate(filter_result)
        ]

        # Update page contents with filtered blocks
        filtered_page_contents = []
        block_index = 0
        for page_content in page_contents:
            page_filtered_blocks = []
            for _ in page_content.blocks:
                if block_index < len(filtered_blocks):
                    page_filtered_blocks.append(filtered_blocks[block_index])
                    block_index += 1
            # Recreate page text from filtered blocks
            new_text = "\n".join(b["text"] for b in page_filtered_blocks)
            filtered_page_contents.append(
                PageContent(
                    page_index=page_content.page_index,
                    text=new_text,
                    blocks=page_filtered_blocks,
                    metadata=page_content.metadata,
                )
            )

        page_contents = filtered_page_contents

        # Step 7: Convert original PDF text blocks to DocumentBlock format.
        #
        # PDF is a fixed-layout format, so the exporter needs the original page
        # number and rectangle for each translated unit. Cross-page paragraph
        # merging is useful for plain text output, but it destroys the mapping
        # needed to put translated text back into the same visual boxes.
        blocks = self._convert_page_contents_to_document_blocks(page_contents, project_id)

        # Step 9: Extract metadata
        metadata = self._extract_metadata(doc, pdf_path, report)

        return PdfParseResult(
            blocks=blocks,
            tables=tables,
            metadata=metadata,
            cleanliness_report=report,
            page_contents=page_contents,
        )

    def _convert_page_contents_to_document_blocks(
        self, page_contents: list[PageContent], project_id: str
    ) -> list[DocumentBlock]:
        """Convert each original PDF text block to a layout-aware document block."""
        blocks: list[DocumentBlock] = []

        for page_content in page_contents:
            page_width = page_content.metadata.get("page_width")
            page_height = page_content.metadata.get("page_height")

            for block in page_content.blocks:
                text = block["text"].strip()
                if not text:
                    continue

                block_type, level = self._detect_pdf_block_type(text)
                block_id = f"{project_id}_pdf_p{page_content.page_index + 1}_b{len(blocks) + 1}"

                blocks.append(
                    DocumentBlock(
                        id=block_id,
                        project_id=project_id,
                        parent_id=None,
                        block_order=len(blocks),
                        block_type=block_type,
                        level=level,
                        source_text=text,
                        target_text=None,
                        metadata={
                            "format": "pdf",
                            "translatable": True,
                            "page_index": page_content.page_index,
                            "rect": [
                                block["x0"],
                                block["y0"],
                                block["x1"],
                                block["y1"],
                            ],
                            "block_no": block.get("block_no"),
                            "pdf_block_type": block.get("block_type"),
                            "page_width": page_width,
                            "page_height": page_height,
                            "line_count": len(text.splitlines()),
                        },
                    )
                )

        return blocks

    def _detect_pdf_block_type(self, text: str) -> tuple[str, int | None]:
        """Detect coarse PDF block type without relying on source generator metadata."""
        compact = " ".join(text.split())

        if re.match(r"^\d+\.\s+\S+", compact) and len(compact) < 120:
            return "heading", 1

        if compact.lower() == "references":
            return "heading", 1

        return "paragraph", None

    def _extract_all_pages(self, doc: Any) -> list[PageContent]:
        """Extract content from all pages."""
        page_contents = []

        for page_index in range(len(doc)):
            page = doc[page_index]

            # Get basic page info
            page_rect = page.rect
            page_width = page_rect.width
            page_height = page_rect.height
            page_area = page_width * page_height

            # Extract text blocks
            blocks = page.get_text("blocks") or []
            text_blocks = []

            for block in blocks:
                if len(block) >= 5:
                    x0, y0, x1, y1, text, block_no, block_type = block[:7]
                    if isinstance(text, str) and text.strip():
                        text_blocks.append(
                            {
                                "x0": float(x0),
                                "y0": float(y0),
                                "x1": float(x1),
                                "y1": float(y1),
                                "text": text.strip(),
                                "block_no": int(block_no),
                                "block_type": int(block_type),
                            }
                        )

            # Extract full text
            full_text = page.get_text("text") or ""

            # Extract image info
            images = []
            try:
                image_info = page.get_image_info(xrefs=True)
                images = list(image_info) if image_info else []
            except Exception:
                pass

            # Create page content
            page_content = PageContent(
                page_index=page_index,
                text=full_text,
                blocks=text_blocks,
                metadata={
                    "page_width": page_width,
                    "page_height": page_height,
                    "page_area": page_area,
                    "image_count": len(images),
                    "images": images,
                    "block_count": len(text_blocks),
                },
            )

            page_contents.append(page_content)

        return page_contents

    def _resolve_multi_column_layouts(
        self, page_contents: list[PageContent], doc: Any
    ) -> list[PageContent]:
        """Resolve multi-column layouts."""
        resolved_pages = []

        for page_content in page_contents:
            page_width = page_content.metadata.get("page_width", 600)
            blocks = page_content.blocks

            # Convert to TextBlock objects
            text_blocks = [
                TextBlock(
                    x0=b["x0"],
                    y0=b["y0"],
                    x1=b["x1"],
                    y1=b["y1"],
                    text=b["text"],
                    page_index=page_content.page_index,
                )
                for b in blocks
            ]

            # Detect columns
            columns = self.multi_column_resolver.detect_columns(text_blocks, page_width)

            # Reorder if multi-column
            if columns > 1:
                reordered = self.multi_column_resolver.reorder_blocks(text_blocks, columns)
                # Update page content with reordered blocks
                updated_blocks = [
                    {
                        "x0": tb.x0,
                        "y0": tb.y0,
                        "x1": tb.x1,
                        "y1": tb.y1,
                        "text": tb.text,
                        "block_no": i,
                        "block_type": 0,
                    }
                    for i, tb in enumerate(reordered)
                ]
                # Update full text
                new_text = "\n".join(tb.text for tb in reordered)

                resolved_pages.append(
                    PageContent(
                        page_index=page_content.page_index,
                        text=new_text,
                        blocks=updated_blocks,
                        metadata=page_content.metadata,
                    )
                )
            else:
                resolved_pages.append(page_content)

        return resolved_pages

    def _filter_headers_footers(
        self, page_contents: list[PageContent]
    ) -> list[PageContent]:
        """Filter headers and footers from pages."""
        # Convert to TextBlock objects for filtering
        pages_text_blocks = []
        for page_content in page_contents:
            text_blocks = [
                TextBlock(
                    x0=b["x0"],
                    y0=b["y0"],
                    x1=b["x1"],
                    y1=b["y1"],
                    text=b["text"],
                    page_index=page_content.page_index,
                )
                for b in page_content.blocks
            ]
            pages_text_blocks.append(text_blocks)

        # Identify repeating patterns
        repeating_patterns = (
            self.header_footer_filter.identify_repeating_elements(pages_text_blocks)
        )

        # Filter blocks
        filtered_pages = []
        for page_content, text_blocks in zip(page_contents, pages_text_blocks):
            filtered_blocks = self.header_footer_filter.filter_blocks(
                text_blocks, repeating_patterns
            )

            # Update page content
            filtered_blocks_data = [
                {
                    "x0": tb.x0,
                    "y0": tb.y0,
                    "x1": tb.x1,
                    "y1": tb.y1,
                    "text": tb.text,
                    "block_no": i,
                    "block_type": 0,
                }
                for i, tb in enumerate(filtered_blocks)
            ]
            new_text = "\n".join(tb.text for tb in filtered_blocks)

            filtered_pages.append(
                PageContent(
                    page_index=page_content.page_index,
                    text=new_text,
                    blocks=filtered_blocks_data,
                    metadata=page_content.metadata,
                )
            )

        return filtered_pages

    def _filter_image_overlapped_text(
        self, page_contents: list[PageContent], doc: Any
    ) -> list[PageContent]:
        """Filter text that overlaps with images."""
        filtered_pages = []

        for page_content in page_contents:
            # Identify image regions
            image_regions = self.image_filter.identify_image_regions(
                page_content.metadata, page_content.page_index
            )

            # Convert to TextBlock objects
            text_blocks = [
                TextBlock(
                    x0=b["x0"],
                    y0=b["y0"],
                    x1=b["x1"],
                    y1=b["y1"],
                    text=b["text"],
                    page_index=page_content.page_index,
                )
                for b in page_content.blocks
            ]

            # Filter overlapping blocks
            filtered_blocks = self.image_filter.filter_image_overlapped_text(
                text_blocks, image_regions
            )

            # Update page content
            filtered_blocks_data = [
                {
                    "x0": tb.x0,
                    "y0": tb.y0,
                    "x1": tb.x1,
                    "y1": tb.y1,
                    "text": tb.text,
                    "block_no": i,
                    "block_type": 0,
                }
                for i, tb in enumerate(filtered_blocks)
            ]
            new_text = "\n".join(tb.text for tb in filtered_blocks)

            filtered_pages.append(
                PageContent(
                    page_index=page_content.page_index,
                    text=new_text,
                    blocks=filtered_blocks_data,
                    metadata=page_content.metadata,
                )
            )

        return filtered_pages

    def _extract_tables(
        self, page_contents: list[PageContent], doc: Any
    ) -> list[dict[str, Any]]:
        """Extract tables from pages."""
        tables = []

        for page_content in page_contents:
            page_tables = self.table_detector.detect_tables(
                page_content.metadata, page_content.page_index
            )

            for table_region in page_tables:
                # Extract table structure
                table = self.table_detector.extract_table_structure(
                    table_region, page_content.blocks
                )

                tables.append(
                    {
                        "region": {
                            "x0": table_region.x0,
                            "y0": table_region.y0,
                            "x1": table_region.x1,
                            "y1": table_region.y1,
                            "rows": table_region.rows,
                            "cols": table_region.cols,
                            "confidence": table_region.confidence,
                            "page_index": table_region.page_index,
                        },
                        "markdown": table.to_markdown(),
                        "headers": table.headers,
                    }
                )

        return tables

    def _merge_cross_page_content(
        self, page_contents: list[PageContent]
    ) -> list[ContentBlock]:
        """Merge content that spans across page boundaries."""
        return self.cross_page_merger.merge_cross_page_content(page_contents)

    def _convert_to_document_blocks(
        self, content_blocks: list[ContentBlock], project_id: str
    ) -> list[DocumentBlock]:
        """Convert content blocks to DocumentBlock format."""
        blocks = []

        for i, content_block in enumerate(content_blocks):
            # Detect block type and heading level
            text = content_block.text.strip()
            if not text:
                continue

            # Simple heading detection
            heading_level = None
            block_type = "paragraph"

            if len(text) < 100 and text.split("\n")[0] == text:
                # Check for heading patterns
                words = text.split()
                if (
                    words
                    and words[0].istitle()
                    and len(words) < 10
                    and not text.endswith(".")
                ):
                    heading_level = 1
                    block_type = "heading"

            # Create DocumentBlock
            block = DocumentBlock(
                id=f"{project_id}_pdf_block_{i}",
                project_id=project_id,
                parent_id=None,
                block_order=i,
                block_type=block_type,
                level=heading_level or 0,
                source_text=text,
                target_text=None,
                metadata={
                    "source_pages": content_block.source_pages,
                    "original_metadata": content_block.metadata,
                },
            )

            blocks.append(block)

        return blocks

    def _extract_metadata(
        self, doc: Any, pdf_path: Path, report: PdfCleanlinessReport
    ) -> dict[str, Any]:
        """Extract document metadata."""
        metadata = {
            "source_file": str(pdf_path),
            "page_count": report.page_count,
            "encrypted": report.encrypted,
            "cleanliness_level": report.level,
            "cleanliness_score": report.score,
            "total_text_chars": report.total_text_chars,
            "avg_text_chars_per_page": report.avg_text_chars_per_page,
        }

        # Try to extract PDF metadata
        try:
            pdf_metadata = doc.metadata
            if pdf_metadata:
                metadata.update(
                    {
                        "title": pdf_metadata.get("title", ""),
                        "author": pdf_metadata.get("author", ""),
                        "subject": pdf_metadata.get("subject", ""),
                        "keywords": pdf_metadata.get("keywords", ""),
                        "creator": pdf_metadata.get("creator", ""),
                        "producer": pdf_metadata.get("producer", ""),
                    }
                )
        except Exception:
            pass

        return metadata
