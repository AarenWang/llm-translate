from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from uuid import uuid4

from ..chunking import ChunkingEngine
from ..domain import DocumentBlock, TranslationChunk, TranslationProject, ValidationReport
from ..exporter import IpynbExporter
from ..parser import IpynbParser
from .base import FormatContext


class IpynbFormatAdapter:
    format_name = "ipynb"

    def __init__(self, soft_input_tokens: int = 2200, max_input_tokens: int = 3000):
        self.parser = IpynbParser()
        self.chunker = ChunkingEngine(soft_input_tokens, max_input_tokens)
        self.exporter = IpynbExporter()

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".ipynb"

    def parse(self, project: TranslationProject, context: FormatContext) -> list[DocumentBlock]:
        notebook = json.loads(context.source_path.read_text(encoding="utf-8"))
        blocks = self.parser.parse(project.id, notebook)
        context.snapshot_dir.mkdir(parents=True, exist_ok=True)
        (context.snapshot_dir / "notebook.original.json").write_text(
            json.dumps(notebook, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (context.snapshot_dir / "notebook.cells.json").write_text(
            json.dumps([block.metadata for block in blocks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (context.snapshot_dir / "ast.json").write_text(
            json.dumps([asdict(block) for block in blocks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return blocks

    def plan_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        return self.chunker.build_chunks(project_id, blocks)

    def prompt_document_format(self) -> str:
        return self.format_name

    def chapter_path(self, chunk: TranslationChunk) -> str | None:
        return f"Jupyter Notebook markdown cell / {chunk.chapter_id or chunk.id}"

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> tuple[dict[str, Path], list[ValidationReport], bool]:
        original_notebook = self._load_original_notebook(context.snapshot_dir)
        reports = [
            report
            for report in reports
            if report.check_type not in {"NOTEBOOK_STRUCTURE", "NOTEBOOK_ARTIFACT"}
        ]
        pre_export_report = self._validate_notebook_blocks(project.id, original_notebook, blocks)
        reports.append(pre_export_report)
        if pre_export_report.status == "FAIL":
            draft = True

        paths = self.exporter.export(
            context.artifact_dir,
            original_notebook,
            blocks,
            chunks,
            reports,
            draft=draft,
        )
        exported_notebook = json.loads(paths["ipynb"].read_text(encoding="utf-8"))
        artifact_report = self._validate_notebook_artifact(
            project.id,
            original_notebook,
            exported_notebook,
        )
        reports.append(artifact_report)
        if artifact_report.status == "FAIL":
            draft = True
        paths = self.exporter.export(
            context.artifact_dir,
            original_notebook,
            blocks,
            chunks,
            reports,
            draft=draft,
        )
        return paths, reports, draft

    def _load_original_notebook(self, snapshot_dir: Path) -> dict:
        snapshot = snapshot_dir / "notebook.original.json"
        return json.loads(snapshot.read_text(encoding="utf-8"))

    def _validate_notebook_blocks(
        self,
        project_id: str,
        original_notebook: dict,
        blocks: list[DocumentBlock],
    ) -> ValidationReport:
        issues: list[dict] = []
        cells = original_notebook.get("cells")
        if not isinstance(cells, list):
            issues.append({"type": "NOTEBOOK_CELLS_NOT_LIST"})
        elif len(cells) != len(blocks):
            issues.append(
                {
                    "type": "NOTEBOOK_CELL_COUNT_CHANGED",
                    "expected": len(cells),
                    "actual": len(blocks),
                }
            )
        else:
            for block in blocks:
                cell_index = block.metadata.get("cell_index")
                if not isinstance(cell_index, int) or cell_index >= len(cells):
                    issues.append({"type": "INVALID_CELL_INDEX", "block_id": block.id})
                    continue
                expected_type = cells[cell_index].get("cell_type", "raw")
                if block.metadata.get("cell_type") != expected_type:
                    issues.append(
                        {
                            "type": "NOTEBOOK_CELL_TYPE_CHANGED",
                            "cell_index": cell_index,
                            "expected": expected_type,
                            "actual": block.metadata.get("cell_type"),
                        }
                    )

        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type="NOTEBOOK_STRUCTURE",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )

    def _validate_notebook_artifact(
        self,
        project_id: str,
        original_notebook: dict,
        exported_notebook: dict,
    ) -> ValidationReport:
        issues: list[dict] = []
        original_cells = original_notebook.get("cells")
        exported_cells = exported_notebook.get("cells")

        for key in ("nbformat", "nbformat_minor", "metadata"):
            if exported_notebook.get(key) != original_notebook.get(key):
                issues.append({"type": "NOTEBOOK_TOP_LEVEL_CHANGED", "field": key})

        if not isinstance(original_cells, list) or not isinstance(exported_cells, list):
            issues.append({"type": "NOTEBOOK_CELLS_NOT_LIST"})
        elif len(original_cells) != len(exported_cells):
            issues.append(
                {
                    "type": "NOTEBOOK_CELL_COUNT_CHANGED",
                    "expected": len(original_cells),
                    "actual": len(exported_cells),
                }
            )
        else:
            for index, (original_cell, exported_cell) in enumerate(zip(original_cells, exported_cells)):
                if exported_cell.get("cell_type") != original_cell.get("cell_type"):
                    issues.append({"type": "NOTEBOOK_CELL_TYPE_CHANGED", "cell_index": index})
                    continue
                for field in ("id", "metadata", "attachments"):
                    if exported_cell.get(field) != original_cell.get(field):
                        issues.append(
                            {
                                "type": "NOTEBOOK_CELL_FIELD_CHANGED",
                                "cell_index": index,
                                "field": field,
                            }
                        )
                if original_cell.get("cell_type") != "markdown":
                    for field in ("source", "outputs", "execution_count"):
                        if exported_cell.get(field) != original_cell.get(field):
                            issues.append(
                                {
                                    "type": "NOTEBOOK_NON_MARKDOWN_CELL_CHANGED",
                                    "cell_index": index,
                                    "field": field,
                                }
                            )

        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type="NOTEBOOK_ARTIFACT",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )
