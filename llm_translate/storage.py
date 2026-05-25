from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, case, create_engine, event, func, select
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.pool import NullPool

from .domain import (
    ChunkStatus,
    DocumentBlock,
    GlossaryTerm,
    ProjectStatus,
    ProtectedSpan,
    TranslationChunk,
    TranslationProject,
    ValidationReport,
)


Base = declarative_base()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    return json.loads(value)


class TranslationProjectRow(Base):
    __tablename__ = "translation_project"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    source_file_name = Column(String, nullable=False)
    source_language = Column(String)
    target_language = Column(String, nullable=False)
    input_format = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    style_guide_id = Column(String)
    glossary_id = Column(String)
    prompt_version = Column(String, nullable=False)
    protection_policy_version = Column(String, nullable=False)
    created_at = Column(String, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(String, server_default=func.current_timestamp(), nullable=False)


class DocumentBlockRow(Base):
    __tablename__ = "document_block"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("translation_project.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String)
    block_order = Column(Integer, nullable=False)
    block_type = Column(String, nullable=False)
    level = Column(Integer)
    source_text = Column(Text, nullable=False)
    target_text = Column(Text)
    metadata_json = Column("metadata", Text, nullable=False, default="{}")


class TranslationChunkRow(Base):
    __tablename__ = "translation_chunk"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("translation_project.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(String)
    chunk_order = Column(Integer, nullable=False)
    block_ids = Column(Text, nullable=False)
    source_text = Column(Text, nullable=False)
    protected_text = Column(Text)
    target_text = Column(Text)
    restored_text = Column(Text)
    status = Column(String, nullable=False, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)
    model_name = Column(String)
    prompt_version = Column(String, nullable=False)
    glossary_version = Column(String, nullable=False)
    style_guide_version = Column(String, nullable=False)
    protection_policy_version = Column(String, nullable=False)
    metadata_json = Column("metadata", Text, nullable=False, default="{}")
    created_at = Column(String, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(String, server_default=func.current_timestamp(), nullable=False)


class ProtectedSpanRow(Base):
    __tablename__ = "protected_span"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("translation_project.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String, ForeignKey("translation_chunk.id", ondelete="CASCADE"), nullable=False, index=True)
    placeholder = Column(String, nullable=False, index=True)
    span_type = Column(String, nullable=False)
    original_text = Column(Text, nullable=False)
    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)
    strategy = Column(String, nullable=False)


class GlossaryTermRow(Base):
    __tablename__ = "glossary_term"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("translation_project.id", ondelete="CASCADE"), nullable=False, index=True)
    source_term = Column(String, nullable=False, index=True)
    target_term = Column(String, nullable=False)
    case_sensitive = Column(Boolean, nullable=False, default=True)
    match_type = Column(String, nullable=False, default="exact")
    priority = Column(Integer, nullable=False, default=100)
    locked = Column(Boolean, nullable=False, default=False)
    note = Column(Text)
    version = Column(String, nullable=False, default="glossary-v1")


class ValidationReportRow(Base):
    __tablename__ = "validation_report"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("translation_project.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String, index=True)
    check_type = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    issues = Column(Text, nullable=False, default="[]")
    created_at = Column(String, server_default=func.current_timestamp(), nullable=False)


class TranslationAttemptRow(Base):
    __tablename__ = "translation_attempt"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String, ForeignKey("translation_project.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String, ForeignKey("translation_chunk.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String, nullable=False)
    model_name = Column(String, nullable=False)
    prompt_preview = Column(Text, nullable=False)
    response_preview = Column(Text)
    status = Column(String, nullable=False)
    error_message = Column(Text)
    created_at = Column(String, server_default=func.current_timestamp(), nullable=False)


class SQLiteStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db_path = self.path.resolve().as_posix()
        self.engine = create_engine(f"sqlite:///{db_path}", future=True, poolclass=NullPool)

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode = MEMORY")
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.engine.begin() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(translation_chunk)")}
            if "metadata" not in columns:
                conn.exec_driver_sql("ALTER TABLE translation_chunk ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")

    def create_project(self, project: TranslationProject) -> None:
        with Session(self.engine) as session:
            session.add(project_to_row(project))
            session.commit()

    def update_project_status(self, project_id: str, status: ProjectStatus) -> None:
        with Session(self.engine) as session:
            row = session.get(TranslationProjectRow, project_id)
            if row is None:
                raise KeyError(f"project not found: {project_id}")
            row.status = status.value
            row.updated_at = _current_timestamp_sqlite(session)
            session.commit()

    def get_project(self, project_id: str) -> TranslationProject:
        with Session(self.engine) as session:
            row = session.get(TranslationProjectRow, project_id)
            if row is None:
                raise KeyError(f"project not found: {project_id}")
            return project_from_row(row)

    def list_projects(self) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            done_count = func.sum(case((TranslationChunkRow.status == "DONE", 1), else_=0))
            failed_count = func.sum(
                case((TranslationChunkRow.status.in_(("FAILED", "NEED_REVIEW")), 1), else_=0)
            )
            rows = session.execute(
                select(
                    TranslationProjectRow,
                    func.count(TranslationChunkRow.id).label("total_chunks"),
                    done_count.label("done_chunks"),
                    failed_count.label("failed_chunks"),
                )
                .outerjoin(TranslationChunkRow, TranslationChunkRow.project_id == TranslationProjectRow.id)
                .group_by(TranslationProjectRow.id)
                .order_by(TranslationProjectRow.updated_at.desc())
            ).all()
        projects: list[dict[str, Any]] = []
        for project_row, total, done, failed in rows:
            project = project_from_row(project_row).__dict__
            project["status"] = project["status"].value
            project.update(
                {
                    "total_chunks": total or 0,
                    "done_chunks": done or 0,
                    "failed_chunks": failed or 0,
                }
            )
            return_shape = {
                "id": project["id"],
                "name": project["name"],
                "source_file_name": project["source_file_name"],
                "target_language": project["target_language"],
                "status": project["status"],
                "created_at": project["created_at"],
                "updated_at": project["updated_at"],
                "total_chunks": project["total_chunks"],
                "done_chunks": project["done_chunks"],
                "failed_chunks": project["failed_chunks"],
            }
            projects.append(return_shape)
        return projects

    def replace_blocks(self, project_id: str, blocks: Iterable[DocumentBlock]) -> None:
        with Session(self.engine) as session:
            session.query(DocumentBlockRow).filter(DocumentBlockRow.project_id == project_id).delete()
            session.add_all(block_to_row(block) for block in blocks)
            session.commit()

    def list_blocks(self, project_id: str) -> list[DocumentBlock]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(DocumentBlockRow)
                    .where(DocumentBlockRow.project_id == project_id)
                    .order_by(DocumentBlockRow.block_order)
                )
                .scalars()
                .all()
            )
            return [block_from_row(row) for row in rows]

    def replace_chunks(self, project_id: str, chunks: Iterable[TranslationChunk]) -> None:
        with Session(self.engine) as session:
            session.query(TranslationChunkRow).filter(TranslationChunkRow.project_id == project_id).delete()
            session.add_all(chunk_to_row(chunk) for chunk in chunks)
            session.commit()

    def upsert_chunk(self, chunk: TranslationChunk) -> None:
        with Session(self.engine) as session:
            row = session.get(TranslationChunkRow, chunk.id)
            if row is None:
                session.add(chunk_to_row(chunk))
            else:
                row.chapter_id = chunk.chapter_id
                row.chunk_order = chunk.chunk_order
                row.block_ids = dumps(chunk.block_ids)
                row.source_text = chunk.source_text
                row.protected_text = chunk.protected_text
                row.target_text = chunk.target_text
                row.restored_text = chunk.restored_text
                row.status = chunk.status.value
                row.retry_count = chunk.retry_count
                row.error_message = chunk.error_message
                row.model_name = chunk.model_name
                row.prompt_version = chunk.prompt_version
                row.glossary_version = chunk.glossary_version
                row.style_guide_version = chunk.style_guide_version
                row.protection_policy_version = chunk.protection_policy_version
                row.metadata_json = dumps(chunk.metadata)
                row.updated_at = _current_timestamp_sqlite(session)
            session.commit()

    def list_chunks(
        self,
        project_id: str,
        statuses: set[ChunkStatus] | None = None,
    ) -> list[TranslationChunk]:
        with Session(self.engine) as session:
            statement = select(TranslationChunkRow).where(TranslationChunkRow.project_id == project_id)
            if statuses:
                statement = statement.where(TranslationChunkRow.status.in_([status.value for status in statuses]))
            rows = session.execute(statement.order_by(TranslationChunkRow.chunk_order)).scalars().all()
            return [chunk_from_row(row) for row in rows]

    def replace_spans(self, chunk_id: str, spans: Iterable[ProtectedSpan]) -> None:
        with Session(self.engine) as session:
            session.query(ProtectedSpanRow).filter(ProtectedSpanRow.chunk_id == chunk_id).delete()
            session.add_all(span_to_row(span) for span in spans)
            session.commit()

    def list_spans(self, chunk_id: str) -> list[ProtectedSpan]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(ProtectedSpanRow)
                    .where(ProtectedSpanRow.chunk_id == chunk_id)
                    .order_by(ProtectedSpanRow.start_offset)
                )
                .scalars()
                .all()
            )
            return [span_from_row(row) for row in rows]

    def add_glossary_terms(self, terms: Iterable[GlossaryTerm]) -> None:
        with Session(self.engine) as session:
            session.add_all(term_to_row(term) for term in terms)
            session.commit()

    def list_glossary_terms(self, project_id: str) -> list[GlossaryTerm]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(GlossaryTermRow)
                    .where(GlossaryTermRow.project_id == project_id)
                    .order_by(GlossaryTermRow.priority.desc(), GlossaryTermRow.source_term.asc())
                )
                .scalars()
                .all()
            )
            return [term_from_row(row) for row in rows]

    def add_validation_report(self, report: ValidationReport) -> None:
        with Session(self.engine) as session:
            session.add(report_to_row(report))
            session.commit()

    def list_validation_reports(self, project_id: str) -> list[ValidationReport]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(ValidationReportRow)
                    .where(ValidationReportRow.project_id == project_id)
                    .order_by(ValidationReportRow.created_at)
                )
                .scalars()
                .all()
            )
            return [report_from_row(row) for row in rows]

    def add_attempt(
        self,
        project_id: str,
        chunk_id: str,
        provider: str,
        model_name: str,
        prompt_preview: str,
        response_preview: str | None,
        status: str,
        error_message: str | None = None,
    ) -> None:
        with Session(self.engine) as session:
            session.add(
                TranslationAttemptRow(
                    project_id=project_id,
                    chunk_id=chunk_id,
                    provider=provider,
                    model_name=model_name,
                    prompt_preview=prompt_preview[:1000],
                    response_preview=response_preview[:1000] if response_preview else None,
                    status=status,
                    error_message=error_message,
                )
            )
            session.commit()


