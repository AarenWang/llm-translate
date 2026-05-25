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


LATEX_BLOCK_MARKER_RE = re.compile(r"__LT_LATEX_BLOCK_(\d{6})__")


class LatexFormatAdapter:
    format_name = "latex"

    _translatable_commands = {
        "title",
        "author",
        "chapter",
        "section",
        "subsection",
        "subsubsection",
        "paragraph",
        "subparagraph",
        "caption",
        "footnote",
    }
    _protected_environments = {
        "align",
        "align*",
        "displaymath",
        "equation",
        "equation*",
        "gather",
        "gather*",
        "lstlisting",
        "math",
        "minted",
        "tabular",
        "tabular*",
        "tikzpicture",
        "verbatim",
        "verbatim*",
    }

    def __init__(self, soft_input_tokens: int = 2200, max_input_tokens: int = 3000):
        self.chunker = ChunkingEngine(soft_input_tokens, max_input_tokens)
        self.exporter = MarkdownExporter()

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in {".tex", ".latex"}

    def parse(self, project: TranslationProject, context: FormatContext) -> list[DocumentBlock]:
        text = context.source_path.read_text(encoding="utf-8")
        blocks = self._parse_blocks(project.id, text)
        self._write_ast_snapshot(context.snapshot_dir, blocks)
        return blocks

    def plan_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        chunks: list[TranslationChunk] = []
        pending: list[DocumentBlock] = []
        pending_tokens = 0
        current_chapter_id: str | None = None

        def flush() -> None:
            nonlocal pending, pending_tokens
            if not pending:
                return
            chunk_order = len(chunks)
            chunks.append(
                TranslationChunk(
                    id=f"{project_id}_c_{chunk_order + 1:06d}",
                    project_id=project_id,
                    chapter_id=current_chapter_id,
                    chunk_order=chunk_order,
                    block_ids=[block.id for block in pending],
                    source_text=self._marked_chunk_source(pending),
                    metadata={"format": "latex"},
                )
            )
            pending = []
            pending_tokens = 0

        for block in blocks:
            if not block.metadata.get("translatable", True):
                continue
            if block.block_type == "latex_command_arg" and block.level is not None and block.level <= 2:
                flush()
                current_chapter_id = block.id

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
        return chunk.chapter_id

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> tuple[dict[str, Path], list[ValidationReport], bool]:
        reports = [report for report in reports if report.check_type not in {"LATEX_STRUCTURE", "LATEX_ARTIFACT"}]
        structure_report = self._validate_structure(project.id, context.source_path, blocks)
        reports.append(structure_report)
        if structure_report.status == "FAIL":
            draft = True

        paths = self._write_artifacts(context, blocks, chunks, reports, draft)
        artifact_report = self._validate_artifact(project.id, context.source_path, paths["latex"])
        reports.append(artifact_report)
        if artifact_report.status == "FAIL":
            draft = True
            paths = self._write_artifacts(context, blocks, chunks, reports, draft)
        else:
            self._write_reports(context.artifact_dir, reports)
        return paths, reports, draft

    def _parse_blocks(self, project_id: str, text: str) -> list[DocumentBlock]:
        blocks: list[DocumentBlock] = []
        protected = self._protected_ranges(text)
        occupied = protected.copy()

        for match in re.finditer(r"\\([A-Za-z]+)\*?", text):
            command = match.group(1)
            if command not in self._translatable_commands or self._inside_ranges(match.start(), protected):
                continue

            arg = self._first_required_argument(text, match.end())
            if arg is None:
                continue
            content_start, content_end, full_end = arg
            source_text = text[content_start:content_end].strip()
            if not self._looks_translatable(source_text):
                continue

            occupied.append((match.start(), full_end))
            start, end = self._trim_span(text, content_start, content_end)
            level = self._heading_level(command)
            blocks.append(
                self._block(
                    project_id,
                    blocks,
                    "latex_command_arg",
                    text[start:end],
                    start,
                    end,
                    {"command": command},
                    level=level,
                )
            )

        occupied = self._merge_ranges(occupied)
        for start, end in self._complement_ranges(len(text), occupied):
            segment = text[start:end]
            for rel_start, rel_end in self._paragraph_spans(segment):
                abs_start, abs_end = self._trim_span(text, start + rel_start, start + rel_end)
                source_text = text[abs_start:abs_end]
                if not self._looks_translatable(source_text):
                    continue
                if self._is_command_only(source_text):
                    continue
                blocks.append(
                    self._block(
                        project_id,
                        blocks,
                        "latex_paragraph",
                        source_text,
                        abs_start,
                        abs_end,
                        {},
                        level=None,
                    )
                )

        blocks.sort(key=lambda block: int(block.metadata["start_offset"]))
        for order, block in enumerate(blocks):
            block.block_order = order
            block.metadata["marker"] = self._marker(order)
        return blocks

    def _block(
        self,
        project_id: str,
        blocks: list[DocumentBlock],
        block_type: str,
        source_text: str,
        start: int,
        end: int,
        extra_metadata: dict[str, Any],
        level: int | None,
    ) -> DocumentBlock:
        order = len(blocks)
        metadata = {
            "format": "latex",
            "translatable": True,
            "start_offset": start,
            "end_offset": end,
            "marker": self._marker(order),
        }
        metadata.update(extra_metadata)
        return DocumentBlock(
            id=f"{project_id}_latex_{order + 1:06d}",
            project_id=project_id,
            parent_id=None,
            block_order=order,
            block_type=block_type,
            level=level,
            source_text=source_text,
            metadata=metadata,
        )

    def _protected_ranges(self, text: str) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        ranges.extend(self._comment_ranges(text))
        for pattern in (
            r"\\\[[\s\S]*?\\\]",
            r"\\\([\s\S]*?\\\)",
            r"\$\$[\s\S]*?\$\$",
            r"(?<!\\)\$(?:\\.|[^$\\])+(?<!\\)\$",
        ):
            ranges.extend((match.start(), match.end()) for match in re.finditer(pattern, text))

        for env in self._protected_environments:
            escaped = re.escape(env)
            pattern = rf"\\begin\{{{escaped}\}}[\s\S]*?\\end\{{{escaped}\}}"
            ranges.extend((match.start(), match.end()) for match in re.finditer(pattern, text))
        return self._merge_ranges(ranges)

    def _comment_ranges(self, text: str) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        line_start = 0
        for line in text.splitlines(keepends=True):
            for index, char in enumerate(line):
                if char == "%" and not self._is_escaped(line, index):
                    ranges.append((line_start + index, line_start + len(line)))
                    break
            line_start += len(line)
        return ranges

    def _first_required_argument(self, text: str, start: int) -> tuple[int, int, int] | None:
        index = start
        while index < len(text) and text[index].isspace():
            index += 1
        while index < len(text) and text[index] == "[":
            close = self._matching_delimiter(text, index, "[", "]")
            if close is None:
                return None
            index = close + 1
            while index < len(text) and text[index].isspace():
                index += 1
        if index >= len(text) or text[index] != "{":
            return None
        close = self._matching_delimiter(text, index, "{", "}")
        if close is None:
            return None
        return index + 1, close, close + 1

    def _matching_delimiter(self, text: str, start: int, open_char: str, close_char: str) -> int | None:
        depth = 0
        index = start
        while index < len(text):
            char = text[index]
            if char == open_char and not self._is_escaped(text, index):
                depth += 1
            elif char == close_char and not self._is_escaped(text, index):
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return None

    def _paragraph_spans(self, segment: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        for match in re.finditer(r"\S(?:[\s\S]*?)(?=\r?\n\s*\r?\n|\Z)", segment):
            spans.append((match.start(), match.end()))
        return spans

    def _looks_translatable(self, text: str) -> bool:
        stripped = text.strip()
        if len(stripped) < 2:
            return False
        without_commands = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", stripped)
        return bool(re.search(r"[A-Za-z\u00C0-\uFFFF]", without_commands))

    def _is_command_only(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True
        plain = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?", "", stripped)
        plain = re.sub(r"[{}\\\s,.;:!?~&%$#_^*-]+", "", plain)
        return not plain

    def _heading_level(self, command: str) -> int | None:
        return {
            "title": 1,
            "chapter": 1,
            "section": 2,
            "subsection": 3,
            "subsubsection": 4,
            "paragraph": 5,
            "subparagraph": 6,
        }.get(command)

    def _marker(self, order: int) -> str:
        return f"__LT_LATEX_BLOCK_{order + 1:06d}__"

    def _marked_chunk_source(self, blocks: list[DocumentBlock]) -> str:
        return "\n\n".join(f"{block.metadata['marker']}\n{block.source_text}" for block in blocks)

    def _split_marked_translation(self, text: str | None) -> dict[str, str]:
        if not text:
            return {}
        matches = list(LATEX_BLOCK_MARKER_RE.finditer(text))
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
        latex_path = context.artifact_dir / f"translated{suffix}.tex"
        replacements = self._replacement_map(blocks, chunks, draft)
        latex_path.write_text(self._build_modified_latex(context.source_path, replacements), encoding="utf-8")
        paths = self.exporter.export(context.artifact_dir, self._markdown_chunks(blocks, chunks), reports, draft=draft)
        paths["latex"] = latex_path
        self._write_latex_review_note(paths["translated"], latex_path)
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

    def _build_modified_latex(self, source_path: Path, replacements: dict[tuple[int, int], str]) -> str:
        text = source_path.read_text(encoding="utf-8")
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
            issues.append({"type": "LATEX_NO_TRANSLATABLE_TEXT"})
        try:
            text = source_path.read_text(encoding="utf-8")
            if "\\begin{document}" in text and "\\end{document}" not in text:
                issues.append({"type": "LATEX_MISSING_END_DOCUMENT"})
        except (OSError, UnicodeDecodeError) as exc:
            issues.append({"type": "LATEX_SOURCE_UNREADABLE", "error": str(exc)})
        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type="LATEX_STRUCTURE",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )

    def _validate_artifact(self, project_id: str, source_path: Path, exported_path: Path) -> ValidationReport:
        issues: list[dict[str, Any]] = []
        try:
            original = source_path.read_text(encoding="utf-8")
            exported = exported_path.read_text(encoding="utf-8")
            if not exported.strip():
                issues.append({"type": "LATEX_EMPTY_ARTIFACT"})
            if self._environment_sequence(original) != self._environment_sequence(exported):
                issues.append({"type": "LATEX_ENVIRONMENT_SEQUENCE_CHANGED"})
        except (OSError, UnicodeDecodeError) as exc:
            issues.append({"type": "LATEX_ARTIFACT_ACCESS_ERROR", "error": str(exc)})
        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type="LATEX_ARTIFACT",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )

    def _environment_sequence(self, text: str) -> list[tuple[str, str]]:
        return [(match.group(1), match.group(2)) for match in re.finditer(r"\\(begin|end)\{([^}]+)\}", text)]

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

    def _write_latex_review_note(self, translated_md_path: Path, latex_path: Path) -> None:
        body = translated_md_path.read_text(encoding="utf-8")
        note = (
            "<!-- NOTE: This Markdown file contains translated LaTeX text spans only. "
            f"The complete structure-preserving LaTeX artifact is {latex_path.name}. -->\n\n"
        )
        translated_md_path.write_text(note + body, encoding="utf-8")

    def _write_ast_snapshot(self, snapshot_dir: Path, blocks: list[DocumentBlock]) -> None:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "ast.json").write_text(
            json.dumps([asdict(block) for block in blocks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _inside_ranges(self, position: int, ranges: list[tuple[int, int]]) -> bool:
        return any(start <= position < end for start, end in ranges)

    def _merge_ranges(self, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        merged: list[tuple[int, int]] = []
        for start, end in sorted(ranges):
            if start >= end:
                continue
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        return merged

    def _complement_ranges(self, length: int, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        result: list[tuple[int, int]] = []
        cursor = 0
        for start, end in ranges:
            if cursor < start:
                result.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < length:
            result.append((cursor, length))
        return result

    def _trim_span(self, text: str, start: int, end: int) -> tuple[int, int]:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        return start, end

    def _is_escaped(self, text: str, index: int) -> bool:
        slash_count = 0
        cursor = index - 1
        while cursor >= 0 and text[cursor] == "\\":
            slash_count += 1
            cursor -= 1
        return slash_count % 2 == 1

