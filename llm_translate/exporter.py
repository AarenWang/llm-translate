from __future__ import annotations

import json
from pathlib import Path

from .domain import TranslationChunk, ValidationReport


class MarkdownExporter:
    def export(
        self,
        artifact_dir: Path,
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool = False,
    ) -> dict[str, Path]:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".draft" if draft else ""
        translated_path = artifact_dir / f"translated{suffix}.md"
        bilingual_path = artifact_dir / f"bilingual{suffix}.md"
        log_path = artifact_dir / "translation-log.json"
        report_json_path = artifact_dir / "validation-report.json"
        report_md_path = artifact_dir / "validation-report.md"

        translated_path.write_text(self._translated(chunks, draft), encoding="utf-8")
        bilingual_path.write_text(self._bilingual(chunks), encoding="utf-8")
        log_path.write_text(
            json.dumps([self._chunk_log(chunk) for chunk in chunks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report_json_path.write_text(
            json.dumps([report.__dict__ for report in reports], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report_md_path.write_text(self._report_markdown(reports), encoding="utf-8")
        return {
            "translated": translated_path,
            "bilingual": bilingual_path,
            "translation_log": log_path,
            "validation_report_json": report_json_path,
            "validation_report_md": report_md_path,
        }

    def _translated(self, chunks: list[TranslationChunk], draft: bool) -> str:
        parts: list[str] = []
        for chunk in chunks:
            text = chunk.restored_text
            if not text:
                marker = f"<!-- {chunk.id} {chunk.status.value} -->"
                text = marker if draft else ""
            parts.append(text)
        return "\n\n".join(part for part in parts if part).strip() + "\n"

    def _bilingual(self, chunks: list[TranslationChunk]) -> str:
        parts: list[str] = []
        for chunk in chunks:
            target = chunk.restored_text or f"[{chunk.status.value}]"
            parts.append(
                f"## Source: {chunk.id}\n\n{chunk.source_text}\n\n"
                f"## Translation: {chunk.id}\n\n{target}\n"
            )
        return "\n---\n\n".join(parts).strip() + "\n"

    def _chunk_log(self, chunk: TranslationChunk) -> dict:
        return {
            "chunk_id": chunk.id,
            "status": chunk.status.value,
            "retry_count": chunk.retry_count,
            "model_name": chunk.model_name,
            "prompt_version": chunk.prompt_version,
            "glossary_version": chunk.glossary_version,
            "style_guide_version": chunk.style_guide_version,
            "protection_policy_version": chunk.protection_policy_version,
            "error_message": chunk.error_message,
        }

    def _report_markdown(self, reports: list[ValidationReport]) -> str:
        if not reports:
            return "# Validation Report\n\nNo validation reports.\n"
        rows = ["# Validation Report", "", "| Chunk | Check | Status | Issues |", "|---|---|---|---|"]
        for report in reports:
            issues = "; ".join(issue["type"] for issue in report.issues) or "-"
            rows.append(f"| {report.chunk_id or '-'} | {report.check_type} | {report.status} | {issues} |")
        return "\n".join(rows) + "\n"
