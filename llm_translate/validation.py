from __future__ import annotations

from uuid import uuid4
import re

from .domain import GlossaryTerm, TranslationChunk, ValidationReport
from .protection import ProtectionEngine


class ValidationEngine:
    def __init__(self) -> None:
        self.protection = ProtectionEngine()

    def validate_chunk(
        self,
        chunk: TranslationChunk,
        glossary_terms: list[GlossaryTerm],
    ) -> ValidationReport:
        issues: list[dict] = []
        source_placeholders = self.protection.placeholders(chunk.protected_text or "")
        target_placeholders = self.protection.placeholders(chunk.target_text or "")

        missing = sorted(source_placeholders - target_placeholders)
        extra = sorted(target_placeholders - source_placeholders)
        if missing:
            issues.append({"type": "MISSING_PLACEHOLDER", "placeholders": missing})
        if extra:
            issues.append({"type": "EXTRA_PLACEHOLDER", "placeholders": extra})
        if not (chunk.target_text or "").strip():
            issues.append({"type": "EMPTY_OUTPUT"})

        fence_count = (chunk.target_text or "").count("```")
        if fence_count % 2 != 0:
            issues.append({"type": "BROKEN_CODE_FENCE"})

        source_tables = self._table_shapes(chunk.source_text)
        target_tables = self._table_shapes(chunk.target_text or "")
        if source_tables and target_tables and source_tables != target_tables:
            issues.append({"type": "TABLE_SHAPE_CHANGED"})

        for term in glossary_terms:
            haystack = chunk.source_text if term.case_sensitive else chunk.source_text.lower()
            needle = term.source_term if term.case_sensitive else term.source_term.lower()
            if needle not in haystack:
                continue
            target = chunk.restored_text or chunk.target_text or ""
            if term.target_term not in target:
                issues.append(
                    {
                        "type": "TERM_MISSING",
                        "source_term": term.source_term,
                        "target_term": term.target_term,
                    }
                )

        status = "PASS" if not issues else "FAIL"
        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=chunk.project_id,
            chunk_id=chunk.id,
            check_type="CHUNK",
            status=status,
            issues=issues,
        )

    def _table_shapes(self, text: str) -> list[int]:
        shapes: list[int] = []
        for line in text.splitlines():
            stripped = line.strip()
            if "|" not in stripped:
                continue
            if re.match(r"^\|?\s*:?-{3,}:?", stripped):
                continue
            shapes.append(len(stripped.strip("|").split("|")))
        return shapes
