#!/usr/bin/env python3
"""Example script demonstrating chunk batching functionality.

This script shows how to use the new chunk batching feature to translate
small chunks more efficiently by combining them into larger batches.
"""

from llm_translate.batching import ChunkBatcher

def example_batching():
    """Demonstrate chunk batching with sample data."""
    print("Chunk Batching Example")
    print("=" * 50)

    # Create a batcher with custom thresholds
    batcher = ChunkBatcher(
        min_chars_for_batch=500,  # Minimum chars before considering batching
        max_chars_per_batch=3000,  # Maximum chars per batch (token limit * 3)
        word_threshold=100,        # Words threshold (100 words ≈ 500 chars)
    )

    # Simulate chunks from a document like The Economist
    sample_chunks = [
        ('economist_01', 'May 23rd 2026'),
        ('economist_02', 'The world this week'),
        ('economist_03', 'Leaders'),
        ('economist_04', 'Letters'),
        ('economist_05', 'United States'),
        ('economist_06', 'The Americas'),
        ('economist_07', 'Asia'),
        ('economist_08', 'China'),
        ('economist_09', 'Middle East & Africa'),
        ('economist_10', 'Europe'),
        ('economist_11', 'Britain'),
        ('economist_12', 'International'),
        ('economist_13', 'Business'),
        ('economist_14', 'Finance & economics'),
        ('economist_15', 'Science & technology'),
        ('economist_16', 'Culture'),
        ('economist_17', 'Economic indicators'),
        ('economist_18', 'Obituary'),
    ]

    print(f"Original chunks: {len(sample_chunks)}")
    print(f"Total characters: {sum(len(text) for _, text in sample_chunks)}")
    print()

    # Create batches
    batches = batcher.create_batches(sample_chunks)

    print(f"Created {len(batches)} batches")
    print()

    # Show batch details
    for i, batch in enumerate(batches, 1):
        chunk_names = [chunk_id.split('_')[1] for chunk_id, _ in batch.chunks]
        print(f"Batch {i}:")
        print(f"  Chunks: {len(batch.chunks)} ({', '.join(chunk_names)})")
        print(f"  Total chars: {batch.total_chars}")
        print()

    # Show statistics
    stats = batcher.get_batch_stats(batches)
    print("Batching Statistics:")
    print(f"  API calls reduced from {stats['total_chunks']} to {stats['total_batches']}")
    print(f"  Reduction: {stats['total_chunks'] - stats['total_batches']} calls ({(1 - stats['total_batches']/stats['total_chunks'])*100:.1f}%)")
    print(f"  Average chunks per batch: {stats['avg_chunks_per_batch']:.1f}")
    print(f"  Single-chunk batches: {stats['batch_size_distribution']['single_chunk_batches']}")
    print(f"  Multi-chunk batches: {stats['batch_size_distribution']['multi_chunk_batches']}")

    print()
    print("Key Benefits:")
    print(f"  * Fewer API calls: {stats['total_chunks']} -> {stats['total_batches']}")
    print(f"  * Faster translation: Less overhead per API call")
    print(f"  * Better token usage: More efficient batching")
    print(f"  * Cost reduction: Less API overhead charges")

if __name__ == "__main__":
    example_batching()