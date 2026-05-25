"""Layout analysis utilities for PDF processing."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sklearn.cluster import DBSCAN
import numpy as np


@dataclass
class TextBlock:
    """Represents a text block in a PDF page."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block_type: str = "text"
    page_index: int = 0

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class ImageRegion:
    """Represents an image region in a PDF page."""

    x0: float
    y0: float
    x1: float
    y1: float
    area: float
    page_index: int = 0

    def overlaps_with(self, block: TextBlock, threshold: float = 0.5) -> bool:
        """Check if this image region overlaps with a text block."""
        # Calculate intersection area
        x_overlap = max(0, min(self.x1, block.x1) - max(self.x0, block.x0))
        y_overlap = max(0, min(self.y1, block.y1) - max(self.y0, block.y0))
        overlap_area = x_overlap * y_overlap

        block_area = block.width * block.height
        overlap_ratio = overlap_area / max(block_area, 1)

        return overlap_ratio > threshold


class MultiColumnResolver:
    """Multi-column layout detection and reordering."""

    def detect_columns(self, blocks: list[TextBlock], page_width: float) -> int:
        """Detect number of columns based on x-coordinate distribution."""
        if len(blocks) < 6:
            return 1

        # Get x positions of meaningful blocks
        x_positions = []
        for block in blocks:
            if len(block.text.strip()) >= 30:  # Only consider substantial blocks
                x_positions.append(block.center_x)

        if len(x_positions) < 6:
            return 1

        # Use clustering to detect columns
        x_array = np.array(x_positions).reshape(-1, 1)

        # Use DBSCAN with eps as percentage of page width
        eps = page_width * 0.15
        clustering = DBSCAN(eps=eps, min_samples=3).fit(x_array)

        unique_labels = set(clustering.labels_)
        # Remove noise points labeled as -1
        unique_labels.discard(-1)

        return max(1, len(unique_labels))

    def reorder_blocks(self, blocks: list[TextBlock], columns: int) -> list[TextBlock]:
        """Reorder multi-column blocks into reading order."""
        if columns <= 1:
            return blocks

        # Group blocks by rows (y-coordinate)
        rows = self._group_by_rows(blocks)

        # Sort each row by x-coordinate
        sorted_blocks = []
        for row in rows:
            sorted_row = sorted(row, key=lambda b: b.x0)
            sorted_blocks.extend(sorted_row)

        return sorted_blocks

    def _group_by_rows(self, blocks: list[TextBlock]) -> list[list[TextBlock]]:
        """Group blocks into rows based on y-coordinate."""
        if not blocks:
            return []

        # Get y positions
        y_positions = [block.center_y for block in blocks]
        y_array = np.array(y_positions).reshape(-1, 1)

        # Cluster by y-coordinate
        clustering = DBSCAN(eps=15, min_samples=1).fit(y_array)

        # Group by cluster
        rows_dict: dict[int, list[TextBlock]] = {}
        for block, label in zip(blocks, clustering.labels_):
            if label not in rows_dict:
                rows_dict[label] = []
            rows_dict[label].append(block)

        # Sort rows by y-coordinate (top to bottom)
        sorted_rows = sorted(rows_dict.values(), key=lambda row: row[0].y0, reverse=True)

        return sorted_rows


