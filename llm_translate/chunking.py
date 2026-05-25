from __future__ import annotations

from .domain import DocumentBlock, TranslationChunk


class TokenEstimator:
    def estimate(self, text: str) -> int:
        return max(1, len(text) // 4)


class ChunkingEngine:
    def __init__(self, soft_input_tokens: int = 2200, max_input_tokens: int = 3000):
        self.soft_input_tokens = soft_input_tokens
        self.max_input_tokens = max_input_tokens
        self.estimator = TokenEstimator()

    def build_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        if blocks and blocks[0].metadata.get("format") == "ipynb":
            return self._build_ipynb_chunks(project_id, blocks)
        if blocks and blocks[0].metadata.get("format") == "docx":
            return self._build_docx_chunks(project_id, blocks)

        chunks: list[TranslationChunk] = []
        pending: list[DocumentBlock] = []
        pending_tokens = 0
        current_chapter_id: str | None = None

        def flush() -> None:
            nonlocal pending, pending_tokens
            if not pending:
                return
            chunk_order = len(chunks)
            chunks.append(
                TranslationChunk(
                    id=f"{project_id}_c_{chunk_order + 1:06d}",
                    project_id=project_id,
                    chapter_id=current_chapter_id,
                    chunk_order=chunk_order,
                    block_ids=[block.id for block in pending],
                    source_text="\n\n".join(block.source_text for block in pending),
                )
            )
            pending = []
            pending_tokens = 0

        for block in blocks:
            if block.block_type == "heading" and (block.level or 99) <= 2:
                flush()
                current_chapter_id = block.id

            block_tokens = self.estimator.estimate(block.source_text)
            if pending and pending_tokens + block_tokens > self.soft_input_tokens:
                flush()

            pending.append(block)
            pending_tokens += block_tokens

            if pending_tokens >= self.max_input_tokens:
                flush()

        flush()
        return chunks

    def _build_ipynb_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        chunks: list[TranslationChunk] = []
        current_chapter_id: str | None = None
        for block in blocks:
            if block.block_type == "notebook_markdown_cell" and block.level is not None:
                current_chapter_id = block.id
            if not block.metadata.get("translatable"):
                continue
            parts = self._split_ipynb_markdown_cell(block.source_text)
            for part_index, part in enumerate(parts):
                chunk_order = len(chunks)
                chunks.append(
                    TranslationChunk(
                        id=f"{project_id}_c_{chunk_order + 1:06d}",
                        project_id=project_id,
                        chapter_id=current_chapter_id,
                        chunk_order=chunk_order,
                        block_ids=[block.id],
                        source_text=part,
                        metadata={
                            "format": "ipynb",
                            "cell_index": block.metadata.get("cell_index"),
                            "cell_id": block.metadata.get("cell_id"),
                            "block_id": block.id,
                            "chunk_part": part_index,
                            "part_count": len(parts),
                        },
                    )
                )
        return chunks

    def _build_docx_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        """Build chunks for DOCX format.

        Groups paragraphs by context while respecting token limits.
        Headings (H1-H2) serve as natural chapter boundaries.

        Args:
            project_id: Translation project identifier
            blocks: List of document blocks

        Returns:
            List of TranslationChunk objects
        """
        chunks: list[TranslationChunk] = []
        pending: list[DocumentBlock] = []
        pending_tokens = 0
        current_chapter_id: str | None = None

        def flush() -> None:
            nonlocal pending, pending_tokens
            if not pending:
                return
            chunk_order = len(chunks)

            # Build chunk with metadata
            chunk = TranslationChunk(
                id=f"{project_id}_c_{chunk_order + 1:06d}",
                project_id=project_id,
                chapter_id=current_chapter_id,
                chunk_order=chunk_order,
                block_ids=[block.id for block in pending],
                source_text="\n\n".join(block.source_text for block in pending),
                metadata={
                    "format": "docx",
                    "chapter_id": current_chapter_id,
                    "block_count": len(pending),
                    "estimated_tokens": pending_tokens,
                }
            )
            chunks.append(chunk)
            pending = []
            pending_tokens = 0

        for block in blocks:
            if not block.metadata.get("translatable", True):
                continue

            # Start new chunk at major headings
            is_major_heading = (
                block.block_type.startswith("docx_heading") and
                block.metadata.get("heading_level", 99) <= 2
            )
            if is_major_heading:
                flush()
                current_chapter_id = block.id

            block_tokens = self.estimator.estimate(block.source_text)

            # Check if adding this block would exceed soft limit
            if pending and pending_tokens + block_tokens > self.soft_input_tokens:
                flush()

            pending.append(block)
            pending_tokens += block_tokens

            # Force chunk if exceeding hard limit
            if pending_tokens >= self.max_input_tokens:
                flush()

        flush()
        return chunks

    def _split_ipynb_markdown_cell(self, text: str) -> list[str]:
        if self.estimator.estimate(text) <= self.max_input_tokens:
            return [text]

        units = text.split("\n\n")
        parts: list[str] = []
        pending: list[str] = []
        pending_tokens = 0

        def flush() -> None:
            nonlocal pending, pending_tokens
            if pending:
                parts.append("\n\n".join(pending))
                pending = []
                pending_tokens = 0

        for unit in units:
            unit_tokens = self.estimator.estimate(unit)
            if unit_tokens > self.max_input_tokens:
                flush()
                parts.extend(self._split_large_text_unit(unit))
                continue
            if pending and pending_tokens + unit_tokens > self.soft_input_tokens:
                flush()
            pending.append(unit)
            pending_tokens += unit_tokens

        flush()
        return [part for part in parts if part.strip()] or [text]

    def _split_large_text_unit(self, text: str) -> list[str]:
        lines = text.splitlines(keepends=True)
        parts: list[str] = []
        pending: list[str] = []
        pending_tokens = 0

        for line in lines:
            line_tokens = self.estimator.estimate(line)
            if pending and pending_tokens + line_tokens > self.soft_input_tokens:
                parts.append("".join(pending))
                pending = []
                pending_tokens = 0
            pending.append(line)
            pending_tokens += line_tokens

        if pending:
            parts.append("".join(pending))
        return parts
