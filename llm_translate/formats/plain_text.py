from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from ..chunking import ChunkingEngine
from ..domain import DocumentBlock, TranslationChunk, TranslationProject, ValidationReport
from ..exporter import MarkdownExporter
from .base import FormatContext


class PlainTextFormatAdapter:
    format_name = "plain_text"

    def __init__(self, soft_input_tokens: int = 2200, max_input_tokens: int = 3000):
        self.chunker = ChunkingEngine(soft_input_tokens, max_input_tokens)
        self.exporter = MarkdownExporter()

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in {".txt", ".text"}

    def parse(self, project: TranslationProject, context: FormatContext) -> list[DocumentBlock]:
        text = context.source_path.read_text(encoding="utf-8")
        blocks = self._parse_paragraphs(project.id, text)
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
        paths = self.exporter.export(context.artifact_dir, chunks, reports, draft=draft)
        txt_path = self._write_translated_text(context.artifact_dir, chunks, draft=draft)
        paths["text"] = txt_path
        return paths, reports, draft

    def _parse_paragraphs(self, project_id: str, text: str) -> list[DocumentBlock]:
        blocks: list[DocumentBlock] = []
        pending: list[str] = []

        def flush() -> None:
            if not pending:
                return
            paragraph = "\n".join(pending).strip()
            pending.clear()
            if not paragraph:
                return
            block_order = len(blocks)
            blocks.append(
                DocumentBlock(
                    id=f"{project_id}_p_{block_order + 1:06d}",
                    project_id=project_id,
                    parent_id=None,
                    block_order=block_order,
                    block_type="plain_paragraph",
                    level=None,
                    source_text=paragraph,
                    metadata={"format": "plain_text", "translatable": True},
                )
            )

        for line in text.splitlines():
            if line.strip():
                pending.append(line.rstrip())
            else:
                flush()
        flush()
        return blocks

    def _write_translated_text(
        self,
        artifact_dir: Path,
        chunks: list[TranslationChunk],
        draft: bool,
    ) -> Path:
        suffix = ".draft" if draft else ""
        txt_path = artifact_dir / f"translated{suffix}.txt"
        parts: list[str] = []
        for chunk in chunks:
            text = chunk.restored_text
            if not text:
                text = f"[{chunk.id} {chunk.status.value}]" if draft else ""
            if text:
                parts.append(text.strip())
        txt_path.write_text("\n\n".join(parts).strip() + "\n", encoding="utf-8")
        return txt_path

    def _write_ast_snapshot(self, snapshot_dir: Path, blocks: list[DocumentBlock]) -> None:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "ast.json").write_text(
            json.dumps([asdict(block) for block in blocks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
