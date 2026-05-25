from __future__ import annotations

import re
from typing import Any

from ..domain import DocumentBlock


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


class IpynbParser:
    """Parse Notebook cells while preserving enough metadata for JSON round-trip."""

    def parse(self, project_id: str, notebook: dict[str, Any]) -> list[DocumentBlock]:
        blocks: list[DocumentBlock] = []
        heading_stack: dict[int, str] = {}

        for cell_index, cell in enumerate(notebook.get("cells", [])):
            block_order = len(blocks)
            cell_type = cell.get("cell_type", "raw")
            source = cell.get("source", "")
            source_text, source_kind = normalize_source(source)
            block_id = f"{project_id}_b_{block_order + 1:06d}"
            heading_level, heading_text = self._first_heading(source_text)
            block_type = f"notebook_{cell_type}_cell"
            if cell_type not in {"markdown", "code", "raw"}:
                block_type = "notebook_raw_cell"

            parent_id = self._parent_id(heading_level, heading_stack)
            if cell_type == "markdown" and heading_level is not None:
                for existing_level in list(heading_stack):
                    if existing_level >= heading_level:
                        del heading_stack[existing_level]
                parent_id = self._parent_id(heading_level, heading_stack)
                heading_stack[heading_level] = block_id
            elif heading_stack:
                parent_id = heading_stack[max(heading_stack)]

            blocks.append(
                DocumentBlock(
                    id=block_id,
                    project_id=project_id,
                    parent_id=parent_id,
                    block_order=block_order,
                    block_type=block_type,
                    level=heading_level,
                    source_text=source_text,
                    metadata={
                        "format": "ipynb",
                        "cell_index": cell_index,
                        "cell_id": cell.get("id"),
                        "cell_type": cell_type,
                        "source_kind": source_kind,
                        "source_line_count": len(source_text.splitlines()),
                        "attachments_present": bool(cell.get("attachments")),
                        "heading_level": heading_level,
                        "heading_text": heading_text,
                        "translatable": cell_type == "markdown" and bool(source_text.strip()),
                    },
                )
            )

        return blocks

    def _first_heading(self, source_text: str) -> tuple[int | None, str | None]:
        match = HEADING_RE.search(source_text)
        if not match:
            return None, None
        return len(match.group(1)), match.group(2)

    def _parent_id(self, level: int | None, heading_stack: dict[int, str]) -> str | None:
        if not heading_stack:
            return None
        if level is None:
            return heading_stack[max(heading_stack)]
        candidates = [
            (heading_level, block_id)
            for heading_level, block_id in heading_stack.items()
            if heading_level < level
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]


def normalize_source(source: str | list[str]) -> tuple[str, str]:
    if isinstance(source, list):
        return "".join(source), "list"
    return str(source), "string"


def source_from_text(text: str, source_kind: str) -> str | list[str]:
    if source_kind == "string":
        return text
    if not text:
        return []
    return text.splitlines(keepends=True)
