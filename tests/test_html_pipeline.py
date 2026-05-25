from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bs4 import BeautifulSoup

from llm_translate.config import Settings
from llm_translate.domain import ChunkStatus
from llm_translate.llm import MockLLMProvider
from llm_translate.service import TranslationService


HTML_SAMPLE = """<!doctype html>
<html>
  <head>
    <title>Sample</title>
    <link rel="stylesheet" href="sample_files/site.css">
    <style>.article { color: red; }</style>
    <script>const label = "Agent";</script>
  </head>
  <body>
    <nav><ul><li>Menu Agent</li></ul></nav>
    <main id="content" class="article main">
      <h1>Agent Guide</h1>
      <p>Agent calls a Tool Call and reads <a class="ref" href="https://example.com/docs">official docs</a>.</p>
      <figure>
        <img src="sample_files/cover.png" alt="Agent diagram">
        <figcaption>Agent diagram</figcaption>
      </figure>
      <table><tr><th>Topic</th><td>Tool Call</td></tr></table>
      <button class="cta">Start Agent</button>
      <pre><code>Agent must not change inside code.</code></pre>
    </main>
    <footer><p>Footer Agent</p></footer>
  </body>
</html>
"""


class HTMLPipelineTest(unittest.TestCase):
    def test_end_to_end_mock_pipeline_exports_translated_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.html"
            source.write_text(HTML_SAMPLE, encoding="utf-8")
            resource_dir = root / "sample_files"
            resource_dir.mkdir()
            (resource_dir / "site.css").write_text(".article { font-weight: 600; }", encoding="utf-8")
            (resource_dir / "cover.png").write_bytes(b"fake-image")
            glossary = root / "glossary.csv"
            glossary.write_text(
                "source_term,target_term\nAgent,Intelligent Agent\nTool Call,Tool Invocation\n",
                encoding="utf-8",
            )
            settings = Settings(database_path=root / "translate.db", workspace_path=root / "workspace")
            service = TranslationService(settings)
            project, artifacts = service.run(
                source,
                "sample-html",
                MockLLMProvider(),
                glossary_path=glossary,
            )

            self.assertEqual(project.input_format, "html")
            self.assertIn("html", artifacts)
            self.assertTrue(artifacts["html"].exists())
            self.assertTrue(artifacts["translated"].exists())
            self.assertTrue((service.project_dir(project.id) / "source" / "sample_files" / "site.css").exists())
            self.assertTrue((artifacts["html"].parent / "sample_files" / "site.css").exists())

            chunks = service.store.list_chunks(project.id)
            self.assertGreaterEqual(len(chunks), 1)
            self.assertTrue(any(len(chunk.block_ids) > 1 for chunk in chunks))
            self.assertEqual({chunk.status for chunk in chunks}, {ChunkStatus.DONE})

            original_soup = BeautifulSoup(source.read_text(encoding="utf-8"), "html5lib")
            exported_soup = BeautifulSoup(artifacts["html"].read_text(encoding="utf-8"), "html5lib")

            self.assertEqual(
                [node.get("href") for node in original_soup.find_all("a")],
                [node.get("href") for node in exported_soup.find_all("a")],
            )
            self.assertEqual(
                [node.get("src") for node in original_soup.find_all("img")],
                [node.get("src") for node in exported_soup.find_all("img")],
            )
            self.assertEqual(
                original_soup.find("main").get("class"),
                exported_soup.find("main").get("class"),
            )
            self.assertEqual(
                original_soup.find("main").get("id"),
                exported_soup.find("main").get("id"),
            )
            self.assertEqual(original_soup.find("style").get_text(), exported_soup.find("style").get_text())
            self.assertEqual(original_soup.find("script").get_text(), exported_soup.find("script").get_text())
            self.assertEqual(original_soup.find("pre").get_text(), exported_soup.find("pre").get_text())

            exported_text = exported_soup.get_text(" ")
            self.assertIn("Intelligent Agent Guide", exported_text)
            self.assertIn("Tool Invocation", exported_text)
            self.assertIn("Menu Agent", exported_text)
            self.assertIn("Footer Agent", exported_text)
            self.assertNotIn("Intelligent Agent must not change inside code", exported_text)

            report = artifacts["validation_report_md"].read_text(encoding="utf-8")
            self.assertIn("HTML_STRUCTURE", report)
            self.assertIn("HTML_ARTIFACT", report)


if __name__ == "__main__":
    unittest.main()
