"""HTML structure parser module."""

from __future__ import annotations

import re
from typing import Any

from ..domain import DocumentBlock


class HTMLStructureParser:
    """HTML structure parser that converts extracted text to DocumentBlock structure.

    This class is responsible for parsing text content extracted from HTML, identifying
    headings, paragraphs, lists, code blocks and other structures, and converting them
    to DocumentBlock objects for subsequent translation processing.
    """

    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
    LIST_RE = re.compile(r"^\s*[-*+]\s+")
    ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+")
    CODE_RE = re.compile(r"^```(\w*)\s*$", re.MULTILINE)

    def __init__(self, project_id: str):
        """Initialize HTML structure parser.

        Args:
            project_id: Project ID used to generate DocumentBlock IDs
        """
        self.project_id = project_id
        self.blocks: list[DocumentBlock] = []
        self.order = 0
        self.heading_stack: dict[int, str] = {}

    def parse(self, content: str, metadata: dict[str, Any] | None = None) -> list[DocumentBlock]:
        """Parse extracted text content into structured DocumentBlocks.

        Args:
            content: Text content extracted from HTML
            metadata: Optional metadata to attach to all DocumentBlocks

        Returns:
            List of DocumentBlocks
        """
        lines = content.splitlines()
        index = 0

        while index < len(lines):
            line = lines[index]

            # Skip empty lines
            if not line.strip():
                index += 1
                continue

            # Identify headings
            heading_match = self.HEADING_RE.match(line)
            if heading_match:
                marker, title = heading_match.groups()
                enhanced_metadata = self._enhance_metadata(metadata, {"markdown_marker": marker})
                self._add_heading(line, len(marker), enhanced_metadata)
                index += 1
                continue

            # 识别无序列表
            if self.LIST_RE.match(line):
                start = index
                index += 1
                while index < len(lines) and self.LIST_RE.match(lines[index]):
                    index += 1
                self._add_block("list", "\n".join(lines[start:index]), metadata)
                continue

            # 识别有序列表
            if self.ORDERED_LIST_RE.match(line):
                start = index
                index += 1
                while index < len(lines) and self.ORDERED_LIST_RE.match(lines[index]):
                    index += 1
                self._add_block("ordered_list", "\n".join(lines[start:index]), metadata)
                continue

            # 识别代码块
            if "```" in line and line.strip().startswith("```"):
                start = index
                language = None
                # 提取语言标识
                lang_match = re.match(r"^```(\w*)", line.strip())
                if lang_match:
                    language = lang_match.group(1) or None
                index += 1
                while index < len(lines) and "```" not in lines[index]:
                    index += 1
                if index < len(lines):
                    index += 1  # 包含结束的 ```
                self._add_code_block(
                    "\n".join(lines[start:index]),
                    language,
                    self._enhance_metadata(metadata, {"language": language})
                )
                continue

            # 处理段落
            start = index
            index += 1
            while index < len(lines):
                current = lines[index]
                if not current.strip() or self._starts_block(current):
                    break
                index += 1

            paragraph_text = "\n".join(lines[start:index])
            if paragraph_text.strip():  # 确保段落不为空
                self._add_block("paragraph", paragraph_text, metadata)

        return self.blocks

    def _add_heading(self, text: str, level: int, metadata: dict[str, Any] | None):
        """Add heading block."""
        block_id = f"{self.project_id}_h_{len(self.blocks) + 1:06d}"
        parent_id = self._get_parent_id(level)

        # Update heading stack
        self.heading_stack[level] = block_id
        # Clear deeper level headings
        for existing_level in list(self.heading_stack):
            if existing_level > level:
                del self.heading_stack[existing_level]

        self.blocks.append(
            DocumentBlock(
                id=block_id,
                project_id=self.project_id,
                parent_id=parent_id,
                block_order=self.order,
                block_type="heading",
                level=level,
                source_text=text,
                metadata=metadata or {},
            )
        )
        self.order += 1

    def _add_block(self, block_type: str, text: str, metadata: dict[str, Any] | None):
        """Add regular block."""
        block_id = f"{self.project_id}_p_{len(self.blocks) + 1:06d}"
        parent_id = self._get_latest_parent()

        self.blocks.append(
            DocumentBlock(
                id=block_id,
                project_id=self.project_id,
                parent_id=parent_id,
                block_order=self.order,
                block_type=block_type,
                level=None,
                source_text=text,
                metadata=metadata or {},
            )
        )
        self.order += 1

    def _add_code_block(self, text: str, language: str | None, metadata: dict[str, Any] | None):
        """Add code block."""
        block_id = f"{self.project_id}_c_{len(self.blocks) + 1:06d}"
        parent_id = self._get_latest_parent()

        self.blocks.append(
            DocumentBlock(
                id=block_id,
                project_id=self.project_id,
                parent_id=parent_id,
                block_order=self.order,
                block_type="code_block",
                level=None,
                source_text=text,
                metadata=metadata or {},
            )
        )
        self.order += 1

    def _starts_block(self, line: str) -> bool:
        """Determine if this is the start of a block."""
        return bool(
            self.HEADING_RE.match(line)
            or self.LIST_RE.match(line)
            or self.ORDERED_LIST_RE.match(line)
            or (line.strip().startswith("```") and "```" in line)
        )

    def _get_parent_id(self, level: int) -> str | None:
        """Get parent ID for specified level."""
        candidates = [
            (candidate_level, block_id)
            for candidate_level, block_id in self.heading_stack.items()
            if candidate_level < level
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    def _get_latest_parent(self) -> str | None:
        """Get latest parent ID."""
        if not self.heading_stack:
            return None
        nearest_level = max(self.heading_stack)
        return self.heading_stack[nearest_level]

    def _enhance_metadata(self, base_metadata: dict[str, Any] | None, additional: dict[str, Any]) -> dict[str, Any]:
        """Enhance metadata by merging base metadata and additional metadata."""
        result = (base_metadata or {}).copy()
        result.update(additional)
        return result