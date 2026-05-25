from __future__ import annotations

from dataclasses import asdict
import csv
import json
from pathlib import Path
import shutil
from uuid import uuid4

from .config import DEFAULT_STYLE_GUIDE, Settings
from .domain import (
    ChunkStatus,
    GlossaryTerm,
    ProjectStatus,
    TranslationChunk,
    TranslationProject,
)
from .formats import FormatContext, FormatRegistry, default_format_registry
from .llm import LLMProvider
from .prompt import PromptBuilder
from .protection import ProtectionEngine
from .storage import SQLiteStore
from .validation import ValidationEngine


class TranslationService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = SQLiteStore(settings.database_path)
        self.formats: FormatRegistry = default_format_registry(
            settings.soft_input_tokens,
            settings.max_input_tokens,
        )
        self.protection = ProtectionEngine()
        self.prompt_builder = PromptBuilder()
        self.validator = ValidationEngine()

    def init_db(self) -> None:
        self.store.init_db()

    def create_project(
        self,
        source_path: Path,
        name: str,
        target_language: str | None = None,
    ) -> TranslationProject:
        self.init_db()
        project_id = f"prj_{uuid4().hex[:12]}"
        project_dir = self.project_dir(project_id)
        source_dir = project_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        destination = source_dir / source_path.name
        shutil.copyfile(source_path, destination)

        project = TranslationProject(
            id=project_id,
            name=name,
            source_file_name=source_path.name,
            source_language=None,
            target_language=target_language or self.settings.default_target_language,
            input_format=self.formats.detect_name(source_path),
            status=ProjectStatus.CREATED,
            prompt_version=self.settings.prompt_version,
            protection_policy_version=self.settings.protection_policy_version,
        )
        self.store.create_project(project)
        return project

    def parse_project(self, project_id: str) -> None:
        project = self.store.get_project(project_id)
        adapter = self.formats.get(project.input_format)
        context = self.format_context(project)
        context.snapshot_dir.mkdir(parents=True, exist_ok=True)
        blocks = adapter.parse(project, context)
        self.store.replace_blocks(project.id, blocks)
        self.store.update_project_status(project.id, ProjectStatus.PARSED)

    def prepare_project(self, project_id: str) -> None:
        blocks = self.store.list_blocks(project_id)
        if not blocks:
            raise ValueError("project has no parsed blocks; run parse first")
        project = self.store.get_project(project_id)
        adapter = self.formats.get(project.input_format)
        chunks = adapter.plan_chunks(project_id, blocks)
        self.store.replace_chunks(project_id, chunks)
        snapshot_dir = self.project_dir(project_id) / "snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "chunks.json").write_text(
            json.dumps([asdict(chunk) for chunk in chunks], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        self.store.update_project_status(project_id, ProjectStatus.READY)

    def import_glossary(self, project_id: str, glossary_path: Path) -> int:
        terms: list[GlossaryTerm] = []
        if glossary_path.suffix.lower() == ".json":
            data = json.loads(glossary_path.read_text(encoding="utf-8"))
            rows = data if isinstance(data, list) else data.get("terms", [])
        else:
            with glossary_path.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.DictReader(file))

        for row in rows:
            terms.append(
                GlossaryTerm(
                    id=f"gt_{uuid4().hex}",
                    project_id=project_id,
                    source_term=row["source_term"],
                    target_term=row["target_term"],
                    case_sensitive=str(row.get("case_sensitive", "true")).lower() != "false",
                    match_type=row.get("match_type", "exact"),
                    priority=int(row.get("priority", 100)),
                    locked=str(row.get("locked", "false")).lower() == "true",
                    note=row.get("note"),
                    version=row.get("version", self.settings.glossary_version),
                )
            )
        self.store.add_glossary_terms(terms)
        return len(terms)

    def translate_project(
        self,
        project_id: str,
        provider: LLMProvider,
        include_need_review: bool = False,
    ) -> None:
        project = self.store.get_project(project_id)
        statuses = {ChunkStatus.PENDING, ChunkStatus.FAILED}
        if include_need_review:
            statuses.add(ChunkStatus.NEED_REVIEW)
        chunks = self.store.list_chunks(project_id, statuses=statuses)
        terms = self.store.list_glossary_terms(project_id)
        self.store.update_project_status(project_id, ProjectStatus.TRANSLATING)

        for chunk in chunks:
            self._translate_chunk(project, chunk, provider, terms)

        remaining = self.store.list_chunks(project_id, statuses={ChunkStatus.PENDING, ChunkStatus.FAILED})
        if remaining:
            self.store.update_project_status(project_id, ProjectStatus.FAILED)
        else:
            self.store.update_project_status(project_id, ProjectStatus.COMPLETED)

    def export_project(self, project_id: str) -> dict[str, Path]:
        project = self.store.get_project(project_id)
        adapter = self.formats.get(project.input_format)
        chunks = self.store.list_chunks(project_id)
        reports = self.store.list_validation_reports(project_id)
        draft = any(chunk.status != ChunkStatus.DONE for chunk in chunks)
        blocks = self.store.list_blocks(project_id)
        paths, reports, draft = adapter.export(
            project,
            self.format_context(project),
            blocks,
            chunks,
            reports,
            draft,
        )
        self._replace_format_reports(project_id, reports)

        self.store.update_project_status(
            project_id,
            ProjectStatus.EXPORTED if not draft else self.store.get_project(project_id).status,
        )
        return paths

    def run(
        self,
        source_path: Path,
        name: str,
        provider: LLMProvider,
        target_language: str | None = None,
        glossary_path: Path | None = None,
    ) -> tuple[TranslationProject, dict[str, Path]]:
        project = self.create_project(source_path, name, target_language=target_language)
        if glossary_path:
            self.import_glossary(project.id, glossary_path)
        self.parse_project(project.id)
        self.prepare_project(project.id)
        self.translate_project(project.id, provider)
        return project, self.export_project(project.id)

    def _translate_chunk(
        self,
        project: TranslationProject,
        chunk: TranslationChunk,
        provider: LLMProvider,
        terms: list[GlossaryTerm],
    ) -> None:
        last_error: str | None = None
        for attempt in range(chunk.retry_count, self.settings.max_retry_count + 1):
            chunk.retry_count = attempt
            try:
                protected = self.protection.protect(project.id, chunk.id, chunk.source_text)
                chunk.protected_text = protected.protected_text
                chunk.status = ChunkStatus.PROTECTED
                self.store.upsert_chunk(chunk)
                self.store.replace_spans(chunk.id, protected.spans)

                prompt = self.prompt_builder.build(
                    chunk=chunk,
                    target_language=project.target_language,
                    glossary_terms=terms,
                    style_guide=DEFAULT_STYLE_GUIDE,
                    chapter_path=self.formats.get(project.input_format).chapter_path(chunk),
                    document_format=self.formats.get(project.input_format).prompt_document_format(),
                )
                chunk.status = ChunkStatus.TRANSLATING
                self.store.upsert_chunk(chunk)

                output = provider.translate(prompt)
                self.store.add_attempt(
                    project_id=project.id,
                    chunk_id=chunk.id,
                    provider=provider.name,
                    model_name=provider.model_name,
                    prompt_preview=prompt.user,
                    response_preview=output,
                    status="OK",
                )
                chunk.target_text = output
                chunk.model_name = provider.model_name
                chunk.status = ChunkStatus.TRANSLATED
                self.store.upsert_chunk(chunk)

                chunk.restored_text = self.protection.restore(output, protected.spans)
                chunk.status = ChunkStatus.VALIDATING
                self.store.upsert_chunk(chunk)

                report = self.validator.validate_chunk(chunk, terms)
                self.store.add_validation_report(report)
                if report.status == "PASS":
                    chunk.status = ChunkStatus.DONE
                    chunk.error_message = None
                    self.store.upsert_chunk(chunk)
                    return
                last_error = "; ".join(issue["type"] for issue in report.issues)
            except Exception as exc:
                last_error = str(exc)
                self.store.add_attempt(
                    project_id=project.id,
                    chunk_id=chunk.id,
                    provider=provider.name,
                    model_name=provider.model_name,
                    prompt_preview=chunk.protected_text or chunk.source_text,
                    response_preview=None,
                    status="ERROR",
                    error_message=last_error,
                )

        chunk.status = ChunkStatus.FAILED
        chunk.error_message = last_error or "translation failed"
        self.store.upsert_chunk(chunk)

    def source_path(self, project: TranslationProject) -> Path:
        return self.project_dir(project.id) / "source" / project.source_file_name

    def project_dir(self, project_id: str) -> Path:
        return self.settings.workspace_path / "projects" / project_id

    def artifact_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "artifacts"

    def format_context(self, project: TranslationProject) -> FormatContext:
        return FormatContext(
            project_dir=self.project_dir(project.id),
            artifact_dir=self.artifact_dir(project.id),
            source_path=self.source_path(project),
            snapshot_dir=self.project_dir(project.id) / "snapshots",
        )

    def _replace_format_reports(self, project_id: str, reports):
        existing = self.store.list_validation_reports(project_id)
        existing_ids = {report.id for report in existing}
        for report in reports:
            if report.id not in existing_ids:
                self.store.add_validation_report(report)
