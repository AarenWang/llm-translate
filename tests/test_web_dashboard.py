from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from llm_translate.domain import (
    ChunkStatus,
    ProjectStatus,
    TranslationChunk,
    TranslationProject,
    ValidationReport,
)
from llm_translate.storage import SQLiteStore
from llm_translate.web.app import create_app


class WebDashboardTest(unittest.TestCase):
    def test_read_only_workspace_project_and_chunk_endpoints(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / ".llm_translate_web"
            db_path = workspace / "translate.db"
            store = SQLiteStore(db_path)
            store.init_db()
            project = TranslationProject(
                id="prj_web",
                name="Web Smoke",
                source_file_name="sample.md",
                source_language=None,
                target_language="zh-CN",
                input_format="markdown",
                status=ProjectStatus.EXPORTED,
            )
            store.create_project(project)
            chunk = TranslationChunk(
                id="chunk_web_1",
                project_id=project.id,
                chapter_id=None,
                chunk_order=0,
                block_ids=[],
                source_text="Agent writes notes.",
                restored_text="Agent writes notes.",
                status=ChunkStatus.DONE,
            )
            store.replace_chunks(project.id, [chunk])
            store.add_validation_report(
                ValidationReport(
                    id="vr_web",
                    project_id=project.id,
                    chunk_id=chunk.id,
                    check_type="CHUNK",
                    status="PASS",
                    issues=[],
                )
            )
            artifact_dir = workspace / "projects" / project.id / "artifacts"
            artifact_dir.mkdir(parents=True)
            (artifact_dir / "translated.md").write_text("Agent writes notes.\n", encoding="utf-8")

            client = TestClient(create_app(root))
            workspaces = client.get("/api/workspaces")
            self.assertEqual(workspaces.status_code, 200)
            self.assertEqual(workspaces.json()["workspaces"][0]["name"], ".llm_translate_web")

            projects = client.get("/api/workspaces/.llm_translate_web/projects")
            self.assertEqual(projects.status_code, 200)
            self.assertEqual(projects.json()["projects"][0]["id"], project.id)

            detail = client.get("/api/workspaces/.llm_translate_web/projects/prj_web")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["chunk_status_counts"], {"DONE": 1})
            self.assertEqual(len(detail.json()["artifacts"]), 1)

            chunk_detail = client.get("/api/workspaces/.llm_translate_web/projects/prj_web/chunks/chunk_web_1")
            self.assertEqual(chunk_detail.status_code, 200)
            self.assertEqual(chunk_detail.json()["chunk"]["status"], "DONE")


if __name__ == "__main__":
    unittest.main()

