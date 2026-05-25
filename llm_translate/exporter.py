from __future__ import annotations

import json
from pathlib import Path

from .domain import DocumentBlock, TranslationChunk, ValidationReport
from .parser.ipynb import source_from_text


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


class IpynbExporter:
    def __init__(self) -> None:
        self.markdown_exporter = MarkdownExporter()

    def export(
        self,
        artifact_dir: Path,
        original_notebook: dict,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool = False,
    ) -> dict[str, Path]:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".draft" if draft else ""
        ipynb_path = artifact_dir / f"translated{suffix}.ipynb"
        notebook = json.loads(json.dumps(original_notebook, ensure_ascii=False))

        chunk_by_block_id = {
            block_id: [chunk for chunk in chunks if block_id in chunk.block_ids]
            for block_id in {block_id for chunk in chunks for block_id in chunk.block_ids}
        }

        for block_id, block_chunks in chunk_by_block_id.items():
            block_chunks.sort(
                key=lambda chunk: (
                    int(chunk.metadata.get("chunk_part", 0)),
                    chunk.chunk_order,
                )
            )

        for block in blocks:
            if block.block_type != "notebook_markdown_cell":
                continue
            cell_index = block.metadata["cell_index"]
            source_kind = block.metadata.get("source_kind", "list")
            block_chunks = chunk_by_block_id.get(block.id, [])
            translated_parts = [chunk.restored_text for chunk in block_chunks if chunk.restored_text]
            if translated_parts and len(translated_parts) == len(block_chunks):
                text = "\n\n".join(part.rstrip("\n") for part in translated_parts)
            elif draft:
                statuses = ", ".join(f"{chunk.id}:{chunk.status.value}" for chunk in block_chunks) or "SKIPPED"
                text = f"<!-- TRANSLATION_PENDING: {statuses} -->\n\n{block.source_text}"
            else:
                text = block.source_text
            notebook["cells"][cell_index]["source"] = source_from_text(text, source_kind)

        ipynb_path.write_text(
            json.dumps(notebook, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        paths = self.markdown_exporter.export(artifact_dir, chunks, reports, draft=draft)
        paths["ipynb"] = ipynb_path
        self._write_notebook_review_note(paths["translated"], ipynb_path)
        return paths

    def _write_notebook_review_note(self, translated_md_path: Path, ipynb_path: Path) -> None:
        body = translated_md_path.read_text(encoding="utf-8")
        note = (
            "<!-- NOTE: This Markdown file contains translated notebook markdown cells only. "
            f"The complete translated notebook is {ipynb_path.name}. -->\n\n"
        )
        translated_md_path.write_text(note + body, encoding="utf-8")
