"""Cross-page content handling utilities for PDF processing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class PageContent:
    """Represents content extracted from a single page."""

    page_index: int
    text: str
    blocks: list[dict[str, Any]]
    metadata: dict[str, Any]

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def block_count(self) -> int:
        return len(self.blocks)


@dataclass
class ContentBlock:
    """Represents a merged content block (may span multiple pages)."""

    text: str
    source_pages: list[int]
    block_type: str = "paragraph"
    metadata: dict[str, Any] | None = None


class CrossPageMerger:
    """Merge content that spans across page boundaries."""

    def __init__(
        self,
        min_paragraph_length: int = 100,
        continuation_threshold: float = 0.7,
    ):
        self.min_paragraph_length = min_paragraph_length
        self.continuation_threshold = continuation_threshold

    def merge_cross_page_content(
        self, pages: list[PageContent]
    ) -> list[ContentBlock]:
        """Rebuild paragraphs and sentences that span across pages."""
        if not pages:
            return []

        merged_blocks = []
        pending_content = ""

        for i, page in enumerate(pages):
            page_text = page.text.strip()

            # Check if this is the last page
            is_last_page = i == len(pages) - 1

            # Check if page ends with incomplete content
            if self._is_incomplete_ending(page_text) and not is_last_page:
                # Check if next page starts with continuation
                if i + 1 < len(pages):
                    next_page = pages[i + 1]
                    next_text = next_page.text.strip()

                    if self._is_continuation_start(next_text):
                        # Merge across page boundary
                        pending_content = page_text + " " + next_text
                        # Skip next page's start since we already merged it
                        i += 1
                        continue

            # Handle any pending content
            if pending_content:
                merged_blocks.append(
                    ContentBlock(
                        text=pending_content,
                        source_pages=[i, i + 1],
                        block_type="paragraph",
                    )
                )
                pending_content = ""

            # Add current page content as separate block
            if page_text:
                merged_blocks.append(
                    ContentBlock(
                        text=page_text,
                        source_pages=[i],
                        block_type="paragraph",
                        metadata=page.metadata,
                    )
                )

        return merged_blocks

    def _is_incomplete_ending(self, text: str) -> bool:
        """Check if text ends with an incomplete sentence."""
        if not text or len(text) < 50:
            return False

        # Get last 200 characters for analysis
        ending = text[-200:] if len(text) > 200 else text
        ending = ending.strip()

        # Check for sentence-ending punctuation
        if re.search(r"[.!?]\s*$", ending):
            return False

        # Check for common ending patterns
        if re.search(r"\b(the|and|or|but|in|on|at|to|for|of|with)\s*$", ending, re.I):
            return True

        # Check if ends with lowercase letter (likely mid-sentence)
        if ending[-1].islower():
            return True

        # Check if ends with hyphen (word broken across pages)
        if ending.endswith("-"):
            return True

        # Check if ends without proper punctuation
        if not ending[-1] in {".", "!", "?", '"', "'", ")", "】", "》"}:
            # But exclude cases where ending looks complete
            if len(ending.split()) > 3:  # Has multiple words
                return True

        return False

    def _is_continuation_start(self, text: str) -> bool:
        """Check if text starts with continuation from previous page."""
        if not text or len(text) < 20:
            return False

        # Get first 200 characters for analysis
        beginning = text[:200] if len(text) > 200 else text
        beginning = beginning.strip()

        # Check if starts with lowercase letter
        if beginning[0].islower():
            return True

        # Check if starts with continuation pattern
        if re.match(r"^[a-z]{2,}", beginning):
            return True

        # Check if starts with common continuation words
        continuation_patterns = [
            r"^(and|or|but|however|therefore|moreover|furthermore)",
            r"^(which|that|this|these|those)",
            r"^(also|too|as well)",
        ]
        for pattern in continuation_patterns:
            if re.match(pattern, beginning, re.I):
                return True

        return False

    def merge_short_blocks(
        self, blocks: list[ContentBlock], min_length: int = 50
    ) -> list[ContentBlock]:
        """Merge blocks that are too short with adjacent blocks."""
        if not blocks:
            return []

        merged = []
        current_merged = blocks[0]

        for block in blocks[1:]:
            # If current merged block is too short, merge with next
            if len(current_merged.text) < min_length:
                current_merged = ContentBlock(
                    text=current_merged.text + " " + block.text,
                    source_pages=current_merged.source_pages + block.source_pages,
                    block_type=current_merged.block_type,
                )
            else:
                merged.append(current_merged)
                current_merged = block

        # Add the last merged block
        if current_merged:
            merged.append(current_merged)

        return merged

    def detect_content_boundaries(self, pages: list[PageContent]) -> dict[int, dict[str, Any]]:
        """Detect logical content boundaries across pages."""
        boundaries = {}

        for i, page in enumerate(pages):
            page_boundaries = {
                "has_start_boundary": self._is_page_start_boundary(page, pages, i),
                "has_end_boundary": self._is_page_end_boundary(page, pages, i),
                "start_boundary_type": None,
                "end_boundary_type": None,
            }

            if page_boundaries["has_start_boundary"]:
                page_boundaries["start_boundary_type"] = self._detect_boundary_type(
                    page.text, "start"
                )

            if page_boundaries["has_end_boundary"]:
                page_boundaries["end_boundary_type"] = self._detect_boundary_type(
                    page.text, "end"
                )

            boundaries[i] = page_boundaries

        return boundaries

    def _is_page_start_boundary(
        self, page: PageContent, pages: list[PageContent], index: int
    ) -> bool:
        """Check if page starts a new content section."""
        if index == 0:
            return True

        # Check if previous page ended cleanly
        prev_page = pages[index - 1]
        prev_ending = prev_page.text.strip()[-100:] if len(prev_page.text) > 100 else prev_page.text

        # If previous page ended with sentence-ending punctuation, this is a boundary
        if re.search(r"[.!?]\s*$", prev_ending):
            return True

        # Check if current page starts with heading or section marker
        current_start = page.text.strip()[:100] if len(page.text) > 100 else page.text
        if re.match(r"^#+\s|[A-Z][A-Z\s]{5,}|^\d+\.\s", current_start):
            return True

        return False

    def _is_page_end_boundary(
        self, page: PageContent, pages: list[PageContent], index: int
    ) -> bool:
        """Check if page ends a content section."""
        if index == len(pages) - 1:
            return True

        # Use the incomplete ending check
        return not self._is_incomplete_ending(page.text)

    def _detect_boundary_type(self, text: str, position: str) -> str | None:
        """Detect the type of content boundary."""
        sample = text[:200] if position == "start" else text[-200:]
        sample = sample.strip()

        # Check for heading patterns
        heading_patterns = [
            r"^#+\s+",  # Markdown headings
            r"^[A-Z][A-Z\s]{5,}$",  # All caps headings
            r"^\d+\.\s+[A-Z]",  # Numbered sections
            r"^Chapter\s+\d+",  # Chapter headings
        ]

        if position == "start":
            for pattern in heading_patterns:
                if re.match(pattern, sample):
                    return "heading"

        # Check for sentence endings
        if position == "end":
            if re.search(r"[.!?]\s*$", sample):
                return "sentence_end"

        return "boundary"


class ContentReconstructor:
    """Reconstruct continuous content from page-based extraction."""

    def __init__(self):
        self.merger = CrossPageMerger()

    def reconstruct_document(
        self, pages: list[PageContent]
    ) -> dict[str, Any]:
        """Reconstruct document structure from pages."""
        # Detect boundaries
        boundaries = self.merger.detect_content_boundaries(pages)

        # Merge cross-page content
        merged_blocks = self.merger.merge_cross_page_content(pages)

        # Merge very short blocks
        final_blocks = self.merger.merge_short_blocks(merged_blocks)

        return {
            "blocks": final_blocks,
            "boundaries": boundaries,
            "original_pages": len(pages),
            "final_blocks": len(final_blocks),
        }
