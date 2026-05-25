"""HTML document parser."""

from __future__ import annotations

from ..domain import DocumentBlock
from ..html_utils.fetcher import LocalHTMLFetcher
from ..html_utils.extractor import HTMLContentExtractor
from ..html_utils.structure import HTMLStructureParser


class HTMLParser:
    """HTML document parser integrating content fetching, extraction, and structure parsing.

    This class provides a complete HTML document parsing pipeline:
    1. Read HTML content from local file system
    2. Extract core main content using Trafilatura
    3. Parse document structure and convert to DocumentBlocks
    """

    def __init__(
        self,
        include_comments: bool = False,
        include_tables: bool = True,
        favor_precision: bool = True,
    ):
        """Initialize HTML parser.

        Args:
            include_comments: Whether to include comment content
            include_tables: Whether to include table content
            favor_precision: Whether to prioritize precision
        """
        self.fetcher = LocalHTMLFetcher()
        self.extractor = HTMLContentExtractor(
            include_comments=include_comments,
            include_tables=include_tables,
            favor_precision=favor_precision,
        )

    def parse(self, project_id: str, html_path: str) -> list[DocumentBlock]:
        """Parse HTML file.

        Args:
            project_id: Project ID
            html_path: HTML file path

        Returns:
            List of DocumentBlocks

        Raises:
            FileNotFoundError: When HTML file doesn't exist
            ValueError: When HTML content is empty or extraction fails
        """
        # 1. Get HTML content
        html_content = self.fetcher.fetch(html_path)

        if not html_content or not html_content.strip():
            raise ValueError(f"HTML content is empty: {html_path}")

        # 2. Extract core content
        extracted = self.extractor.extract(html_content)

        if not extracted.text or not extracted.text.strip():
            raise ValueError(f"Failed to extract content from HTML: {html_path}")

        # 3. Parse document structure
        structure_parser = HTMLStructureParser(project_id)
        blocks = structure_parser.parse(
            extracted.text,
            metadata={
                "title": extracted.title,
                "author": extracted.author,
                "date": extracted.date,
                "source": html_path,
                **extracted.metadata,
            },
        )

        return blocks