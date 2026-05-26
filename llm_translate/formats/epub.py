from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from uuid import uuid4
import warnings
import zipfile
import logging

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from ..domain import ChunkStatus, DocumentBlock, TranslationChunk, TranslationProject, ValidationReport
from ..exporter import MarkdownExporter
from ..parser.epub import EpubParser
from .base import FormatContext


logger = logging.getLogger(__name__)

# Default token limits for chunking
DEFAULT_SOFT_TOKEN_LIMIT = 2200
DEFAULT_MAX_TOKEN_LIMIT = 3000


class EpubFormatAdapter:
    """Format adapter for EPUB files.

    This adapter handles parsing, translation, and export of EPUB files while
    preserving the original structure, formatting, and non-translatable content.
    """

    format_name = "epub"

    def __init__(self, soft_input_tokens: int = DEFAULT_SOFT_TOKEN_LIMIT, max_input_tokens: int = DEFAULT_MAX_TOKEN_LIMIT):
        self.parser = EpubParser()
        self.markdown_exporter = MarkdownExporter()

    def supports(self, path: Path) -> bool:
        """Check if the format adapter supports the given file.

        Args:
            path: Path to the file to check

        Returns:
            True if the file is an EPUB file
        """
        return path.suffix.lower() == ".epub"

    def parse(self, project: TranslationProject, context: FormatContext) -> list[DocumentBlock]:
        """Parse EPUB file and extract translatable document blocks.

        Args:
            project: Translation project configuration
            context: Format context containing source path and snapshot directory

        Returns:
            List of DocumentBlock objects containing translatable content
        """
        result = self.parser.parse(project.id, context.source_path)
        context.snapshot_dir.mkdir(parents=True, exist_ok=True)
        (context.snapshot_dir / "epub.json").write_text(
            json.dumps(result.to_snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (context.snapshot_dir / "ast.json").write_text(
            json.dumps([asdict(block) for block in result.blocks], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return result.blocks

    def plan_chunks(self, project_id: str, blocks: list[DocumentBlock]) -> list[TranslationChunk]:
        """Plan translation chunks from document blocks.

        Each translatable block becomes a separate chunk to maintain
        fine-grained control over translation and preservation.

        Args:
            project_id: Translation project identifier
            blocks: List of document blocks to convert to chunks

        Returns:
            List of TranslationChunk objects for translation
        """
        chunks: list[TranslationChunk] = []
        for block in blocks:
            if not block.metadata.get("translatable"):
                continue
            chunk_order = len(chunks)
            chunks.append(
                TranslationChunk(
                    id=f"{project_id}_c_{chunk_order + 1:06d}",
                    project_id=project_id,
                    chapter_id=block.metadata.get("href"),
                    chunk_order=chunk_order,
                    block_ids=[block.id],
                    source_text=block.source_text,
                    metadata={
                        "format": "epub",
                        "block_id": block.id,
                        "href": block.metadata.get("href"),
                        "file_name": block.metadata.get("file_name"),
                        "spine_index": block.metadata.get("spine_index"),
                        "is_nav": block.metadata.get("is_nav", False),
                        "text_node_index": block.metadata.get("text_node_index"),
                        "tag": block.metadata.get("tag"),
                    },
                )
            )
        return chunks

    def prompt_document_format(self) -> str:
        return self.format_name

    def chapter_path(self, chunk: TranslationChunk) -> str | None:
        href = chunk.metadata.get("href") or chunk.chapter_id
        if href is None:
            return None
        if chunk.metadata.get("is_nav"):
            return f"EPUB navigation / {href}"
        return f"EPUB XHTML text node / {href}"

    def export(
        self,
        project: TranslationProject,
        context: FormatContext,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        reports: list[ValidationReport],
        draft: bool,
    ) -> tuple[dict[str, Path], list[ValidationReport], bool]:
        """Export translated EPUB file with validation.

        Performs structure validation, creates translated EPUB, validates the artifact,
        and falls back to draft mode if validation fails.

        Args:
            project: Translation project configuration
            context: Format context with paths
            blocks: Original document blocks
            chunks: Translated chunks
            reports: Existing validation reports
            draft: Whether to create a draft version

        Returns:
            Tuple of (artifact_paths, validation_reports, is_draft_flag)
        """
        reports = [
            report
            for report in reports
            if report.check_type not in {"EPUB_STRUCTURE", "EPUB_ARTIFACT"}
        ]
        structure_report = self._validate_structure(project.id, context.source_path, blocks)
        reports.append(structure_report)
        if structure_report.status == "FAIL":
            draft = True

        paths = self._write_artifacts(context, blocks, chunks, reports, draft=draft)
        artifact_report = self._validate_artifact(project.id, context.source_path, paths["epub"])
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
        epub_path = context.artifact_dir / f"translated{suffix}.epub"
        replacements = self._replacement_map(blocks, chunks, draft=draft)
        modified_files = self._build_modified_documents(context.source_path, replacements)
        self._copy_epub_with_replacements(context.source_path, epub_path, modified_files)
        paths = self.markdown_exporter.export(context.artifact_dir, chunks, reports, draft=draft)
        paths["epub"] = epub_path
        self._write_epub_review_note(paths["translated"], epub_path)
        return paths

    def _replacement_map(
        self,
        blocks: list[DocumentBlock],
        chunks: list[TranslationChunk],
        draft: bool,
    ) -> dict[str, dict[int, str]]:
        chunks_by_block = {chunk.block_ids[0]: chunk for chunk in chunks if chunk.block_ids}
        replacements: dict[str, dict[int, str]] = {}
        for block in blocks:
            file_name = block.metadata.get("file_name")
            text_node_index = block.metadata.get("text_node_index")
            if file_name is None or text_node_index is None:
                continue
            chunk = chunks_by_block.get(block.id)
            if chunk is None:
                continue
            if chunk.restored_text:
                text = chunk.restored_text.strip()
            elif draft:
                text = block.source_text
            else:
                continue
            text = f"{block.metadata.get('prefix', '')}{text}{block.metadata.get('suffix', '')}"
            replacements.setdefault(file_name, {})[int(text_node_index)] = text
        return replacements

    def _build_modified_documents(
        self,
        source_path: Path,
        replacements: dict[str, dict[int, str]],
    ) -> dict[str, bytes]:
        """Build modified EPUB document contents with translations applied.

        Args:
            source_path: Path to the source EPUB file
            replacements: Dictionary mapping file names to node index replacements

        Returns:
            Dictionary of file names to modified content bytes
        """
        modified: dict[str, bytes] = {}
        with zipfile.ZipFile(source_path, "r") as archive:
            for file_name, node_replacements in replacements.items():
                raw = archive.read(file_name)
                soup = self.parser.parse_html_safely(raw)
                nodes = self.parser._iter_translatable_text_nodes(soup)
                for text_node_index, replacement in node_replacements.items():
                    if 0 <= text_node_index < len(nodes):
                        nodes[text_node_index].replace_with(replacement)
                modified[file_name] = soup.encode(formatter="minimal")
        return modified

    def _copy_epub_with_replacements(
        self,
        source_path: Path,
        target_path: Path,
        modified_files: dict[str, bytes],
    ) -> None:
        with zipfile.ZipFile(source_path, "r") as source:
            infos = source.infolist()
            with zipfile.ZipFile(target_path, "w") as target:
                mimetype_info = next((info for info in infos if info.filename == "mimetype"), None)
                if mimetype_info is not None:
                    target.writestr(
                        zipfile.ZipInfo("mimetype"),
                        source.read(mimetype_info),
                        compress_type=zipfile.ZIP_STORED,
                    )
                for info in infos:
                    if info.filename == "mimetype":
                        continue
                    data = modified_files.get(info.filename)
                    if data is None:
                        data = source.read(info)
                    target_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    target_info.comment = info.comment
                    target_info.extra = info.extra
                    target_info.internal_attr = info.internal_attr
                    target_info.external_attr = info.external_attr
                    target.writestr(target_info, data, compress_type=info.compress_type)

    def _validate_structure(
        self,
        project_id: str,
        source_path: Path,
        blocks: list[DocumentBlock],
    ) -> ValidationReport:
        """Validate the structure and integrity of the source EPUB file.

        Args:
            project_id: Translation project identifier
            source_path: Path to the source EPUB file
            blocks: Parsed document blocks

        Returns:
            ValidationReport with structure check results
        """
        issues: list[dict] = []
        if not blocks:
            issues.append({"type": "EPUB_NO_TRANSLATABLE_TEXT"})
        try:
            with zipfile.ZipFile(source_path, "r") as archive:
                names = set(archive.namelist())
                if archive.read("mimetype").decode("utf-8", errors="replace").strip() != "application/epub+zip":
                    issues.append({"type": "EPUB_BAD_MIMETYPE"})
                if "META-INF/container.xml" not in names:
                    issues.append({"type": "EPUB_MISSING_CONTAINER"})
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            logger.error(f"Invalid EPUB file: {exc}")
            issues.append({"type": "EPUB_UNREADABLE_ZIP", "error": str(exc)})
        except (OSError, IOError) as exc:
            logger.error(f"File access error: {exc}")
            issues.append({"type": "EPUB_FILE_ACCESS_ERROR", "error": str(exc)})
        except UnicodeDecodeError as exc:
            logger.error(f"Encoding error in EPUB: {exc}")
            issues.append({"type": "EPUB_ENCODING_ERROR", "error": str(exc)})

        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type="EPUB_STRUCTURE",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )

    def _validate_artifact(
        self,
        project_id: str,
        original_path: Path,
        exported_path: Path,
    ) -> ValidationReport:
        """Validate the exported EPUB file against the original.

        Checks that file structure, links, images, and protected content
        are preserved during translation.

        Args:
            project_id: Translation project identifier
            original_path: Path to the original EPUB file
            exported_path: Path to the exported translated EPUB file

        Returns:
            ValidationReport with artifact validation results
        """
        issues: list[dict] = []
        try:
            with zipfile.ZipFile(original_path, "r") as original, zipfile.ZipFile(exported_path, "r") as exported:
                original_names = original.namelist()
                exported_names = exported.namelist()
                if original_names != exported_names:
                    issues.append({"type": "EPUB_FILE_LIST_CHANGED"})
                if exported_names and exported_names[0] != "mimetype":
                    issues.append({"type": "EPUB_MIMETYPE_NOT_FIRST"})
                if exported.read("mimetype").decode("utf-8", errors="replace").strip() != "application/epub+zip":
                    issues.append({"type": "EPUB_BAD_MIMETYPE"})
                for name in original_names:
                    if not name.lower().endswith((".xhtml", ".html", ".htm")):
                        continue
                    if name not in exported_names:
                        continue
                    original_soup = self.parser.parse_html_safely(original.read(name))
                    exported_soup = self.parser.parse_html_safely(exported.read(name))
                    if self._attrs(original_soup, "a", "href") != self._attrs(exported_soup, "a", "href"):
                        issues.append({"type": "EPUB_HREF_CHANGED", "file": name})
                    if self._attrs(original_soup, "img", "src") != self._attrs(exported_soup, "img", "src"):
                        issues.append({"type": "EPUB_SRC_CHANGED", "file": name})
                    if self._protected_texts(original_soup) != self._protected_texts(exported_soup):
                        issues.append({"type": "EPUB_PROTECTED_TEXT_CHANGED", "file": name})
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            logger.error(f"Invalid EPUB artifact: {exc}")
            issues.append({"type": "EPUB_ARTIFACT_UNREADABLE", "error": str(exc)})
        except (OSError, IOError) as exc:
            logger.error(f"Artifact file access error: {exc}")
            issues.append({"type": "EPUB_ARTIFACT_ACCESS_ERROR", "error": str(exc)})
        except UnicodeDecodeError as exc:
            logger.error(f"Artifact encoding error: {exc}")
            issues.append({"type": "EPUB_ARTIFACT_ENCODING_ERROR", "error": str(exc)})

        return ValidationReport(
            id=f"vr_{uuid4().hex}",
            project_id=project_id,
            chunk_id=None,
            check_type="EPUB_ARTIFACT",
            status="PASS" if not issues else "FAIL",
            issues=issues,
        )

    def _attrs(self, soup: BeautifulSoup, tag: str, attr: str) -> list[str | None]:
        return [node.get(attr) for node in soup.find_all(tag)]

    def _protected_texts(self, soup: BeautifulSoup) -> list[str]:
        """Extract text content from protected elements (code, scripts, etc.).

        Args:
            soup: BeautifulSoup object to extract from

        Returns:
            List of text content from protected elements
        """
        texts: list[str] = []
        for tag_name in ("code", "pre", "kbd", "samp", "script", "style"):
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

    def _write_epub_review_note(self, translated_md_path: Path, epub_path: Path) -> None:
        body = translated_md_path.read_text(encoding="utf-8")
        note = (
            "<!-- NOTE: This Markdown file contains translated EPUB text nodes only. "
            f"The complete translated book is {epub_path.name}. -->\n\n"
        )
        translated_md_path.write_text(note + body, encoding="utf-8")
