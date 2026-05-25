from __future__ import annotations

import re

from ..domain import DocumentBlock


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+")
UNORDERED_LIST_RE = re.compile(r"^\s*[-*+]\s+")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


class MarkdownParser:
    """Conservative block parser for the V1 Markdown MVP."""

    def parse(self, project_id: str, markdown: str) -> list[DocumentBlock]:
        lines = markdown.splitlines()
        blocks: list[DocumentBlock] = []
        order = 0
        index = 0
        heading_stack: dict[int, str] = {}

        def add_block(
            block_type: str,
            text: str,
            level: int | None = None,
            metadata: dict | None = None,
        ) -> None:
            nonlocal order
            block_id = f"{project_id}_b_{order + 1:06d}"
            parent_id = self._parent_id(level, block_type, heading_stack)
            if block_type == "heading" and level is not None:
                heading_stack[level] = block_id
                for existing_level in list(heading_stack):
                    if existing_level > level:
                        del heading_stack[existing_level]
                parent_id = self._heading_parent(level, heading_stack, block_id)
            blocks.append(
                DocumentBlock(
                    id=block_id,
                    project_id=project_id,
                    parent_id=parent_id,
                    block_order=order,
                    block_type=block_type,
                    level=level,
                    source_text=text.strip("\n"),
                    metadata=metadata or {},
                )
            )
            order += 1

        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue

            if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
                fence = line.lstrip()[:3]
                start = index
                index += 1
                while index < len(lines):
                    if lines[index].lstrip().startswith(fence):
                        index += 1
                        break
                    index += 1
                text = "\n".join(lines[start:index])
                language = line.lstrip()[3:].strip() or None
                add_block("code_block", text, metadata={"language": language})
                continue

            heading = HEADING_RE.match(line)
            if heading:
                marker, title = heading.groups()
                chapter_number, chapter_title = self._split_heading_number(title)
                add_block(
                    "heading",
                    line,
                    level=len(marker),
                    metadata={
                        "markdown_marker": marker,
                        "chapter_number": chapter_number,
                        "chapter_title": chapter_title,
                    },
                )
                index += 1
                continue

            if self._is_table_start(lines, index):
                start = index
                index += 2
                while index < len(lines) and "|" in lines[index] and lines[index].strip():
                    index += 1
                table_lines = lines[start:index]
                add_block(
                    "table",
                    "\n".join(table_lines),
                    metadata={
                        "columns": self._table_columns(table_lines[0]),
                        "rows": len(table_lines),
                    },
                )
                continue

            if UNORDERED_LIST_RE.match(line) or ORDERED_LIST_RE.match(line):
                start = index
                index += 1
                while index < len(lines):
                    current = lines[index]
                    if not current.strip():
                        break
                    if (
                        UNORDERED_LIST_RE.match(current)
                        or ORDERED_LIST_RE.match(current)
                        or current.startswith("  ")
                        or current.startswith("\t")
                    ):
                        index += 1
                        continue
                    break
                add_block("list", "\n".join(lines[start:index]))
                continue

            if line.lstrip().startswith(">"):
                start = index
                index += 1
                while index < len(lines) and lines[index].lstrip().startswith(">"):
                    index += 1
                add_block("quote", "\n".join(lines[start:index]))
                continue

            start = index
            index += 1
            while index < len(lines):
                current = lines[index]
                if not current.strip() or self._starts_block(lines, index):
                    break
                index += 1
            add_block("paragraph", "\n".join(lines[start:index]))

        return blocks

    def _starts_block(self, lines: list[str], index: int) -> bool:
        line = lines[index]
        return (
            bool(HEADING_RE.match(line))
            or line.lstrip().startswith(("```", "~~~", ">"))
            or bool(UNORDERED_LIST_RE.match(line))
            or bool(ORDERED_LIST_RE.match(line))
            or self._is_table_start(lines, index)
        )

    def _is_table_start(self, lines: list[str], index: int) -> bool:
        return (
            index + 1 < len(lines)
            and "|" in lines[index]
            and bool(TABLE_SEPARATOR_RE.match(lines[index + 1]))
        )

    def _table_columns(self, header: str) -> int:
        return len([cell for cell in header.strip().strip("|").split("|")])

    def _parent_id(
        self,
        level: int | None,
        block_type: str,
        heading_stack: dict[int, str],
    ) -> str | None:
        if block_type == "heading" and level is not None:
            return self._heading_parent(level, heading_stack, None)
        if not heading_stack:
            return None
        nearest_level = max(heading_stack)
        return heading_stack[nearest_level]

    def _heading_parent(
        self,
        level: int,
        heading_stack: dict[int, str],
        current_id: str | None,
    ) -> str | None:
        candidates = [
            (candidate_level, block_id)
            for candidate_level, block_id in heading_stack.items()
            if candidate_level < level and block_id != current_id
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    def _split_heading_number(self, title: str) -> tuple[str | None, str]:
        patterns = [
            r"^(Chapter\s+\d+(?:\.\d+)*\.?)\s+(.+)$",
            r"^(\d+(?:\.\d+)*\.?)\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, title, re.IGNORECASE)
            if match:
                return match.group(1), match.group(2)
        return None, title
