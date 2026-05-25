from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import warnings
import zipfile

from bs4 import BeautifulSoup, NavigableString, XMLParsedAsHTMLWarning
from ebooklib import ITEM_DOCUMENT
from ebooklib import epub

from ..domain import DocumentBlock


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
    "code",
    "kbd",
    "math",
    "pre",
    "samp",
    "script",
    "style",
    "svg",
})


@dataclass(frozen=True)
class EpubDocument:
    item_id: str
    href: str
    file_name: str
    media_type: str | None
    spine_index: int


@dataclass(frozen=True)
class EpubParseResult:
    blocks: list[DocumentBlock]
    documents: list[EpubDocument]
    spine: list[dict[str, Any]]
    manifest_count: int

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "documents": [asdict(document) for document in self.documents],
            "spine": self.spine,
            "manifest_count": self.manifest_count,
        }


class EpubParser:
    """Extract translatable text nodes from EPUB spine XHTML documents.

    This parser processes EPUB files and extracts text nodes that should be
    translated while preserving structure and protecting non-translatable content
    like code blocks, scripts, and styles.

    The parser maintains metadata about each text node including its position,
    parent element type, and whitespace prefix/suffix to enable accurate
    reconstruction of translated EPUB files.
    """

    @staticmethod
    def parse_html_safely(raw: bytes) -> BeautifulSoup:
        """Parse HTML content safely, suppressing XML parsing warnings.

        Args:
            raw: Raw HTML bytes content

        Returns:
            BeautifulSoup object parsed with html5lib
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            return BeautifulSoup(raw.decode("utf-8", errors="replace"), "html5lib")

    def parse(self, project_id: str, epub_path: Path) -> EpubParseResult:
        """Parse an EPUB file and extract translatable text nodes from spine documents.

        Args:
            project_id: Unique identifier for the translation project
            epub_path: Path to the EPUB file to parse

        Returns:
            EpubParseResult containing extracted blocks, document metadata,
            and spine information

        Raises:
            zipfile.BadZipFile: If the EPUB file is corrupted or invalid
            UnicodeDecodeError: If text encoding cannot be resolved
        """
        book = epub.read_epub(str(epub_path))
        manifest = {item.get_id(): item for item in book.get_items()}
        archive_names = self._archive_names(epub_path)
        documents: list[EpubDocument] = []
        blocks: list[DocumentBlock] = []
        spine_snapshot: list[dict[str, Any]] = []

        for spine_index, spine_entry in enumerate(book.spine):
            item_id = spine_entry[0]
            linear = spine_entry[1] if len(spine_entry) > 1 else None
            spine_snapshot.append({"id": item_id, "linear": linear})
            item = manifest.get(item_id)
            # Handle both ITEM_DOCUMENT (type 9) and type 0 (some EPUBs use this)
            if item is None or (item.get_type() != ITEM_DOCUMENT and item.get_type() != 0):
                continue

            href = item.get_name()
            document = EpubDocument(
                item_id=item_id,
                href=href,
                file_name=self._archive_file_name(href, archive_names),
                media_type=getattr(item, "media_type", None),
                spine_index=spine_index,
            )
            documents.append(document)
            html = item.get_content()
            soup = self.parse_html_safely(html)

            for text_index, text_node in enumerate(self._iter_translatable_text_nodes(soup)):
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
                        block_type=f"epub_{tag_name}_text",
                        level=self._heading_level(tag_name),
                        source_text=stripped,
                        metadata={
                            "format": "epub",
                            "item_id": document.item_id,
                            "href": document.href,
                            "file_name": document.file_name,
                            "spine_index": document.spine_index,
                            "text_node_index": text_index,
                            "tag": tag_name,
                            "prefix": prefix,
                            "suffix": suffix,
                            "translatable": True,
                        },
                    )
                )

        return EpubParseResult(
            blocks=blocks,
            documents=documents,
            spine=spine_snapshot,
            manifest_count=len(manifest),
        )

    def _iter_translatable_text_nodes(self, soup: BeautifulSoup) -> list[NavigableString]:
        """Extract translatable text nodes using parent type caching for better performance.

        This method caches parent node types to avoid traversing the parent chain
        for each text node, reducing time complexity from O(n×d) to O(n+d).
        """
        nodes: list[NavigableString] = []
        body = soup.body or soup

        # Pre-compute ancestor types for all elements
        ancestor_cache: dict[Any, set[str]] = {}
        for element in body.find_all(True):
            # Include the element itself and all its ancestors
            ancestor_types = {element.name.lower()}
            ancestor_types.update(
                parent.name.lower()
                for parent in element.parents
                if getattr(parent, "name", None)
            )
            ancestor_cache[element] = ancestor_types

        for node in body.find_all(string=True):
            if not isinstance(node, NavigableString):
                continue
            if not str(node).strip():
                continue

            ancestor_types = ancestor_cache.get(node.parent, set())
            if ancestor_types & SKIP_ANCESTORS:
                continue
            if ancestor_types & TRANSLATABLE_ANCESTORS:
                nodes.append(node)
        return nodes

    def _heading_level(self, tag_name: str) -> int | None:
        """Extract heading level from tag name (e.g., 'h1' -> 1, 'p' -> None)."""
        if len(tag_name) == 2 and tag_name.startswith("h") and tag_name[1].isdigit():
            return int(tag_name[1])
        return None

    def _archive_names(self, epub_path: Path) -> set[str]:
        """Extract all file names from the EPUB archive."""
        with zipfile.ZipFile(epub_path, "r") as archive:
            return set(archive.namelist())

    def _archive_file_name(self, href: str, archive_names: set[str]) -> str:
        """Resolve archive file name from href, handling directory prefixes."""
        if href in archive_names:
            return href
        matches = [name for name in archive_names if name.endswith(f"/{href}")]
        if len(matches) == 1:
            return matches[0]
        return href
        if len(tag_name) == 2 and tag_name.startswith("h") and tag_name[1].isdigit():
            return int(tag_name[1])
        return None

    def _archive_names(self, epub_path: Path) -> set[str]:
        with zipfile.ZipFile(epub_path, "r") as archive:
            return set(archive.namelist())

    def _archive_file_name(self, href: str, archive_names: set[str]) -> str:
        if href in archive_names:
            return href
        matches = [name for name in archive_names if name.endswith(f"/{href}")]
        if len(matches) == 1:
            return matches[0]
        return href