class HeaderFooterFilter:
    """Header and footer identification and filtering."""

    def identify_repeating_elements(
        self, pages_blocks: list[list[TextBlock]]
    ) -> list[str]:
        """Identify repeating text patterns across pages."""
        all_candidates: list[str] = []

        for page_blocks in pages_blocks:
            page_candidates = self._extract_top_bottom_candidates(page_blocks)
            all_candidates.extend(page_candidates)

        # Count repetitions
        counts = Counter(all_candidates)
        total_pages = len(pages_blocks)

        # Find patterns that appear in at least 80% of pages
        repeating = [
            pattern
            for pattern, count in counts.items()
            if count >= total_pages * 0.8
        ]

        return repeating

    def _extract_top_bottom_candidates(self, blocks: list[TextBlock]) -> list[str]:
        """Extract text from top and bottom regions of a page."""
        if not blocks:
            return []

        # Get page bounds
        y_positions = [block.y0 for block in blocks] + [block.y1 for block in blocks]
        min_y = min(y_positions)
        max_y = max(y_positions)
        page_height = max_y - min_y

        candidates: list[str] = []

        for block in blocks:
            # Check if in top 12% or bottom 12% of page
            if block.y1 < min_y + page_height * 0.12:  # Top region
                line = self._normalize_line(block.text)
                if 2 <= len(line) <= 120:
                    candidates.append(line)
            elif block.y0 > max_y - page_height * 0.12:  # Bottom region
                line = self._normalize_line(block.text)
                if 2 <= len(line) <= 120:
                    candidates.append(line)

        return candidates

    def _normalize_line(self, text: str) -> str:
        """Normalize text for pattern matching."""
        # Remove extra whitespace
        text = re.sub(r"\s+", " ", text.strip())
        # Replace page numbers
        text = re.sub(r"\bpage\s+\d+\b", "page #", text, flags=re.I)
        # Replace standalone numbers
        text = re.sub(r"^\d+$", "#", text)
        return text.lower()

    def filter_blocks(
        self, blocks: list[TextBlock], repeating_patterns: list[str]
    ) -> list[TextBlock]:
        """Filter out blocks that match repeating patterns."""
        if not repeating_patterns:
            return blocks

        filtered = []
        for block in blocks:
            normalized = self._normalize_line(block.text)
            if not self._matches_repeating_pattern(normalized, repeating_patterns):
                filtered.append(block)

        return filtered

    def _matches_repeating_pattern(
        self, normalized: str, patterns: list[str]
    ) -> bool:
        """Check if normalized text matches any repeating pattern."""
        for pattern in patterns:
            if normalized == pattern or normalized.startswith(pattern):
                return True
        return False


class ImageFilter:
    """Image region identification and text filtering."""

    def identify_image_regions(
        self, page_info: dict[str, Any], page_index: int = 0
    ) -> list[ImageRegion]:
        """Identify image regions in a page."""
        images = []

        # Check if page has image info
        image_list = page_info.get("images", [])
        if not image_list:
            # Try alternative image extraction method
            image_list = self._extract_images_from_page(page_info)

        for img_info in image_list:
            bbox = img_info.get("bbox")
            if bbox and len(bbox) == 4:
                x0, y0, x1, y1 = bbox
                area = max(0, x1 - x0) * max(0, y1 - y0)
                images.append(
                    ImageRegion(
                        x0=x0, y0=y0, x1=x1, y1=y1, area=area, page_index=page_index
                    )
                )

        return images

    def _extract_images_from_page(self, page_info: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract image information from page dict."""
        # This is a fallback method for different PDF library formats
        images = []
        # Implementation depends on the specific library being used
        return images

    def has_large_image(
        self, images: list[ImageRegion], page_area: float, threshold: float = 0.65
    ) -> bool:
        """Check if page has a large image."""
        for image in images:
            if page_area > 0 and image.area / page_area > threshold:
                return True
        return False

    def filter_image_overlapped_text(
        self, blocks: list[TextBlock], image_regions: list[ImageRegion]
    ) -> list[TextBlock]:
        """Filter text blocks that overlap with images."""
        if not image_regions:
            return blocks

        filtered = []
        for block in blocks:
            if not self._is_overlapped_with_images(block, image_regions):
                filtered.append(block)

        return filtered

    def _is_overlapped_with_images(
        self, block: TextBlock, image_regions: list[ImageRegion], threshold: float = 0.3
    ) -> bool:
        """Check if block overlaps with any image region."""
        for region in image_regions:
            if region.overlaps_with(block, threshold):
                return True
        return False
