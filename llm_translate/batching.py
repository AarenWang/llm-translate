"""Chunk batching for efficient LLM translation.

This module implements intelligent chunk batching to combine small chunks
into larger batches for more efficient LLM API calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re


@dataclass
class ChunkBatch:
    """A batch of chunks to be translated together.

    Attributes:
        chunks: List of chunk IDs and their source texts
        total_chars: Total character count across all chunks
        separator: String used to join chunk translations
    """
    chunks: list[tuple[str, str]]  # (chunk_id, source_text)
    total_chars: int = 0
    separator: str = "\n\n"

    def __post_init__(self):
        self.total_chars = sum(len(text) for _, text in self.chunks)


@dataclass
class BatchTranslationResult:
    """Result from translating a batch of chunks.

    Attributes:
        chunk_translations: Dictionary mapping chunk_id to translated text
        success: Whether the batch translation succeeded
        error_message: Error message if translation failed
    """
    chunk_translations: dict[str, str]
    success: bool
    error_message: str | None = None


class ChunkBatcher:
    """Batches small chunks together for efficient translation.

    This class implements intelligent batching strategies:
    - Combines chunks smaller than a threshold
    - Respects token limits
    - Maintains chunk boundaries for proper result distribution
    """

    def __init__(
        self,
        min_chars_for_batch: int = 500,
        max_chars_per_batch: int = 3000,
        word_threshold: int = 100,
    ):
        """Initialize chunk batcher.

        Args:
            min_chars_for_batch: Minimum chars before considering batching
            max_chars_per_batch: Maximum chars per batch (token limit * 3)
            word_threshold: Words threshold (100 words ≈ 500 chars)
        """
        self.min_chars_for_batch = min_chars_for_batch
        self.max_chars_per_batch = max_chars_per_batch
        self.word_threshold = word_threshold

    def estimate_word_count(self, text: str) -> int:
        """Estimate word count for text (rough estimate works for mixed content).

        Args:
            text: Text to estimate word count for

        Returns:
            Estimated word count
        """
        # Simple word count: split by whitespace and count
        return len(re.findall(r'\S+', text))

    def should_batch(self, chunk_text: str) -> bool:
        """Determine if a chunk is small enough to be batched.

        Args:
            chunk_text: Chunk source text

        Returns:
            True if chunk should be batched with others
        """
        word_count = self.estimate_word_count(chunk_text)
        char_count = len(chunk_text)

        # Batch if below word threshold OR character threshold
        return word_count < self.word_threshold or char_count < self.min_chars_for_batch

    def create_batches(
        self,
        chunks: list[tuple[str, str]]
    ) -> list[ChunkBatch]:
        """Create batches from chunks, grouping small chunks together.

        Args:
            chunks: List of (chunk_id, source_text) tuples

        Returns:
            List of ChunkBatch objects
        """
        if not chunks:
            return []

        batches: list[ChunkBatch] = []
        current_batch: list[tuple[str, str]] = []
        current_batch_chars = 0

        for chunk_id, text in chunks:
            # Check if this chunk should be batched
            if not self.should_batch(text):
                # Large chunk: flush current batch and create single-item batch
                if current_batch:
                    batches.append(ChunkBatch(chunks=current_batch))
                    current_batch = []
                    current_batch_chars = 0

                batches.append(ChunkBatch(chunks=[(chunk_id, text)]))
                continue

            # Small chunk: try to add to current batch
            chunk_chars = len(text)

            # Check if adding would exceed max batch size
            if current_batch_chars + chunk_chars > self.max_chars_per_batch:
                # Flush current batch
                if current_batch:
                    batches.append(ChunkBatch(chunks=current_batch))
                    current_batch = []
                    current_batch_chars = 0

            # Add to current batch
            current_batch.append((chunk_id, text))
            current_batch_chars += chunk_chars

        # Flush remaining batch
        if current_batch:
            batches.append(ChunkBatch(chunks=current_batch))

        return batches

    def split_batch_result(
        self,
        batch: ChunkBatch,
        translated_text: str
    ) -> dict[str, str]:
        """Split batch translation result into individual chunk translations.

        Args:
            batch: The batch that was translated
            translated_text: The translated text (concatenated results)

        Returns:
            Dictionary mapping chunk_id to translated text
        """
        if len(batch.chunks) == 1:
            chunk_id, _ = batch.chunks[0]
            return {chunk_id: translated_text}

        # Split by separator and map to chunks
        separator = batch.separator
        translations = translated_text.split(separator)

        if len(translations) != len(batch.chunks):
            # Fallback: if split count doesn't match, try to distribute proportionally
            return self._distribute_by_proportion(batch, translated_text)

        return {chunk_id: trans.strip() for (chunk_id, _), trans in zip(batch.chunks, translations)}

    def _distribute_by_proportion(
        self,
        batch: ChunkBatch,
        translated_text: str
    ) -> dict[str, str]:
        """Distribute translated text proportionally when splitting fails.

        This is a fallback when the separator-based split doesn't work.
        It distributes text based on original chunk lengths.

        Args:
            batch: The batch that was translated
            translated_text: The translated text

        Returns:
            Dictionary mapping chunk_id to translated text
        """
        result = {}
        total_chars = sum(len(text) for _, text in batch.chunks)
        total_trans_chars = len(translated_text)

        current_pos = 0
        for chunk_id, original_text in batch.chunks:
            if total_chars > 0:
                # Proportional distribution
                proportion = len(original_text) / total_chars
                chunk_trans_chars = int(total_trans_chars * proportion)
            else:
                chunk_trans_chars = total_trans_chars // len(batch.chunks)

            # For the last chunk, take all remaining text
            if chunk_id == batch.chunks[-1][0]:
                chunk_text = translated_text[current_pos:]
            else:
                chunk_text = translated_text[current_pos:current_pos + chunk_trans_chars]
                current_pos += chunk_trans_chars

            result[chunk_id] = chunk_text.strip()

        return result

    def get_batch_stats(self, batches: list[ChunkBatch]) -> dict[str, Any]:
        """Calculate statistics about batching strategy.

        Args:
            batches: List of batches to analyze

        Returns:
            Dictionary with batch statistics
        """
        if not batches:
            return {
                "total_batches": 0,
                "total_chunks": 0,
                "avg_chunks_per_batch": 0,
                "avg_chars_per_batch": 0,
                "max_batch_size": 0,
                "min_batch_size": 0,
            }

        total_chunks = sum(len(batch.chunks) for batch in batches)
        total_chars = sum(batch.total_chars for batch in batches)
        batch_sizes = [len(batch.chunks) for batch in batches]

        return {
            "total_batches": len(batches),
            "total_chunks": total_chunks,
            "avg_chunks_per_batch": total_chunks / len(batches),
            "avg_chars_per_batch": total_chars / len(batches),
            "max_batch_size": max(batch_sizes),
            "min_batch_size": min(batch_sizes),
            "batch_size_distribution": {
                "single_chunk_batches": sum(1 for size in batch_sizes if size == 1),
                "multi_chunk_batches": sum(1 for size in batch_sizes if size > 1),
            }
        }