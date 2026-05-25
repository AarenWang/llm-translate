from __future__ import annotations

from dataclasses import asdict, replace
import json
import re
from pathlib import Path
from uuid import uuid4
from typing import Any

from ..chunking import ChunkingEngine
from ..domain import ChunkStatus, DocumentBlock, TranslationChunk, TranslationProject, ValidationReport
from ..exporter import MarkdownExporter
from .base import FormatContext


SUBTITLE_CUE_MARKER_RE = re.compile(r"__LT_SUBTITLE_CUE_(\d{6})__")
SRT_TIMING_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}(?:\s+.*)?$")
VTT_TIMING_RE = re.compile(r"^(?:\d{2}:)?\d{2}:\d{2}\.\d{3}\s+-->\s+(?:\d{2}:)?\d{2}:\d{2}\.\d{3}(?:\s+.*)?$")


class SubtitleFormatAdapter:
    format_name = "subtitle"
    file_suffix = ""
    timing_re = SRT_TIMING_RE

    def __init__(self, soft_input_tokens: int = 2200, max_input_tokens: int = 3000):
        self.chunker = ChunkingEngine(soft_input_tokens, max_input_tokens)
        self.exporter = MarkdownExporter()

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == self.file_suffix

    def parse(self, project: TranslationProject, context: FormatContext) -> list[DocumentBlock]:
        text = context.source_path.read_text(encoding="utf-8-sig")
        blocks = self._parse_blocks(project.id, text)
        self._write_ast_snapshot(context.snapshot_dir, blocks)
        return blocks

    def plan_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        chunks: list[TranslationChunk] = []
        pending: list[DocumentBlock] = []
        pending_tokens = 0

        def flush() -> None:
            nonlocal pending, pending_tokens
            if not pending:
                return
            chunk_order = len(chunks)
            chunks.append(
                TranslationChunk(
                    id=f"{project_id}_c_{chunk_order + 1:06d}",
                    project_id=project_id,
                    chapter_id=None,
                    chunk_order=chunk_order,
                    block_ids=[block.id for block in pending],
                    source_text=self._marked_chunk_source(pending),
                    metadata={"format": self.format_name},
                )
            )
            pending = []
            pending_tokens = 0

        for block in blocks:
            block_tokens = self.chunker.estimator.estimate(block.source_text) + 2
            if pending and pending_tokens + block_tokens > self.chunker.soft_input_tokens:
                flush()
            pending.append(block)
            pending_tokens += block_tokens
            if pending_tokens >= self.chunker.max_input_tokens:
                flush()

        flush()
        return chunks

    def prompt_document_format(self) -> str:
        return self.format_name

    def chapter_path(self, chunk: TranslationChunk) -> str | None:
        return None

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> tuple[dict[str, Path], list[ValidationReport], bool]:
        check_prefix = self.format_name.upper()
        reports = [
            report
            for report in reports
            if report.check_type not in {f"{check_prefix}_STRUCTURE", f"{check_prefix}_ARTIFACT"}
        ]
        structure_report = self._validate_structure(project.id, context.source_path, blocks)
        reports.append(structure_report)
        if structure_report.status == "FAIL":
            draft = True

        paths = self._write_artifacts(context, blocks, chunks, reports, draft)
        artifact_report = self._validate_artifact(project.id, context.source_path, paths[self.format_name])
        reports.append(artifact_report)
        if artifact_report.status == "FAIL":
            draft = True
            paths = self._write_artifacts(context, blocks, chunks, reports, draft)
        else:
            self._write_reports(context.artifact_dir, reports)
        return paths, reports, draft

    def _parse_blocks(self, project_id: str, text: str) -> list[DocumentBlock]:
        blocks: list[DocumentBlock] = []
        for block_start, block_end in self._subtitle_block_spans(text):
            block_text = text[block_start:block_end]
            cue = self._cue_text_span(block_text)
            if cue is None:
                continue
            rel_text_start, rel_text_end, timing, identifier = cue
            abs_start, abs_end = self._trim_newlines_span(text, block_start + rel_text_start, block_start + rel_text_end)
            source_text = text[abs_start:abs_end]
            if not source_text.strip():
                continue
            order = len(blocks)
            blocks.append(
                DocumentBlock(
                    id=f"{project_id}_{self.format_name}_{order + 1:06d}",
                    project_id=project_id,
                    parent_id=None,
                    block_order=order,
                    block_type=f"{self.format_name}_cue",
                    level=None,
                    source_text=source_text,
                    metadata={
                        "format": self.format_name,
                        "translatable": True,
                        "cue_index": order,
                        "identifier": identifier,
                        "timing": timing,
                        "start_offset": abs_start,
                        "end_offset": abs_end,
                        "marker": self._marker(order),
                    },
                )
            )
        return blocks

    def _subtitle_block_spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        cursor = 0
        for match in re.finditer(r"\r?\n\s*\r?\n", text):
            start, end = cursor, match.start()
            if text[start:end].strip():
                spans.append((start, end))
            cursor = match.end()
        if cursor < len(text) and text[cursor:].strip():
            spans.append((cursor, len(text)))
        return spans

    def _cue_text_span(self, block_text: str) -> tuple[int, int, str, str | None] | None:
        lines = block_text.splitlines(keepends=True)
        if not lines:
            return None
        offsets: list[int] = []
        cursor = 0
        for line in lines:
            offsets.append(cursor)
            cursor += len(line)

        timing_index = None
        for index, line in enumerate(lines[:3]):
            if self.timing_re.match(line.strip()):
                timing_index = index
                break
        if timing_index is None:
            return None

        identifier = None
        if timing_index > 0:
            candidate = "".join(lines[:timing_index]).strip()
            identifier = candidate or None

        text_index = timing_index + 1
        if text_index >= len(lines):
            return None

        text_start = offsets[text_index]
        text_end = len(block_text)
        timing = lines[timing_index].strip()
        return text_start, text_end, timing, identifier

    def _marked_chunk_source(self, blocks: list[DocumentBlock]) -> str:
        return "\n\n".join(f"{block.metadata['marker']}\n{block.source_text}" for block in blocks)

    def _marker(self, order: int) -> str:
        return f"__LT_SUBTITLE_CUE_{order + 1:06d}__"

    def _split_marked_translation(self, text: str | None) -> dict[str, str]:
        if not text:
            return {}
        matches = list(SUBTITLE_CUE_MARKER_RE.finditer(text))
        if not matches:
            return {}
        translations: dict[str, str] = {}
        for index, match in enumerate(matches):
            marker = match.group(0)
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            translations[marker] = text[start:end].strip()
        return translations

    def _write_artifacts(
        self,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> dict[str, Path]:
        context.artifact_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".draft" if draft else ""
        subtitle_path = context.artifact_dir / f"translated{suffix}{self.file_suffix}"
        replacements = self._replacement_map(blocks, chunks, draft)
        subtitle_path.write_text(self._build_modified_subtitle(context.source_path, replacements), encoding="utf-8")
        paths = self.exporter.export(context.artifact_dir, self._markdown_chunks(blocks, chunks), reports, draft=draft)
        paths[self.format_name] = subtitle_path
        self._write_review_note(paths["translated"], subtitle_path)
        return paths

    def _replacement_map(
        self,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        draft: bool,
    ) -> dict[tuple[int, int], str]:
        blocks_by_id = {block.id: block for block in blocks}
        replacements: dict[tuple[int, int], str] = {}
        for chunk in chunks:
            translated_by_marker = self._split_marked_translation(chunk.restored_text)
            for block_id in chunk.block_ids:
                block = blocks_by_id.get(block_id)
                if block is None:
                    continue
                marker = block.metadata["marker"]
                if marker in translated_by_marker:
                    text = translated_by_marker[marker]
                elif chunk.restored_text and len(chunk.block_ids) == 1:
                    text = chunk.restored_text.strip()
                elif draft or chunk.status == ChunkStatus.SKIPPED:
                    text = block.source_text
                else:
                    continue
                replacements[(int(block.metadata["start_offset"]), int(block.metadata["end_offset"]))] = text
        return replacements

    def _build_modified_subtitle(self, source_path: Path, replacements: dict[tuple[int, int], str]) -> str:
        text = source_path.read_text(encoding="utf-8-sig")
        for (start, end), replacement in sorted(replacements.items(), reverse=True):
            text = text[:start] + replacement + text[end:]
        return text

    def _markdown_chunks(
        self,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
    ) -> list[TranslationChunk]:
        blocks_by_id = {block.id: block for block in blocks}
        markdown_chunks: list[TranslationChunk] = []
        for chunk in chunks:
            source_parts: list[str] = []
            target_parts: list[str] = []
            translated_by_marker = self._split_marked_translation(chunk.restored_text)
            for block_id in chunk.block_ids:
                block = blocks_by_id.get(block_id)
                if block is None:
                    continue
                source_parts.append(block.source_text)
                marker = block.metadata["marker"]
                if marker in translated_by_marker:
                    target_parts.append(translated_by_marker[marker])
            markdown_chunks.append(
                replace(
                    chunk,
                    source_text="\n\n".join(source_parts),
                    restored_text="\n\n".join(target_parts) if target_parts else chunk.restored_text,
                )
            )
        return markdown_chunks

    def _validate_structure(
        self,
        project_id: str,
        source_path: Path,
        blocks: list[DocumentBlock],
    ) -> ValidationReport:
        issues: list[dict[str, Any]] = []
        if not blocks:
            issues.append({"type": f"{self.format_name.upper()}_NO_TRANSLATABLE_CUES"})
        try:
            text = source_path.read_text(encoding="utf-8-sig")
            if self.format_name == "vtt" and not text.lstrip("\ufeff").startswith("WEBVTT"):
                issues.append({"type": "VTT_MISSING_HEADER"})
        except (OSError, UnicodeDecodeError) as exc:
            issues.append({"type": f"{self.format_name.upper()}_SOURCE_UNREADABLE", "error": str(exc)})
        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type=f"{self.format_name.upper()}_STRUCTURE",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )

    def _validate_artifact(self, project_id: str, source_path: Path, exported_path: Path) -> ValidationReport:
        issues: list[dict[str, Any]] = []
        try:
            original = source_path.read_text(encoding="utf-8-sig")
            exported = exported_path.read_text(encoding="utf-8")
            original_blocks = self._parse_blocks(project_id, original)
            exported_blocks = self._parse_blocks(project_id, exported)
            if len(original_blocks) != len(exported_blocks):
                issues.append(
                    {
                        "type": f"{self.format_name.upper()}_CUE_COUNT_CHANGED",
                        "original": len(original_blocks),
                        "exported": len(exported_blocks),
                    }
                )
            original_timing = [block.metadata["timing"] for block in original_blocks]
            exported_timing = [block.metadata["timing"] for block in exported_blocks]
            if original_timing != exported_timing:
                issues.append({"type": f"{self.format_name.upper()}_TIMING_CHANGED"})
            if self.format_name == "vtt" and not exported.lstrip("\ufeff").startswith("WEBVTT"):
                issues.append({"type": "VTT_HEADER_CHANGED"})
        except (OSError, UnicodeDecodeError) as exc:
            issues.append({"type": f"{self.format_name.upper()}_ARTIFACT_ACCESS_ERROR", "error": str(exc)})
        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type=f"{self.format_name.upper()}_ARTIFACT",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )

    def _write_reports(self, artifact_dir: Path, reports: list[ValidationReport]) -> None:
        report_json_path = artifact_dir / "validation-report.json"
        report_md_path = artifact_dir / "validation-report.md"
        report_json_path.write_text(
            json.dumps([report.__dict__ for report in reports], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows = ["# Validation Report", "", "| Chunk | Check | Status | Issues |", "|---|---|---|---|"]
        for report in reports:
            issues = "; ".join(issue["type"] for issue in report.issues) or "-"
            rows.append(f"| {report.chunk_id or '-'} | {report.check_type} | {report.status} | {issues} |")
        report_md_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    def _write_review_note(self, translated_md_path: Path, subtitle_path: Path) -> None:
        body = translated_md_path.read_text(encoding="utf-8")
        note = (
            "<!-- NOTE: This Markdown file contains translated subtitle cue text only. "
            f"The complete structure-preserving subtitle artifact is {subtitle_path.name}. -->\n\n"
        )
        translated_md_path.write_text(note + body, encoding="utf-8")

    def _write_ast_snapshot(self, snapshot_dir: Path, blocks: list[DocumentBlock]) -> None:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "ast.json").write_text(
            json.dumps([asdict(block) for block in blocks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _trim_newlines_span(self, text: str, start: int, end: int) -> tuple[int, int]:
        while start < end and text[start] in "\r\n":
            start += 1
        while end > start and text[end - 1] in "\r\n":
            end -= 1
        return start, end


class SrtFormatAdapter(SubtitleFormatAdapter):
    format_name = "srt"
    file_suffix = ".srt"
    timing_re = SRT_TIMING_RE


class VttFormatAdapter(SubtitleFormatAdapter):
    format_name = "vtt"
    file_suffix = ".vtt"
    timing_re = VTT_TIMING_RE

    def _cue_text_span(self, block_text: str) -> tuple[int, int, str, str | None] | None:
        stripped = block_text.lstrip("\ufeff")
        upper = stripped.strip().upper()
        if upper.startswith("WEBVTT") or upper.startswith("NOTE") or upper.startswith("STYLE") or upper.startswith("REGION"):
            return None
        return super()._cue_text_span(block_text)

