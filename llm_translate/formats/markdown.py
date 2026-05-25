from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from ..chunking import ChunkingEngine
from ..domain import DocumentBlock, TranslationChunk, TranslationProject, ValidationReport
from ..exporter import MarkdownExporter
from ..parser import MarkdownParser
from .base import FormatContext


class MarkdownFormatAdapter:
    format_name = "markdown"

    def __init__(self, soft_input_tokens: int = 2200, max_input_tokens: int = 3000):
        self.parser = MarkdownParser()
        self.chunker = ChunkingEngine(soft_input_tokens, max_input_tokens)
        self.exporter = MarkdownExporter()

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in {".md", ".markdown"}

    def parse(self, project: TranslationProject, context: FormatContext) -> list[DocumentBlock]:
        blocks = self.parser.parse(project.id, context.source_path.read_text(encoding="utf-8"))
        self._write_ast_snapshot(context.snapshot_dir, blocks)
        return blocks

    def plan_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        return self.chunker.build_chunks(project_id, blocks)

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
        return self.exporter.export(context.artifact_dir, chunks, reports, draft=draft), reports, draft

    def _write_ast_snapshot(self, snapshot_dir: Path, blocks: list[DocumentBlock]) -> None:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "ast.json").write_text(
            json.dumps([asdict(block) for block in blocks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
