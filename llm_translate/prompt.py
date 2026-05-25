from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_STYLE_GUIDE
from .domain import GlossaryTerm, TranslationChunk


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


class PromptBuilder:
    def build(
        self,
        chunk: TranslationChunk,
        target_language: str,
        glossary_terms: list[GlossaryTerm],
        style_guide: str = DEFAULT_STYLE_GUIDE,
        chapter_path: str | None = None,
    ) -> Prompt:
        matched_terms = self._matched_terms(chunk.protected_text or chunk.source_text, glossary_terms)
        glossary_text = "\n".join(
            f"- {term.source_term} => {term.target_term}" for term in matched_terms
        ) or "- No matched glossary terms."
        system = (
            "You are a structured long-document translation engine. Translate "
            "only natural-language text, preserve Markdown structure, and never "
            "rewrite placeholders."
        )
        user = f"""Target language: {target_language}
Style guide: {style_guide}
Chapter context: {chapter_path or "N/A"}

Glossary terms that must be followed:
{glossary_text}

Rules:
- Return only translated Markdown.
- Do not add explanations.
- Do not remove, duplicate, or modify placeholders like __LT_URL_000001__.
- Preserve code, URLs, file paths, API paths, and references represented by placeholders.

Text to translate:
{chunk.protected_text or chunk.source_text}
"""
        return Prompt(system=system, user=user)

    def _matched_terms(self, text: str, terms: list[GlossaryTerm]) -> list[GlossaryTerm]:
        matches: list[GlossaryTerm] = []
        for term in terms:
            haystack = text if term.case_sensitive else text.lower()
            needle = term.source_term if term.case_sensitive else term.source_term.lower()
            if needle in haystack:
                matches.append(term)
        return matches
