# LaTeX Format Adapter Design

## Goals

Add `.tex` / `.latex` translation support without introducing LaTeX-specific logic into `TranslationService`.

The adapter should:

- Preserve the original LaTeX document structure and commands.
- Translate natural-language text in section-like commands and body paragraphs.
- Skip comments, math spans, and code/math-heavy environments.
- Export the standard Markdown review artifacts plus a structure-preserving translated `.tex`.

## Parsing Model

The LaTeX adapter records replaceable source spans instead of building a full TeX AST. Each translatable span becomes a `DocumentBlock` with:

- `metadata.format = "latex"`
- `metadata.start_offset` / `metadata.end_offset` for source reconstruction
- `metadata.marker` for robust chunk splitting after LLM translation
- `block_type` such as `latex_command_arg` or `latex_paragraph`

Protected source regions are excluded from parsing:

- `%` comments
- Inline/display math: `$...$`, `$$...$$`, `\(...\)`, `\[...\]`
- Environments such as `verbatim`, `lstlisting`, `minted`, `equation`, `align`, `tikzpicture`, and `tabular`

Common translatable command arguments are parsed, including `\title{}`, `\chapter{}`, `\section{}`, `\caption{}`, and `\footnote{}`.

## Chunking

Chunks contain one or more marked blocks:

```text
__LT_LATEX_BLOCK_000001__
Introduction

__LT_LATEX_BLOCK_000002__
This paper describes ...
```

Markers are preserved by the prompt and used during export to map translated text back to individual source spans.

## Export

The exporter:

1. Splits each translated chunk by `__LT_LATEX_BLOCK_000000__` markers.
2. Builds a replacement map from original span offsets to translated text.
3. Applies replacements in reverse source order to avoid offset drift.
4. Writes `translated.tex` or `translated.draft.tex`.
5. Emits the normal Markdown review, bilingual, log, and validation artifacts.

## Validation

The first validation layer checks that:

- The source produced at least one translatable block.
- `\begin{...}` / `\end{...}` environment sequences are unchanged in the exported artifact.
- The exported artifact can be written without dropping the document body.

This is intentionally conservative. A future iteration can add optional `latexmk` compilation checks when a TeX distribution is available.

