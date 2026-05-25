"""HTML format adapter."""

from __future__ import annotations

from dataclasses import replace
import json
import re
from uuid import uuid4
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from .base import FormatAdapter, FormatContext
from ..chunking import ChunkingEngine
from ..domain import (
    ChunkStatus,
    DocumentBlock,
    TranslationChunk,
    TranslationProject,
    ValidationReport,
)
from ..exporter import MarkdownExporter
from ..parser.html import HTMLParser

HTML_NODE_MARKER_RE = re.compile(r"__LT_HTML_NODE_(\d{6})__")


class HTMLFormatAdapter(FormatAdapter):
    """HTML document format adapter.

    This adapter implements HTML document parsing, chunking, prompt generation,
    and export functionality, seamlessly integrating with the existing translation system.
    """

    format_name = "html"

    def __init__(
        self,
        soft_input_tokens: int = 2200,
        max_input_tokens: int = 3000,
        include_comments: bool = False,
        include_tables: bool = True,
        favor_precision: bool = True,
    ):
        """Initialize HTML format adapter.

        Args:
            soft_input_tokens: Soft input token limit
            max_input_tokens: Maximum input token limit
            include_comments: Whether to include comment content
            include_tables: Whether to include table content
            favor_precision: Whether to prioritize precision
        """
        self.parser = HTMLParser(
            include_comments=include_comments,
            include_tables=include_tables,
            favor_precision=favor_precision,
        )
        self.chunker = ChunkingEngine(soft_input_tokens, max_input_tokens)
        self.exporter = MarkdownExporter()

    def supports(self, path: Path) -> bool:
        """Determine if file path supports HTML format.

        Args:
            path: File path

        Returns:
            True if HTML file, False otherwise
        """
        return path.suffix.lower() in [".html", ".htm"]

    def parse(
        self, project: TranslationProject, context: FormatContext
    ) -> list[DocumentBlock]:
        """Parse HTML document.

        Args:
            project: Translation project
            context: Format context

        Returns:
            List of DocumentBlocks
        """
        html_path = str(context.source_path)
        return self.parser.parse(project.id, html_path)

    def plan_chunks(
        self, project_id: str, blocks: list[DocumentBlock]
    ) -> list[TranslationChunk]:
        """Plan translation chunks.

        Args:
            project_id: Project ID
            blocks: List of DocumentBlocks

        Returns:
            List of TranslationChunks
        """
        if blocks and blocks[0].metadata.get("format") == "html":
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
                        metadata={
                            "format": "html",
                            "source": pending[0].metadata.get("source"),
                            "block_markers": [
                                {
                                    "block_id": block.id,
                                    "text_node_index": block.metadata.get("text_node_index"),
                                    "marker": self._marker_for_block(block),
                                    "tag": block.metadata.get("tag"),
                                }
                                for block in pending
                            ],
                        },
                    )
                )
                pending = []
                pending_tokens = 0

            for block in blocks:
                if not block.metadata.get("translatable", True):
                    continue
                if block.level is not None and block.level <= 2:
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

        return self.chunker.build_chunks(project_id, blocks)

    def prompt_document_format(self) -> str:
        """Generate document format prompt.

        Returns:
            Prompt string describing HTML document format
        """
        return "html"

    def chapter_path(self, chunk: TranslationChunk) -> str | None:
        """Get chapter path.

        Args:
            chunk: Translation chunk

        Returns:
            Chapter path, HTML format doesn't use chapters, returns None
        """
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
        """Export translation results.

        HTML documents export both the existing Markdown artifacts and a
        structure-preserving translated HTML artifact.

        Args:
            project: Translation project
            context: Format context
            blocks: List of DocumentBlocks
            chunks: List of TranslationChunks
            reports: List of validation reports
            draft: Whether to use draft mode

        Returns:
            Tuple of (output file path dictionary, validation report list, success flag)
        """
        if not (blocks and blocks[0].metadata.get("format") == "html"):
            return self.exporter.export(context.artifact_dir, chunks, reports, draft=draft), reports, draft

        reports = [
            report
            for report in reports
            if report.check_type not in {"HTML_STRUCTURE", "HTML_ARTIFACT"}
        ]
        structure_report = self._validate_structure(project.id, context.source_path, blocks)
        reports.append(structure_report)
        if structure_report.status == "FAIL":
            draft = True

        paths = self._write_artifacts(context, blocks, chunks, reports, draft=draft)
        artifact_report = self._validate_artifact(project.id, context.source_path, paths["html"])
        reports.append(artifact_report)
        if artifact_report.status == "FAIL":
            draft = True
            paths = self._write_artifacts(context, blocks, chunks, reports, draft=draft)
        else:
            self._write_reports(context.artifact_dir, reports)
        return paths, reports, draft

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
        html_path = context.artifact_dir / f"translated{suffix}.html"
        replacements = self._replacement_map(blocks, chunks, draft=draft)
        html_path.write_text(
            self._build_modified_html(context.source_path, replacements),
            encoding="utf-8",
        )
        paths = self.exporter.export(
            context.artifact_dir,
            self._markdown_chunks(blocks, chunks),
            reports,
            draft=draft,
        )
        paths["html"] = html_path
        self._write_html_review_note(paths["translated"], html_path)
        return paths

    def _replacement_map(
        self,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        draft: bool,
    ) -> dict[int, str]:
        blocks_by_id = {block.id: block for block in blocks}
        replacements: dict[int, str] = {}
        for chunk in chunks:
            translated_by_marker = (
                self._split_marked_translation(chunk.restored_text)
                if chunk.restored_text
                else {}
            )
            for block_id in chunk.block_ids:
                block = blocks_by_id.get(block_id)
                if block is None:
                    continue
                text_node_index = block.metadata.get("text_node_index")
                if text_node_index is None:
                    continue

                marker = self._marker_for_block(block)
                if marker in translated_by_marker:
                    text = translated_by_marker[marker].strip()
                elif chunk.restored_text and len(chunk.block_ids) == 1:
                    text = chunk.restored_text.strip()
                elif draft or chunk.status == ChunkStatus.SKIPPED:
                    text = block.source_text
                else:
                    continue

                text = f"{block.metadata.get('prefix', '')}{text}{block.metadata.get('suffix', '')}"
                replacements[int(text_node_index)] = text
        return replacements

    def _build_modified_html(self, source_path: Path, replacements: dict[int, str]) -> str:
        raw = source_path.read_text(encoding="utf-8")
        soup = self.parser.parse_html_safely(raw)
        nodes = self.parser._iter_translatable_text_nodes(soup)
        for text_node_index, replacement in replacements.items():
            if 0 <= text_node_index < len(nodes):
                nodes[text_node_index].replace_with(replacement)
        return soup.decode(formatter="minimal")

    def _validate_structure(
        self,
        project_id: str,
        source_path: Path,
        blocks: list[DocumentBlock],
    ) -> ValidationReport:
        issues: list[dict[str, Any]] = []
        if not blocks:
            issues.append({"type": "HTML_NO_TRANSLATABLE_TEXT"})
        try:
            soup = self.parser.parse_html_safely(source_path.read_text(encoding="utf-8"))
            if not soup.find(True):
                issues.append({"type": "HTML_EMPTY_DOM"})
        except (OSError, UnicodeDecodeError) as exc:
            issues.append({"type": "HTML_SOURCE_UNREADABLE", "error": str(exc)})

        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type="HTML_STRUCTURE",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )

    def _validate_artifact(
        self,
        project_id: str,
        original_path: Path,
        exported_path: Path,
    ) -> ValidationReport:
        issues: list[dict[str, Any]] = []
        try:
            original_soup = self.parser.parse_html_safely(original_path.read_text(encoding="utf-8"))
            exported_soup = self.parser.parse_html_safely(exported_path.read_text(encoding="utf-8"))
            if not exported_soup.find(True):
                issues.append({"type": "HTML_ARTIFACT_UNPARSEABLE"})
            for attr in ("href", "src", "id", "class"):
                if self._attrs(original_soup, attr) != self._attrs(exported_soup, attr):
                    issues.append({"type": f"HTML_{attr.upper()}_CHANGED"})
            if self._protected_texts(original_soup) != self._protected_texts(exported_soup):
                issues.append({"type": "HTML_PROTECTED_TEXT_CHANGED"})
            original_count = len(self.parser._iter_translatable_text_nodes(original_soup))
            exported_count = len(self.parser._iter_translatable_text_nodes(exported_soup))
            count_delta = abs(original_count - exported_count)
            tolerated_delta = max(3, int(original_count * 0.02))
            if count_delta > tolerated_delta:
                issues.append(
                    {
                        "type": "HTML_TEXT_NODE_COUNT_CHANGED",
                        "original": original_count,
                        "exported": exported_count,
                        "tolerance": tolerated_delta,
                    }
                )
        except (OSError, UnicodeDecodeError) as exc:
            issues.append({"type": "HTML_ARTIFACT_ACCESS_ERROR", "error": str(exc)})

        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type="HTML_ARTIFACT",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )

    def _attrs(self, soup: BeautifulSoup, attr: str) -> list[Any]:
        values: list[Any] = []
        for node in soup.find_all(True):
            if not node.has_attr(attr):
                continue
            value = node.get(attr)
            if isinstance(value, list):
                values.append(tuple(value))
            else:
                values.append(value)
        return values

    def _protected_texts(self, soup: BeautifulSoup) -> list[str]:
        texts: list[str] = []
        for tag_name in ("code", "math", "noscript", "pre", "script", "style", "svg"):
            texts.extend(node.get_text() for node in soup.find_all(tag_name))
        return texts

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

    def _write_html_review_note(self, translated_md_path: Path, html_path: Path) -> None:
        body = translated_md_path.read_text(encoding="utf-8")
        note = (
            "<!-- NOTE: This Markdown file contains translated HTML text nodes only. "
            f"The complete structure-preserving HTML artifact is {html_path.name}. -->\n\n"
        )
        translated_md_path.write_text(note + body, encoding="utf-8")

    def _marker_for_block(self, block: DocumentBlock) -> str:
        text_node_index = int(block.metadata.get("text_node_index", block.block_order))
        return f"__LT_HTML_NODE_{text_node_index + 1:06d}__"

    def _marked_chunk_source(self, blocks: list[DocumentBlock]) -> str:
        parts: list[str] = []
        for block in blocks:
            parts.append(f"{self._marker_for_block(block)}\n{block.source_text}")
        return "\n\n".join(parts)

    def _split_marked_translation(self, text: str | None) -> dict[str, str]:
        if not text:
            return {}
        matches = list(HTML_NODE_MARKER_RE.finditer(text))
        if not matches:
            return {}

        translated: dict[str, str] = {}
        for index, match in enumerate(matches):
            marker = match.group(0)
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            translated[marker] = text[start:end].strip()
        return translated

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
                marker = self._marker_for_block(block)
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
