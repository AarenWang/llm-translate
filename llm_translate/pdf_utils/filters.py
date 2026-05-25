"""Content filtering utilities for PDF processing."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any
import re

from .layout import TextBlock


@dataclass
class FilterResult:
    """Result of content filtering."""

    filtered_blocks: list[TextBlock]
    removed_count: int
    removal_reasons: dict[str, int]


class RepeatingPatternFilter:
    """Filter repeating patterns like headers, footers, page numbers."""

    def __init__(self, min_repetition_ratio: float = 0.6):
        self.min_repetition_ratio = min_repetition_ratio

    def filter_repeating_patterns(
        self, pages_blocks: list[list[TextBlock]]
    ) -> FilterResult:
        """Filter out repeating patterns across pages."""
        if not pages_blocks:
            return FilterResult(filtered_blocks=[], removed_count=0, removal_reasons={})

        # Identify repeating patterns
        repeating_patterns = self._identify_repeating_patterns(pages_blocks)

        # Filter blocks
        filtered_blocks = []
        removed_count = 0
        removal_reasons: dict[str, int] = {}

        for page_blocks in pages_blocks:
            for block in page_blocks:
                normalized = self._normalize_text(block.text)
                if self._is_repeating_pattern(normalized, repeating_patterns):
                    removed_count += 1
                    reason = "repeating_pattern"
                    removal_reasons[reason] = removal_reasons.get(reason, 0) + 1
                else:
                    filtered_blocks.append(block)

        return FilterResult(
            filtered_blocks=filtered_blocks,
            removed_count=removed_count,
            removal_reasons=removal_reasons,
        )

    def _identify_repeating_patterns(
        self, pages_blocks: list[list[TextBlock]]
    ) -> list[str]:
        """Identify patterns that repeat across multiple pages."""
        all_patterns: list[str] = []

        # Collect potential patterns from page edges
        for page_blocks in pages_blocks:
            page_patterns = self._extract_page_edge_patterns(page_blocks)
            all_patterns.extend(page_patterns)

        if not all_patterns:
            return []

        # Count repetitions
        pattern_counts = Counter(all_patterns)
        total_pages = len(pages_blocks)
        min_count = max(2, int(total_pages * self.min_repetition_ratio))

        # Find patterns that repeat frequently
        repeating = [
            pattern for pattern, count in pattern_counts.items() if count >= min_count
        ]

        return repeating

    def _extract_page_edge_patterns(self, blocks: list[TextBlock]) -> list[str]:
        """Extract potential repeating patterns from page edges."""
        if not blocks:
            return []

        # Get page bounds
        y_positions = [b.y0 for b in blocks] + [b.y1 for b in blocks]
        min_y = min(y_positions)
        max_y = max(y_positions)
        page_height = max_y - min_y

        patterns = []

        for block in blocks:
            # Check if in top 10% or bottom 10%
            if block.y1 < min_y + page_height * 0.10:  # Top
                normalized = self._normalize_text(block.text)
                if self._is_valid_pattern(normalized):
                    patterns.append(normalized)
            elif block.y0 > max_y - page_height * 0.10:  # Bottom
                normalized = self._normalize_text(block.text)
                if self._is_valid_pattern(normalized):
                    patterns.append(normalized)

        return patterns

    def _normalize_text(self, text: str) -> str:
        """Normalize text for pattern matching."""
        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text.strip())
        # Replace page numbers
        text = re.sub(r"\bpage\s+\d+\b", "PAGE_NUM", text, flags=re.I)
        text = re.sub(r"^\d+$", "NUM_ONLY", text)
        # Replace common patterns
        text = re.sub(r"\b\d{1,3}\s*of\s*\d{1,3}\b", "PAGE_RANGE", text, flags=re.I)
        return text.lower()

    def _is_valid_pattern(self, normalized: str) -> bool:
        """Check if normalized text is a valid repeating pattern."""
        # Must be reasonable length
        if len(normalized) < 2 or len(normalized) > 150:
            return False

        # Should not be too generic
        generic_patterns = ["page_num", "num_only", "page_range"]
        if normalized in generic_patterns:
            return False

        return True

    def _is_repeating_pattern(
        self, normalized: str, repeating_patterns: list[str]
    ) -> bool:
        """Check if normalized text matches any repeating pattern."""
        return normalized in repeating_patterns


class ContentFilter:
    """Main content filtering coordinator."""

    def __init__(self):
        self.repeating_filter = RepeatingPatternFilter()

    def filter_all(
        self, pages_blocks: list[list[TextBlock]]
    ) -> FilterResult:
        """Apply all content filters."""
        # Filter repeating patterns
        result = self.repeating_filter.filter_repeating_patterns(pages_blocks)

        return result

    def filter_single_page(
        self, blocks: list[TextBlock], page_context: dict[str, Any] | None = None
    ) -> list[TextBlock]:
        """Filter blocks from a single page."""
        # For single page filtering, apply basic filters
        filtered = []

        for block in blocks:
            # Skip empty blocks
            if not block.text or not block.text.strip():
                continue

            # Skip very short blocks (likely artifacts)
            if len(block.text.strip()) < 2:
                continue

            filtered.append(block)

        return filtered
