from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProjectStatus(StrEnum):
    CREATED = "CREATED"
    PARSED = "PARSED"
    READY = "READY"
    TRANSLATING = "TRANSLATING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    EXPORTED = "EXPORTED"


class ChunkStatus(StrEnum):
    PENDING = "PENDING"
    PROTECTED = "PROTECTED"
    TRANSLATING = "TRANSLATING"
    TRANSLATED = "TRANSLATED"
    VALIDATING = "VALIDATING"
    DONE = "DONE"
    FAILED = "FAILED"
    NEED_REVIEW = "NEED_REVIEW"
    SKIPPED = "SKIPPED"


@dataclass
class TranslationProject:
    id: str
    name: str
    source_file_name: str
    source_language: str | None
    target_language: str
    input_format: str
    status: ProjectStatus
    style_guide_id: str | None = None
    glossary_id: str | None = None
    prompt_version: str = "prompt-v1"
    protection_policy_version: str = "protection-v1"
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class DocumentBlock:
    id: str
    project_id: str
    parent_id: str | None
    block_order: int
    block_type: str
    level: int | None
    source_text: str
    target_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TranslationChunk:
    id: str
    project_id: str
    chapter_id: str | None
    chunk_order: int
    block_ids: list[str]
    source_text: str
    protected_text: str | None = None
    target_text: str | None = None
    restored_text: str | None = None
    status: ChunkStatus = ChunkStatus.PENDING
    retry_count: int = 0
    error_message: str | None = None
    model_name: str | None = None
    prompt_version: str = "prompt-v1"
    glossary_version: str = "glossary-v1"
    style_guide_version: str = "style-v1"
    protection_policy_version: str = "protection-v1"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProtectedSpan:
    id: str
    project_id: str
    chunk_id: str
    placeholder: str
    span_type: str
    original_text: str
    start_offset: int
    end_offset: int
    strategy: str = "restore"


@dataclass
class GlossaryTerm:
    id: str
    project_id: str
    source_term: str
    target_term: str
    case_sensitive: bool = True
    match_type: str = "exact"
    priority: int = 100
    locked: bool = False
    note: str | None = None
    version: str = "glossary-v1"


@dataclass
class ValidationReport:
    id: str
    project_id: str
    chunk_id: str | None
    check_type: str
    status: str
    issues: list[dict[str, Any]]
