from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..domain import DocumentBlock, TranslationChunk, TranslationProject, ValidationReport


@dataclass(frozen=True)
class FormatContext:
    project_dir: Path
    artifact_dir: Path
    source_path: Path
    snapshot_dir: Path


class FormatAdapter(Protocol):
    format_name: str

    def supports(self, path: Path) -> bool:
        ...

    def parse(self, project: TranslationProject, context: FormatContext) -> list[DocumentBlock]:
        ...

    def plan_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        ...

    def prompt_document_format(self) -> str:
        ...

    def chapter_path(self, chunk: TranslationChunk) -> str | None:
        ...

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> tuple[dict[str, Path], list[ValidationReport], bool]:
        ...
