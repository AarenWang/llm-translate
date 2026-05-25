# SRT Subtitle Adapter Design

## Goals

Add `.srt` translation support through the existing `FormatAdapter` protocol.

The adapter should:

- Translate cue text only.
- Preserve cue numbers, timing lines, blank-line separation, and cue order.
- Export a translated `.srt` plus the standard Markdown review artifacts.

## Parsing Model

The parser treats each subtitle cue as one `DocumentBlock`.

For each block:

- Numeric sequence lines are metadata, not translated.
- Timing lines matching `00:00:00,000 --> 00:00:00,000` are metadata, not translated.
- One or more following text lines are the translatable span.

Each cue block records:

- `metadata.format = "srt"`
- `metadata.cue_index`
- `metadata.start_offset` / `metadata.end_offset`
- `metadata.timing`
- `metadata.marker`

## Chunking

Cue text is chunked with stable markers:

```text
__LT_SUBTITLE_CUE_000001__
Hello there.

__LT_SUBTITLE_CUE_000002__
Welcome back.
```

The marker lets export recover each cue translation even when a chunk contains many short subtitle cues.

## Export

Export replaces only cue text spans in the original file. It does not regenerate numbering or timing data.

Validation checks:

- Cue count is unchanged.
- Timing lines are unchanged.
- The exported file is non-empty and parseable by the same adapter.

