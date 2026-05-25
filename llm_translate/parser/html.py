"""HTML document parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import warnings

from bs4 import BeautifulSoup, NavigableString, XMLParsedAsHTMLWarning

from ..domain import DocumentBlock
from ..html_utils.fetcher import LocalHTMLFetcher
from ..html_utils.extractor import HTMLContentExtractor
from ..html_utils.structure import HTMLStructureParser

TRANSLATABLE_ANCESTORS = frozenset({
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "blockquote",
    "td",
    "th",
    "figcaption",
})

SKIP_ANCESTORS = frozenset({
    "aside",
    "button",
    "code",
    "footer",
    "header",
    "math",
    "nav",
    "noscript",
    "pre",
    "script",
    "style",
    "svg",
})


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

    @staticmethod
    def parse_html_safely(raw: bytes | str) -> BeautifulSoup:
        """Parse HTML with html5lib while suppressing XML/HTML warning noise."""
        if isinstance(raw, bytes):
            html = raw.decode("utf-8", errors="replace")
        else:
            html = raw
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            return BeautifulSoup(html, "html5lib")

    def parse(self, project_id: str, html_path: str) -> list[DocumentBlock]:
        """Parse HTML file into DOM text-node blocks for structural writeback.

        Args:
            project_id: Project ID
            html_path: HTML file path

        Returns:
            List of DocumentBlocks

        Raises:
            FileNotFoundError: When HTML file doesn't exist
            ValueError: When HTML content is empty or extraction fails
        """
        html_content = self.fetcher.fetch(html_path)

        if not html_content or not html_content.strip():
            raise ValueError(f"HTML content is empty: {html_path}")

        blocks = self.parse_dom_text_nodes(project_id, html_content, source=html_path)
        if blocks:
            return blocks

        # Keep the legacy extraction path as a last-resort fallback for unusual
        # HTML where no whitelisted DOM text nodes can be identified.
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

    def parse_dom_text_nodes(
        self,
        project_id: str,
        html_content: str,
        source: str | Path | None = None,
    ) -> list[DocumentBlock]:
        """Extract translatable DOM text nodes while preserving node positions."""
        soup = self.parse_html_safely(html_content)
        nodes = self._iter_translatable_text_nodes(soup)
        blocks: list[DocumentBlock] = []

        for text_index, text_node in enumerate(nodes):
            raw_text = str(text_node)
            stripped = raw_text.strip()
            if not stripped:
                continue
            parent = text_node.parent
            tag_name = parent.name.lower() if parent and parent.name else "text"
            prefix = raw_text[: len(raw_text) - len(raw_text.lstrip())]
            suffix = raw_text[len(raw_text.rstrip()) :]
            block_order = len(blocks)
            blocks.append(
                DocumentBlock(
                    id=f"{project_id}_b_{block_order + 1:06d}",
                    project_id=project_id,
                    parent_id=None,
                    block_order=block_order,
                    block_type=f"html_{tag_name}_text",
                    level=self._heading_level(tag_name),
                    source_text=stripped,
                    metadata={
                        "format": "html",
                        "source": str(source) if source is not None else None,
                        "text_node_index": text_index,
                        "tag": tag_name,
                        "prefix": prefix,
                        "suffix": suffix,
                        "translatable": True,
                    },
                )
            )

        return blocks

    def _iter_translatable_text_nodes(self, soup: BeautifulSoup) -> list[NavigableString]:
        """Return visible natural-language text nodes eligible for P0 writeback."""
        nodes: list[NavigableString] = []
        root = self._content_root(soup)
        ancestor_cache: dict[Any, set[str]] = {}

        for element in root.find_all(True):
            ancestor_types = {element.name.lower()}
            ancestor_types.update(
                parent.name.lower()
                for parent in element.parents
                if getattr(parent, "name", None)
            )
            ancestor_cache[element] = ancestor_types

        for node in root.find_all(string=True):
            if not isinstance(node, NavigableString):
                continue
            if not self._has_translatable_text(str(node)):
                continue

            ancestor_types = ancestor_cache.get(node.parent, set())
            if ancestor_types & SKIP_ANCESTORS:
                continue
            if ancestor_types & TRANSLATABLE_ANCESTORS:
                nodes.append(node)
        return nodes

    def _content_root(self, soup: BeautifulSoup):
        # P0 stays local and deterministic: prefer semantic content containers
        # when present, otherwise translate whitelisted body text nodes.
        return soup.find("main") or soup.find("article") or soup.body or soup

    def _heading_level(self, tag_name: str) -> int | None:
        if len(tag_name) == 2 and tag_name.startswith("h") and tag_name[1].isdigit():
            return int(tag_name[1])
        return None

    def _has_translatable_text(self, text: str) -> bool:
        stripped = text.strip()
        return bool(stripped) and any(char.isalpha() for char in stripped)