def _current_timestamp_sqlite(session: Session) -> str:
    return session.execute(select(func.current_timestamp())).scalar_one()


def project_to_row(project: TranslationProject) -> TranslationProjectRow:
    return TranslationProjectRow(
        id=project.id,
        name=project.name,
        source_file_name=project.source_file_name,
        source_language=project.source_language,
        target_language=project.target_language,
        input_format=project.input_format,
        status=project.status.value,
        style_guide_id=project.style_guide_id,
        glossary_id=project.glossary_id,
        prompt_version=project.prompt_version,
        protection_policy_version=project.protection_policy_version,
    )


def project_from_row(row: TranslationProjectRow) -> TranslationProject:
    return TranslationProject(
        id=row.id,
        name=row.name,
        source_file_name=row.source_file_name,
        source_language=row.source_language,
        target_language=row.target_language,
        input_format=row.input_format,
        status=ProjectStatus(row.status),
        style_guide_id=row.style_guide_id,
        glossary_id=row.glossary_id,
        prompt_version=row.prompt_version,
        protection_policy_version=row.protection_policy_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def block_to_row(block: DocumentBlock) -> DocumentBlockRow:
    return DocumentBlockRow(
        id=block.id,
        project_id=block.project_id,
        parent_id=block.parent_id,
        block_order=block.block_order,
        block_type=block.block_type,
        level=block.level,
        source_text=block.source_text,
        target_text=block.target_text,
        metadata_json=dumps(block.metadata),
    )


def block_from_row(row: DocumentBlockRow) -> DocumentBlock:
    return DocumentBlock(
        id=row.id,
        project_id=row.project_id,
        parent_id=row.parent_id,
        block_order=row.block_order,
        block_type=row.block_type,
        level=row.level,
        source_text=row.source_text,
        target_text=row.target_text,
        metadata=loads(row.metadata_json, {}),
    )


def chunk_to_row(chunk: TranslationChunk) -> TranslationChunkRow:
    return TranslationChunkRow(
        id=chunk.id,
        project_id=chunk.project_id,
        chapter_id=chunk.chapter_id,
        chunk_order=chunk.chunk_order,
        block_ids=dumps(chunk.block_ids),
        source_text=chunk.source_text,
        protected_text=chunk.protected_text,
        target_text=chunk.target_text,
        restored_text=chunk.restored_text,
        status=chunk.status.value,
        retry_count=chunk.retry_count,
        error_message=chunk.error_message,
        model_name=chunk.model_name,
        prompt_version=chunk.prompt_version,
        glossary_version=chunk.glossary_version,
        style_guide_version=chunk.style_guide_version,
        protection_policy_version=chunk.protection_policy_version,
        metadata_json=dumps(chunk.metadata),
    )


def chunk_from_row(row: TranslationChunkRow) -> TranslationChunk:
    return TranslationChunk(
        id=row.id,
        project_id=row.project_id,
        chapter_id=row.chapter_id,
        chunk_order=row.chunk_order,
        block_ids=loads(row.block_ids, []),
        source_text=row.source_text,
        protected_text=row.protected_text,
        target_text=row.target_text,
        restored_text=row.restored_text,
        status=ChunkStatus(row.status),
        retry_count=row.retry_count,
        error_message=row.error_message,
        model_name=row.model_name,
        prompt_version=row.prompt_version,
        glossary_version=row.glossary_version,
        style_guide_version=row.style_guide_version,
        protection_policy_version=row.protection_policy_version,
        metadata=loads(row.metadata_json, {}),
    )


def span_to_row(span: ProtectedSpan) -> ProtectedSpanRow:
    return ProtectedSpanRow(
        id=span.id,
        project_id=span.project_id,
        chunk_id=span.chunk_id,
        placeholder=span.placeholder,
        span_type=span.span_type,
        original_text=span.original_text,
        start_offset=span.start_offset,
        end_offset=span.end_offset,
        strategy=span.strategy,
    )


def span_from_row(row: ProtectedSpanRow) -> ProtectedSpan:
    return ProtectedSpan(
        id=row.id,
        project_id=row.project_id,
        chunk_id=row.chunk_id,
        placeholder=row.placeholder,
        span_type=row.span_type,
        original_text=row.original_text,
        start_offset=row.start_offset,
        end_offset=row.end_offset,
        strategy=row.strategy,
    )


def term_to_row(term: GlossaryTerm) -> GlossaryTermRow:
    return GlossaryTermRow(
        id=term.id,
        project_id=term.project_id,
        source_term=term.source_term,
        target_term=term.target_term,
        case_sensitive=term.case_sensitive,
        match_type=term.match_type,
        priority=term.priority,
        locked=term.locked,
        note=term.note,
        version=term.version,
    )


def term_from_row(row: GlossaryTermRow) -> GlossaryTerm:
    return GlossaryTerm(
        id=row.id,
        project_id=row.project_id,
        source_term=row.source_term,
        target_term=row.target_term,
        case_sensitive=bool(row.case_sensitive),
        match_type=row.match_type,
        priority=row.priority,
        locked=bool(row.locked),
        note=row.note,
        version=row.version,
    )


def report_to_row(report: ValidationReport) -> ValidationReportRow:
    return ValidationReportRow(
        id=report.id,
        project_id=report.project_id,
        chunk_id=report.chunk_id,
        check_type=report.check_type,
        status=report.status,
        issues=dumps(report.issues),
    )


def report_from_row(row: ValidationReportRow) -> ValidationReport:
    return ValidationReport(
        id=row.id,
        project_id=row.project_id,
        chunk_id=row.chunk_id,
        check_type=row.check_type,
        status=row.status,
        issues=loads(row.issues, []),
    )
