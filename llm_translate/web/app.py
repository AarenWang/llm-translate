from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import json
import os
import sqlite3
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


MODULE_DIR = Path(__file__).resolve().parent
STATIC_DIR = MODULE_DIR / "static"


def create_app(root: Path | None = None) -> FastAPI:
    repository = ReadOnlyWorkspaceRepository(root or _default_root())
    app = FastAPI(title="llm-translate workspace dashboard", version="0.1.0")

    @app.get("/api/workspaces")
    def list_workspaces() -> dict[str, Any]:
        return {"workspaces": repository.list_workspaces()}

    @app.get("/api/workspaces/{workspace_name}")
    def get_workspace(workspace_name: str) -> dict[str, Any]:
        return repository.get_workspace(workspace_name)

    @app.get("/api/workspaces/{workspace_name}/projects")
    def list_projects(
        workspace_name: str,
        status: str | None = None,
        input_format: str | None = Query(default=None, alias="format"),
        q: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return repository.list_projects(
            workspace_name,
            status=status,
            input_format=input_format,
            q=q,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/workspaces/{workspace_name}/projects/{project_id}")
    def get_project(workspace_name: str, project_id: str) -> dict[str, Any]:
        return repository.get_project(workspace_name, project_id)

    @app.get("/api/workspaces/{workspace_name}/projects/{project_id}/chunks")
    def list_chunks(
        workspace_name: str,
        project_id: str,
        status: str | None = None,
        q: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return repository.list_chunks(
            workspace_name,
            project_id,
            status=status,
            q=q,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/workspaces/{workspace_name}/projects/{project_id}/chunks/{chunk_id}")
    def get_chunk(workspace_name: str, project_id: str, chunk_id: str) -> dict[str, Any]:
        return repository.get_chunk(workspace_name, project_id, chunk_id)

    @app.get("/api/workspaces/{workspace_name}/projects/{project_id}/validation-reports")
    def list_validation_reports(workspace_name: str, project_id: str) -> dict[str, Any]:
        return repository.list_validation_reports(workspace_name, project_id)

    @app.get("/api/workspaces/{workspace_name}/projects/{project_id}/artifacts")
    def list_artifacts(workspace_name: str, project_id: str) -> dict[str, Any]:
        return repository.list_artifacts(workspace_name, project_id)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


class ReadOnlyWorkspaceRepository:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def list_workspaces(self) -> list[dict[str, Any]]:
        workspaces: list[dict[str, Any]] = []
        for path in self._workspace_paths():
            workspaces.append(self._workspace_summary(path))
        return sorted(
            workspaces,
            key=lambda item: (item.get("latest_project_updated_at") or "", item["name"]),
            reverse=True,
        )

    def get_workspace(self, name: str) -> dict[str, Any]:
        path = self._workspace_by_name(name)
        summary = self._workspace_summary(path)
        summary["status_counts"] = self._status_counts(path)
        summary["format_counts"] = self._format_counts(path)
        summary["recent_projects"] = self.list_projects(name, limit=12, offset=0)["projects"]
        return summary

    def list_projects(
        self,
        workspace_name: str,
        status: str | None = None,
        input_format: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        workspace = self._workspace_by_name(workspace_name)
        self._require_database(workspace)
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("p.status = ?")
            params.append(status)
        if input_format:
            conditions.append("p.input_format = ?")
            params.append(input_format)
        if q:
            conditions.append("(p.id LIKE ? OR p.name LIKE ? OR p.source_file_name LIKE ?)")
            needle = f"%{q}%"
            params.extend([needle, needle, needle])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._connect(workspace) as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM translation_project p {where}", params).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT
                    p.*,
                    COUNT(c.id) AS total_chunks,
                    SUM(CASE WHEN c.status = 'DONE' THEN 1 ELSE 0 END) AS done_chunks,
                    SUM(CASE WHEN c.status IN ('FAILED', 'NEED_REVIEW') THEN 1 ELSE 0 END) AS failed_chunks,
                    SUM(CASE WHEN c.status = 'PENDING' THEN 1 ELSE 0 END) AS pending_chunks,
                    (
                        SELECT COUNT(*)
                        FROM validation_report vr
                        WHERE vr.project_id = p.id AND vr.status = 'FAIL'
                    ) AS failed_reports,
                    (
                        SELECT COUNT(*)
                        FROM document_block db
                        WHERE db.project_id = p.id
                    ) AS block_count,
                    (
                        SELECT COUNT(*)
                        FROM translation_attempt ta
                        WHERE ta.project_id = p.id
                    ) AS attempt_count
                FROM translation_project p
                LEFT JOIN translation_chunk c ON c.project_id = p.id
                {where}
                GROUP BY p.id
                ORDER BY p.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return {
            "workspace": self._workspace_public(workspace),
            "total": total,
            "limit": limit,
            "offset": offset,
            "projects": [self._project_row(row) for row in rows],
        }

    def get_project(self, workspace_name: str, project_id: str) -> dict[str, Any]:
        workspace = self._workspace_by_name(workspace_name)
        with self._connect(workspace) as conn:
            project = conn.execute(
                "SELECT * FROM translation_project WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project is None:
                raise HTTPException(status_code=404, detail="project not found")
            chunk_status = self._count_rows(
                conn,
                "SELECT status, COUNT(*) AS count FROM translation_chunk WHERE project_id = ? GROUP BY status",
                (project_id,),
            )
            block_types = self._count_rows(
                conn,
                "SELECT block_type, COUNT(*) AS count FROM document_block WHERE project_id = ? GROUP BY block_type",
                (project_id,),
                key="block_type",
            )
            report_status = self._count_rows(
                conn,
                "SELECT status, COUNT(*) AS count FROM validation_report WHERE project_id = ? GROUP BY status",
                (project_id,),
            )
            glossary_count = conn.execute(
                "SELECT COUNT(*) FROM glossary_term WHERE project_id = ?",
                (project_id,),
            ).fetchone()[0]
            attempt_status = self._count_rows(
                conn,
                "SELECT status, COUNT(*) AS count FROM translation_attempt WHERE project_id = ? GROUP BY status",
                (project_id,),
            )
        return {
            "workspace": self._workspace_public(workspace),
            "project": dict(project),
            "chunk_status_counts": chunk_status,
            "block_type_counts": block_types,
            "validation_status_counts": report_status,
            "attempt_status_counts": attempt_status,
            "glossary_count": glossary_count,
            "artifacts": self._artifact_entries(workspace, project_id),
        }

    def list_chunks(
        self,
        workspace_name: str,
        project_id: str,
        status: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        workspace = self._workspace_by_name(workspace_name)
        conditions = ["c.project_id = ?"]
        params: list[Any] = [project_id]
        if status:
            conditions.append("c.status = ?")
            params.append(status)
        if q:
            conditions.append("(c.id LIKE ? OR c.source_text LIKE ? OR c.restored_text LIKE ? OR c.error_message LIKE ?)")
            needle = f"%{q}%"
            params.extend([needle, needle, needle, needle])
        where = f"WHERE {' AND '.join(conditions)}"

        with self._connect(workspace) as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM translation_chunk c {where}", params).fetchone()[0]
            rows = conn.execute(
                f"""
                SELECT
                    c.id,
                    c.project_id,
                    c.chapter_id,
                    c.chunk_order,
                    c.block_ids,
                    c.status,
                    c.retry_count,
                    c.error_message,
                    c.model_name,
                    c.prompt_version,
                    c.glossary_version,
                    c.style_guide_version,
                    c.protection_policy_version,
                    c.metadata,
                    c.created_at,
                    c.updated_at,
                    LENGTH(c.source_text) AS source_chars,
                    LENGTH(COALESCE(c.protected_text, '')) AS protected_chars,
                    LENGTH(COALESCE(c.target_text, '')) AS target_chars,
                    LENGTH(COALESCE(c.restored_text, '')) AS restored_chars,
                    (
                        SELECT COUNT(*)
                        FROM validation_report vr
                        WHERE vr.project_id = c.project_id AND vr.chunk_id = c.id AND vr.status = 'FAIL'
                    ) AS failed_reports,
                    (
                        SELECT COUNT(*)
                        FROM translation_attempt ta
                        WHERE ta.chunk_id = c.id
                    ) AS attempt_count,
                    (
                        SELECT COUNT(*)
                        FROM protected_span ps
                        WHERE ps.chunk_id = c.id
                    ) AS protected_span_count
                FROM translation_chunk c
                {where}
                ORDER BY c.chunk_order
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return {
            "workspace": self._workspace_public(workspace),
            "project_id": project_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "chunks": [self._chunk_summary(row) for row in rows],
        }

    def get_chunk(self, workspace_name: str, project_id: str, chunk_id: str) -> dict[str, Any]:
        workspace = self._workspace_by_name(workspace_name)
        with self._connect(workspace) as conn:
            chunk = conn.execute(
                "SELECT * FROM translation_chunk WHERE project_id = ? AND id = ?",
                (project_id, chunk_id),
            ).fetchone()
            if chunk is None:
                raise HTTPException(status_code=404, detail="chunk not found")
            chunk_dict = dict(chunk)
            block_ids = _loads(chunk_dict.get("block_ids"), [])
            blocks = []
            if block_ids:
                placeholders = ",".join("?" for _ in block_ids)
                blocks = [
                    self._decode_json_columns(dict(row), ("metadata",))
                    for row in conn.execute(
                        f"SELECT * FROM document_block WHERE project_id = ? AND id IN ({placeholders}) ORDER BY block_order",
                        [project_id, *block_ids],
                    ).fetchall()
                ]
            reports = [
                self._decode_json_columns(dict(row), ("issues",))
                for row in conn.execute(
                    "SELECT * FROM validation_report WHERE project_id = ? AND chunk_id = ? ORDER BY created_at",
                    (project_id, chunk_id),
                ).fetchall()
            ]
            attempts = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM translation_attempt WHERE project_id = ? AND chunk_id = ? ORDER BY created_at DESC, id DESC",
                    (project_id, chunk_id),
                ).fetchall()
            ]
            spans = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM protected_span WHERE project_id = ? AND chunk_id = ? ORDER BY start_offset",
                    (project_id, chunk_id),
                ).fetchall()
            ]
        chunk_dict = self._decode_json_columns(chunk_dict, ("block_ids", "metadata"))
        return {
            "workspace": self._workspace_public(workspace),
            "project_id": project_id,
            "chunk": chunk_dict,
            "blocks": blocks,
            "validation_reports": reports,
            "attempts": attempts,
            "protected_spans": spans,
        }

    def list_validation_reports(self, workspace_name: str, project_id: str) -> dict[str, Any]:
        workspace = self._workspace_by_name(workspace_name)
        with self._connect(workspace) as conn:
            rows = conn.execute(
                "SELECT * FROM validation_report WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return {
            "workspace": self._workspace_public(workspace),
            "project_id": project_id,
            "reports": [self._decode_json_columns(dict(row), ("issues",)) for row in rows],
        }

    def list_artifacts(self, workspace_name: str, project_id: str) -> dict[str, Any]:
        workspace = self._workspace_by_name(workspace_name)
        return {
            "workspace": self._workspace_public(workspace),
            "project_id": project_id,
            "artifacts": self._artifact_entries(workspace, project_id),
        }

    def _workspace_paths(self) -> list[Path]:
        if not self.root.exists():
            return []
        return [
            path
            for path in self.root.iterdir()
            if path.is_dir() and path.name.startswith(".llm_translate")
        ]

    def _workspace_by_name(self, name: str) -> Path:
        for path in self._workspace_paths():
            if path.name == name:
                return path
        raise HTTPException(status_code=404, detail="workspace not found")

    def _workspace_summary(self, path: Path) -> dict[str, Any]:
        db_path = path / "translate.db"
        summary: dict[str, Any] = {
            "name": path.name,
            "path": str(path),
            "database_path": str(db_path),
            "database_exists": db_path.exists(),
            "database_size": db_path.stat().st_size if db_path.exists() else 0,
            "readable": False,
            "project_count": 0,
            "status_counts": {},
            "format_counts": {},
            "latest_project_updated_at": None,
            "error": None,
        }
        if not db_path.exists():
            return summary
        try:
            with self._connect(path) as conn:
                if not self._has_table(conn, "translation_project"):
                    summary["error"] = "translation_project table not found"
                    return summary
                project_stats = conn.execute(
                    "SELECT COUNT(*) AS count, MAX(updated_at) AS latest FROM translation_project"
                ).fetchone()
                summary["readable"] = True
                summary["project_count"] = project_stats["count"] or 0
                summary["latest_project_updated_at"] = project_stats["latest"]
                summary["status_counts"] = self._status_counts(path, conn)
                summary["format_counts"] = self._format_counts(path, conn)
        except sqlite3.Error as exc:
            summary["error"] = str(exc)
        return summary

    def _require_database(self, workspace: Path) -> None:
        if not (workspace / "translate.db").exists():
            raise HTTPException(status_code=404, detail="translate.db not found")

    @contextmanager
    def _connect(self, workspace: Path) -> Iterator[sqlite3.Connection]:
        db_path = (workspace / "translate.db").resolve()
        uri = f"file:{db_path.as_posix()}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA busy_timeout = 1000")
            yield conn
        finally:
            try:
                conn.close()
            except UnboundLocalError:
                pass

    def _has_table(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    def _status_counts(self, workspace: Path, conn: sqlite3.Connection | None = None) -> dict[str, int]:
        if conn is not None:
            return self._count_rows(conn, "SELECT status, COUNT(*) AS count FROM translation_project GROUP BY status")
        with self._connect(workspace) as owned:
            return self._count_rows(owned, "SELECT status, COUNT(*) AS count FROM translation_project GROUP BY status")

    def _format_counts(self, workspace: Path, conn: sqlite3.Connection | None = None) -> dict[str, int]:
        sql = "SELECT input_format, COUNT(*) AS count FROM translation_project GROUP BY input_format"
        if conn is not None:
            return self._count_rows(conn, sql, key="input_format")
        with self._connect(workspace) as owned:
            return self._count_rows(owned, sql, key="input_format")

    def _count_rows(
        self,
        conn: sqlite3.Connection,
        sql: str,
        params: tuple[Any, ...] = (),
        key: str = "status",
    ) -> dict[str, int]:
        return {str(row[key]): int(row["count"] or 0) for row in conn.execute(sql, params).fetchall()}

    def _project_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in ("total_chunks", "done_chunks", "failed_chunks", "pending_chunks", "failed_reports", "block_count", "attempt_count"):
            data[key] = int(data.get(key) or 0)
        return data

    def _chunk_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data = self._decode_json_columns(data, ("block_ids", "metadata"))
        for key in (
            "source_chars",
            "protected_chars",
            "target_chars",
            "restored_chars",
            "failed_reports",
            "attempt_count",
            "protected_span_count",
        ):
            data[key] = int(data.get(key) or 0)
        data["block_count"] = len(data.get("block_ids") or [])
        return data

    def _decode_json_columns(self, row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
        for column in columns:
            row[column] = _loads(row.get(column), [] if column in {"block_ids", "issues"} else {})
        return row

    def _artifact_entries(self, workspace: Path, project_id: str) -> list[dict[str, Any]]:
        artifact_dir = workspace / "projects" / project_id / "artifacts"
        if not artifact_dir.is_dir():
            return []
        entries: list[dict[str, Any]] = []
        for path in sorted(artifact_dir.iterdir(), key=lambda item: item.name):
            if not path.is_file():
                continue
            stat = path.stat()
            entries.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
        return entries

    def _workspace_public(self, workspace: Path) -> dict[str, str]:
        return {"name": workspace.name, "path": str(workspace), "database_path": str(workspace / "translate.db")}


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _default_root() -> Path:
    return Path(os.getenv("LLM_TRANSLATE_WEB_ROOT", Path.cwd()))


app = create_app()


def run_web_server() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required. Install with: pip install -r requirements-web.txt") from exc
    uvicorn.run("llm_translate.web.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run_web_server()

