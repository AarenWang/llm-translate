"""DOCX validation for translated documents."""

from __future__ import annotations

from uuid import uuid4
import re

from .domain import GlossaryTerm, TranslationChunk, ValidationReport
from .protection import ProtectionEngine


class DocxValidator:
    """Validate DOCX translations for quality and integrity."""

    def __init__(self) -> None:
        self.protection = ProtectionEngine()

    def validate_chunk(
        self,
        chunk: TranslationChunk,
        glossary_terms: list[GlossaryTerm],
    ) -> ValidationReport:
        """Validate a translated DOCX chunk.

        Args:
            chunk: Translation chunk to validate
            glossary_terms: Glossary terms to check

        Returns:
            ValidationReport with any issues found
        """
        issues: list[dict] = []

        # Check placeholder integrity
        source_placeholders = self.protection.placeholders(chunk.protected_text or chunk.source_text)
        target_placeholders = self.protection.placeholders(chunk.target_text or "")
        missing = sorted(source_placeholders - target_placeholders)
        extra = sorted(target_placeholders - source_placeholders)

        if missing:
            issues.append({"type": "MISSING_PLACEHOLDER", "placeholders": missing})
        if extra:
            issues.append({"type": "EXTRA_PLACEHOLDER", "placeholders": extra})

        # Check for empty output
        if not (chunk.target_text or "").strip():
            issues.append({"type": "EMPTY_OUTPUT"})

        # Check for broken code patterns (if any code-like content was translated)
        if self._has_broken_code_patterns(chunk):
            issues.append({"type": "BROKEN_CODE_PATTERNS"})

        # Check paragraph structure preservation
        if self._paragraph_count_changed(chunk):
            issues.append({"type": "PARAGRAPH_COUNT_CHANGED"})

        # Check heading level preservation
        if self._heading_levels_changed(chunk):
            issues.append({"type": "HEADING_LEVELS_CHANGED"})

        # Check glossary term compliance
        for term in glossary_terms:
            if self._term_missing(chunk, term):
                issues.append({
                    "type": "TERM_MISSING",
                    "source_term": term.source_term,
                    "target_term": term.target_term,
                })

        # Check for translation length anomalies
        if self._has_length_anomaly(chunk):
            issues.append({"type": "LENGTH_ANOMALY"})

        # Determine overall status
        status = "PASS" if not issues else "FAIL"

        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=chunk.project_id,
            chunk_id=chunk.id,
            check_type="DOCX_CHUNK",
            status=status,
            issues=issues,
        )

    def validate_document_integrity(
        self,
        source_blocks: list,
        translated_chunks: list[TranslationChunk],
    ) -> ValidationReport:
        """Validate overall document integrity after translation.

        Args:
            source_blocks: Original document blocks
            translated_chunks: Translated chunks

        Returns:
            ValidationReport with any structural issues
        """
        issues: list[dict] = []

        # Check that all blocks were translated
        translated_block_ids = set()
        for chunk in translated_chunks:
            translated_block_ids.update(chunk.block_ids)

        missing_blocks = [
            block.id for block in source_blocks
            if block.id not in translated_block_ids and block.metadata.get("translatable", True)
        ]

        if missing_blocks:
            issues.append({
                "type": "MISSING_TRANSLATIONS",
                "block_ids": missing_blocks,
                "count": len(missing_blocks)
            })

        # Check document structure preservation
        source_structure = self._analyze_document_structure(source_blocks)
        translated_structure = self._analyze_translated_structure(translated_chunks)

        # Compare only the structural elements, not total counts
        structural_elements = ["headings", "paragraphs", "tables", "heading_levels"]
        structure_changed = any(
            source_structure.get(key) != translated_structure.get(key)
            for key in structural_elements
        )

        if structure_changed:
            issues.append({
                "type": "STRUCTURE_CHANGED",
                "source": source_structure,
                "translated": translated_structure
            })

        status = "PASS" if not issues else "FAIL"
        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=translated_chunks[0].project_id if translated_chunks else "unknown",
            chunk_id=None,
            check_type="DOCX_DOCUMENT",
            status=status,
            issues=issues,
        )

    def _has_broken_code_patterns(self, chunk: TranslationChunk) -> bool:
        """Check if code-like patterns were broken during translation.

        Args:
            chunk: Translation chunk to check

        Returns:
            True if broken code patterns detected
        """
        if not chunk.target_text:
            return False

        # Check for unbalanced brackets in translated text
        text = chunk.target_text
        if text.count('{') != text.count('}'):
            return True
        if text.count('(') != text.count(')'):
            return True
        if text.count('[') != text.count(']'):
            return True

        return False

    def _paragraph_count_changed(self, chunk: TranslationChunk) -> bool:
        """Check if paragraph count changed significantly.

        Args:
            chunk: Translation chunk to check

        Returns:
            True if paragraph count changed significantly
        """
        source_paragraphs = len([p for p in chunk.source_text.split('\n') if p.strip()])
        target_paragraphs = len([p for p in (chunk.target_text or "").split('\n') if p.strip()])

        # Allow for some variation due to translation
        return abs(source_paragraphs - target_paragraphs) > max(2, source_paragraphs * 0.5)

    def _heading_levels_changed(self, chunk: TranslationChunk) -> bool:
        """Check if heading structure was preserved.

        Args:
            chunk: Translation chunk to check

        Returns:
            True if heading levels changed
        """
        # Extract heading levels from source
        source_headings = re.findall(r'^#+\s', chunk.source_text, re.MULTILINE)
        target_headings = re.findall(r'^#+\s', chunk.target_text or "", re.MULTILINE)

        return len(source_headings) != len(target_headings)

    def _term_missing(self, chunk: TranslationChunk, term: GlossaryTerm) -> bool:
        """Check if a glossary term translation is missing.

        Args:
            chunk: Translation chunk to check
            term: Glossary term to check

        Returns:
            True if term translation is missing
        """
        # Check if source term is in source text
        haystack = chunk.source_text if term.case_sensitive else chunk.source_text.lower()
        needle = term.source_term if term.case_sensitive else term.source_term.lower()
        if needle not in haystack:
            return False

        # Check if target term is in translated text
        target = chunk.restored_text or chunk.target_text or ""
        return term.target_term not in target

    def _has_length_anomaly(self, chunk: TranslationChunk) -> bool:
        """Check if translation length is anomalous.

        Args:
            chunk: Translation chunk to check

        Returns:
            True if length is anomalous
        """
        if not chunk.target_text:
            return False

        source_len = len(chunk.source_text)
        target_len = len(chunk.target_text)

        # Check for extremely short or long translations
        if target_len < source_len * 0.1:  # Less than 10% of source
            return True
        if target_len > source_len * 5:  # More than 5x source
            return True

        return False

    def _analyze_document_structure(self, blocks: list) -> dict:
        """Analyze document structure.

        Args:
            blocks: Document blocks to analyze

        Returns:
            Dictionary with structure information
        """
        structure = {
            "total_blocks": len(blocks),
            "headings": 0,
            "paragraphs": 0,
            "tables": 0,
            "heading_levels": set(),
        }

        for block in blocks:
            if block.block_type.startswith("docx_heading"):
                structure["headings"] += 1
                # Check both level field and metadata
                level = block.level or block.metadata.get("heading_level")
                if level is not None:
                    structure["heading_levels"].add(level)
            elif block.block_type == "docx_paragraph":
                structure["paragraphs"] += 1
            elif block.block_type == "docx_table_cell":
                structure["tables"] += 1

        # Convert set to list for JSON serialization
        structure["heading_levels"] = sorted(list(structure["heading_levels"]))
        return structure

    def _analyze_translated_structure(self, chunks: list[TranslationChunk]) -> dict:
        """Analyze translated document structure.

        Args:
            chunks: Translated chunks to analyze

        Returns:
            Dictionary with structure information
        """
        structure = {
            "total_chunks": len(chunks),
            "headings": 0,
            "paragraphs": 0,
            "tables": 0,
            "heading_levels": set(),
        }

        for chunk in chunks:
            # Count headings in source text
            headings = re.findall(r'^#+\s', chunk.source_text, re.MULTILINE)
            structure["headings"] += len(headings)

            # Count paragraphs
            paragraphs = [p for p in chunk.source_text.split('\n') if p.strip()]
            structure["paragraphs"] += len(paragraphs)

            # Extract heading levels
            for heading in headings:
                level = len(heading.strip())
                structure["heading_levels"].add(level)

        # Convert set to list for JSON serialization
        structure["heading_levels"] = sorted(list(structure["heading_levels"]))
        return structure
