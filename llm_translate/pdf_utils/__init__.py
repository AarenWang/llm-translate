"""PDF utility modules for document processing."""

from __future__ import annotations

from .layout import (
    HeaderFooterFilter,
    ImageFilter,
    MultiColumnResolver,
    TextBlock,
    ImageRegion,
)
from .tables import TableDetector, TableRegion, Table
from .filters import ContentFilter, RepeatingPatternFilter
from .cross_page import CrossPageMerger, PageContent, ContentBlock
from .quality import TextQualityChecker, CidResolver

__all__ = [
    # Layout
    "HeaderFooterFilter",
    "ImageFilter",
    "MultiColumnResolver",
    "TextBlock",
    "ImageRegion",
    # Tables
    "TableDetector",
    "TableRegion",
    "Table",
    # Filters
    "ContentFilter",
    "RepeatingPatternFilter",
    # Cross-page
    "CrossPageMerger",
    "PageContent",
    "ContentBlock",
    # Quality
    "TextQualityChecker",
    "CidResolver",
]
