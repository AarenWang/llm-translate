"""HTML core content extractor module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtractedContent:
    """Extracted web page core content.

    Attributes:
        title: Web page title
        author: Author information
        date: Publication date
        text: Extracted main text content
        raw_html: Original HTML content
        metadata: Additional metadata
    """

    title: str | None
    author: str | None
    date: str | None
    text: str
    raw_html: str
    metadata: dict[str, Any]


class HTMLContentExtractor:
    """HTML core content extractor using Trafilatura to extract web page main content.

    This class wraps the Trafilatura library to provide core content extraction from HTML.
    """

    def __init__(
        self,
        include_comments: bool = False,
        include_tables: bool = True,
        favor_precision: bool = True,
    ):
        """Initialize HTML content extractor.

        Args:
            include_comments: Whether to include comment content
            include_tables: Whether to include table content
            favor_precision: Whether to prioritize precision (extract less but more accurately)
        """
        self.include_comments = include_comments
        self.include_tables = include_tables
        self.favor_precision = favor_precision

    def extract(self, html: str, url: str | None = None) -> ExtractedContent:
        """Extract core content from HTML.

        Args:
            html: HTML content string
            url: Optional original URL for relative link resolution

        Returns:
            ExtractedContent object containing extracted core content
        """
        try:
            import trafilatura
        except ImportError:
            raise ImportError(
                "trafilatura library is required for HTML content extraction. "
                "Install it with: pip install trafilatura"
            )

        # Use trafilatura for structured extraction
        result = trafilatura.bare_extraction(
            html,
            url=url,
            include_comments=self.include_comments,
            include_tables=self.include_tables,
            favor_precision=self.favor_precision,
            no_fallback=False,  # Allow fallback extraction methods
        )

        # Check extraction results
        # trafilatura.bare_extraction returns a Document object
        if not result or not result.text:
            # If structured extraction fails, use basic text extraction as fallback
            text = trafilatura.extract(
                html,
                include_comments=self.include_comments,
                include_tables=self.include_tables,
                favor_precision=self.favor_precision,
            )

            return ExtractedContent(
                title=None,
                author=None,
                date=None,
                text=text or "",
                raw_html=html,
                metadata={"extraction_method": "fallback"},
            )

        # Extraction successful, build result object
        # Access Document object attributes
        return ExtractedContent(
            title=result.title,
            author=result.author,
            date=result.date,
            text=result.text or "",
            raw_html=html,
            metadata={
                "language": result.language,
                "url": result.url,
                "hostname": result.hostname,
                "description": result.description,
                "categories": result.categories,
                "tags": result.tags,
                "extraction_method": "structured",
            },
        )