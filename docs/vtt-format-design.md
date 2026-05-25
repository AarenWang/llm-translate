# WebVTT Subtitle Adapter Design

## Goals

Add `.vtt` / WebVTT translation support through the same subtitle adapter foundation used for SRT.

The adapter should:

- Preserve the `WEBVTT` header and header metadata.
- Preserve cue ids, timing lines, `NOTE`, `STYLE`, and `REGION` blocks.
- Translate cue payload text only.
- Export a translated `.vtt` plus the standard Markdown review artifacts.

## Parsing Model

WebVTT is parsed as blank-line-separated blocks:

- Header and metadata blocks are skipped.
- `NOTE`, `STYLE`, and `REGION` blocks are skipped.
- A cue block may contain an optional cue id line followed by a timing line.
- Lines after the timing line are the translatable cue text span.

Each cue block records:

- `metadata.format = "vtt"`
- `metadata.cue_index`
- `metadata.identifier`
- `metadata.start_offset` / `metadata.end_offset`
- `metadata.timing`
- `metadata.marker`

## Chunking

VTT cues use the same marker pattern as SRT:

```text
__LT_SUBTITLE_CUE_000001__
First WebVTT cue text.
```

Markers allow robust export after translation and support batching small cues together.

## Export

Export applies translated cue text back to the original source offsets in reverse order, preserving all non-cue blocks exactly as they appeared.

Validation checks:

- Cue count is unchanged.
- Timing lines are unchanged.
- The `WEBVTT` header remains present.

