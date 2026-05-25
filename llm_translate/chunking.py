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
