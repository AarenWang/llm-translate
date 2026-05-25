from __future__ import annotations

from dataclasses import dataclass

from .config import DEFAULT_STYLE_GUIDE
from .domain import GlossaryTerm, TranslationChunk


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


class PromptBuilder:
    def add_style_guide(self, style_guide: str = DEFAULT_STYLE_GUIDE) -> "PromptBuilder":
        """Add style guide to prompt (for chaining)."""
        self._style_guide = style_guide
        return self

    def add_translation_prompt(
        self,
        source_text: str,
        document_format: str,
        target_language: str = "zh-CN",
        chunk_count: int = 1,
        is_batch: bool = False,
        chapter_path: str | None = None,
    ) -> "PromptBuilder":
        """Add translation prompt with source text."""
        self._target_language = target_language
        self._document_format = document_format
        self._chapter_path = chapter_path
        self._source_text = source_text
        self._chunk_count = chunk_count
        self._is_batch = is_batch
        return self

    def add_glossary(self, terms: list[GlossaryTerm]) -> "PromptBuilder":
        """Add glossary terms to prompt."""
        self._glossary_terms = terms
        return self

    def build(self) -> Prompt:
        """Build the final prompt from accumulated components."""
        # Get matched terms if we have source text
        if hasattr(self, '_source_text') and hasattr(self, '_glossary_terms'):
            matched_terms = self._matched_terms(self._source_text, self._glossary_terms)
            glossary_text = "\n".join(
                f"- {term.source_term} => {term.target_term}" for term in matched_terms
            ) or "- No matched glossary terms."
        else:
            glossary_text = "- No glossary terms provided."

        target_language = getattr(self, '_target_language', 'zh-CN')
        style_guide = getattr(self, '_style_guide', DEFAULT_STYLE_GUIDE)
        document_format = getattr(self, '_document_format', 'markdown')
        chapter_path = getattr(self, '_chapter_path', None)
        source_text = getattr(self, '_source_text', '')
        chunk_count = getattr(self, '_chunk_count', 1)
        is_batch = getattr(self, '_is_batch', False)

        if document_format == "ipynb":
            system = (
                "You are a structured Jupyter Notebook markdown-cell translation engine. "
                "Translate only natural-language text inside the current markdown cell, "
                "preserve Markdown/HTML structure, and never rewrite placeholders."
            )
            extra_rules = (
                "- This input is one piece of a Jupyter Notebook markdown cell.\n"
                "- Do not add notebook cell markers, JSON, explanations, or code execution output.\n"
                "- Preserve HTML tags and attachment references represented by placeholders.\n"
            )
            return_type = "translated Markdown"
        elif document_format == "epub":
            system = (
                "You are a structured EPUB XHTML text-node translation engine. "
                "Translate only the natural-language text from the current text node, "
                "do not emit HTML, and never rewrite placeholders."
            )
            if is_batch and chunk_count > 1:
                extra_rules = (
                    f"- This input contains {chunk_count} separate EPUB text nodes separated by \"\\n\\n\".\n"
                    "- Translate each text node independently and maintain the separator structure.\n"
                    "- Return translated text only, without HTML, Markdown wrappers, or explanations.\n"
                    "- Keep placeholders unchanged; EPUB attributes and resources are handled outside the model.\n"
                )
            else:
                extra_rules = (
                    "- This input is plain text extracted from one EPUB XHTML text node.\n"
                    "- Return plain translated text only, without HTML, Markdown wrappers, or explanations.\n"
                    "- Keep placeholders unchanged; EPUB attributes and resources are handled outside the model.\n"
                )
            return_type = "plain translated text"
        elif document_format == "html":
            system = (
                "You are a structured HTML DOM text-node translation engine. "
                "Translate only the natural-language text after each DOM node marker, "
                "do not emit HTML, and never rewrite markers or placeholders."
            )
            extra_rules = (
                "- This input contains one or more HTML DOM text nodes separated by markers like __LT_HTML_NODE_000001__.\n"
                "- Keep every marker exactly as written and in the same order.\n"
                "- Translate the text following each marker; do not translate the marker itself.\n"
                "- Return plain translated text only, without HTML, Markdown wrappers, or explanations.\n"
                "- Keep placeholders unchanged; HTML tags, attributes, links, images, and styles are handled outside the model.\n"
            )
            return_type = "plain translated text"
        elif document_format == "plain_text":
            system = (
                "You are a plain text translation engine. Translate natural-language text, "
                "preserve paragraph breaks, and never rewrite placeholders."
            )
            extra_rules = (
                "- This input is plain text without document formatting.\n"
                "- Preserve paragraph boundaries and line breaks when they carry meaning.\n"
                "- Do not add Markdown, HTML, explanations, titles, or wrappers.\n"
            )
            return_type = "plain translated text"
        else:
            system = (
                "You are a structured long-document translation engine. Translate "
                "only natural-language text, preserve Markdown structure, and never "
                "rewrite placeholders."
            )
            extra_rules = ""
            return_type = "translated Markdown"

        user = f"""Target language: {target_language}
Style guide: {style_guide}
Chapter context: {chapter_path or "N/A"}

Glossary terms that must be followed:
{glossary_text}

Rules:
- Return only {return_type}.
- Do not add explanations.
- Do not remove, duplicate, or modify placeholders like __LT_URL_000001__.
- Preserve code, URLs, file paths, API paths, and references represented by placeholders.
{extra_rules}

Text to translate:
{source_text}
"""
        return Prompt(system=system, user=user)

    def build_legacy(
        self,
        chunk: TranslationChunk,
        target_language: str = "zh-CN",
        glossary_terms: list[GlossaryTerm] | None = None,
        style_guide: str = DEFAULT_STYLE_GUIDE,
        chapter_path: str | None = None,
        document_format: str = "markdown",
    ) -> Prompt:
        """Build prompt using legacy API for backward compatibility."""
        if glossary_terms is None:
            glossary_terms = []

        matched_terms = self._matched_terms(chunk.protected_text or chunk.source_text, glossary_terms)
        glossary_text = "\n".join(
            f"- {term.source_term} => {term.target_term}" for term in matched_terms
        ) or "- No matched glossary terms."
        if document_format == "ipynb":
            system = (
                "You are a structured Jupyter Notebook markdown-cell translation engine. "
                "Translate only natural-language text inside the current markdown cell, "
                "preserve Markdown/HTML structure, and never rewrite placeholders."
            )
            extra_rules = (
                "- This input is one piece of a Jupyter Notebook markdown cell.\n"
                "- Do not add notebook cell markers, JSON, explanations, or code execution output.\n"
                "- Preserve HTML tags and attachment references represented by placeholders.\n"
            )
            return_type = "translated Markdown"
        elif document_format == "epub":
            system = (
                "You are a structured EPUB XHTML text-node translation engine. "
                "Translate only the natural-language text from the current text node, "
                "do not emit HTML, and never rewrite placeholders."
            )
            extra_rules = (
                "- This input is plain text extracted from one EPUB XHTML text node.\n"
                "- Return plain translated text only, without HTML, Markdown wrappers, or explanations.\n"
                "- Keep placeholders unchanged; EPUB attributes and resources are handled outside the model.\n"
            )
            return_type = "plain translated text"
        elif document_format == "html":
            system = (
                "You are a structured HTML DOM text-node translation engine. "
                "Translate only the natural-language text after each DOM node marker, "
                "do not emit HTML, and never rewrite markers or placeholders."
            )
            extra_rules = (
                "- This input contains one or more HTML DOM text nodes separated by markers like __LT_HTML_NODE_000001__.\n"
                "- Keep every marker exactly as written and in the same order.\n"
                "- Translate the text following each marker; do not translate the marker itself.\n"
                "- Return plain translated text only, without HTML, Markdown wrappers, or explanations.\n"
                "- Keep placeholders unchanged; HTML tags, attributes, links, images, and styles are handled outside the model.\n"
            )
            return_type = "plain translated text"
        elif document_format == "plain_text":
            system = (
                "You are a plain text translation engine. Translate natural-language text, "
                "preserve paragraph breaks, and never rewrite placeholders."
            )
            extra_rules = (
                "- This input is plain text without document formatting.\n"
                "- Preserve paragraph boundaries and line breaks when they carry meaning.\n"
                "- Do not add Markdown, HTML, explanations, titles, or wrappers.\n"
            )
            return_type = "plain translated text"
        else:
            system = (
                "You are a structured long-document translation engine. Translate "
                "only natural-language text, preserve Markdown structure, and never "
                "rewrite placeholders."
            )
            extra_rules = ""
            return_type = "translated Markdown"
        user = f"""Target language: {target_language}
Style guide: {style_guide}
Chapter context: {chapter_path or "N/A"}

Glossary terms that must be followed:
{glossary_text}

Rules:
- Return only {return_type}.
- Do not add explanations.
- Do not remove, duplicate, or modify placeholders like __LT_URL_000001__.
- Preserve code, URLs, file paths, API paths, and references represented by placeholders.
{extra_rules}

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
