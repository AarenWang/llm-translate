from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

import unittest

from llm_translate.config import Settings
from llm_translate.domain import ChunkStatus
from llm_translate.llm import MockLLMProvider
from llm_translate.service import TranslationService
from llm_translate.parser.epub import EpubParser
from llm_translate.formats.epub import EpubFormatAdapter


CHAPTER = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Sample</title>
    <link href="styles.css" rel="stylesheet" type="text/css"/>
  </head>
  <body>
    <section>
      <h1>Agent Guide</h1>
      <p>Agent reads a book and calls a Tool Call.</p>
      <p>See <a href="https://example.com/docs">official docs</a>.</p>
      <figure>
        <img src="images/cover.png" alt="cover"/>
        <figcaption>Agent diagram</figcaption>
      </figure>
      <pre><code>Agent must not change inside code.</code></pre>
    </section>
  </body>
</html>
"""


class EpubPipelineTest(unittest.TestCase):
    def test_end_to_end_mock_pipeline_exports_translated_epub(self) -> None:
        """Test complete end-to-end EPUB translation pipeline."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sample.epub"
            self._write_sample_epub(source)
            glossary = root / "glossary.csv"
            glossary.write_text(
                "source_term,target_term\nAgent,Intelligent Agent\nTool Call,Tool Invocation\n",
                encoding="utf-8",
            )
            settings = Settings(database_path=root / "translate.db", workspace_path=root / "workspace")
            service = TranslationService(settings)
            project, artifacts = service.run(
                source,
                "sample-epub",
                MockLLMProvider(),
                glossary_path=glossary,
            )

            self.assertEqual(project.input_format, "epub")
            chunks = service.store.list_chunks(project.id)
            self.assertGreaterEqual(len(chunks), 4)
            self.assertEqual({chunk.status for chunk in chunks}, {ChunkStatus.DONE})
            self.assertIn("epub", artifacts)
            self.assertTrue(artifacts["epub"].exists())

            with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(artifacts["epub"], "r") as exported:
                self.assertEqual(original.namelist(), exported.namelist())
                self.assertEqual(exported.namelist()[0], "mimetype")
                original_chapter = original.read("OEBPS/chapter1.xhtml").decode("utf-8")
                exported_chapter = exported.read("OEBPS/chapter1.xhtml").decode("utf-8")

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
                original_soup = BeautifulSoup(original_chapter, "html5lib")
                exported_soup = BeautifulSoup(exported_chapter, "html5lib")
            self.assertEqual(
                [node.get("href") for node in original_soup.find_all("a")],
                [node.get("href") for node in exported_soup.find_all("a")],
            )
            self.assertEqual(
                [node.get("src") for node in original_soup.find_all("img")],
                [node.get("src") for node in exported_soup.find_all("img")],
            )
            self.assertEqual(
                original_soup.find("pre").get_text(),
                exported_soup.find("pre").get_text(),
            )
            self.assertIn("Intelligent Agent Guide", exported_soup.get_text())
            self.assertIn("Tool Invocation", exported_soup.get_text())

            report = artifacts["validation_report_md"].read_text(encoding="utf-8")
            self.assertIn("EPUB_STRUCTURE", report)
            self.assertIn("EPUB_ARTIFACT", report)
            glossary = root / "glossary.csv"
            glossary.write_text(
                "source_term,target_term\nAgent,Intelligent Agent\nTool Call,Tool Invocation\n",
                encoding="utf-8",
            )
            settings = Settings(database_path=root / "translate.db", workspace_path=root / "workspace")
            service = TranslationService(settings)
            project, artifacts = service.run(
                source,
                "sample-epub",
                MockLLMProvider(),
                glossary_path=glossary,
            )

            self.assertEqual(project.input_format, "epub")
            chunks = service.store.list_chunks(project.id)
            self.assertGreaterEqual(len(chunks), 4)
            self.assertEqual({chunk.status for chunk in chunks}, {ChunkStatus.DONE})
            self.assertIn("epub", artifacts)
            self.assertTrue(artifacts["epub"].exists())

            with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(artifacts["epub"], "r") as exported:
                self.assertEqual(original.namelist(), exported.namelist())
                self.assertEqual(exported.namelist()[0], "mimetype")
                original_chapter = original.read("OEBPS/chapter1.xhtml").decode("utf-8")
                exported_chapter = exported.read("OEBPS/chapter1.xhtml").decode("utf-8")

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
                original_soup = BeautifulSoup(original_chapter, "html5lib")
                exported_soup = BeautifulSoup(exported_chapter, "html5lib")
            self.assertEqual(
                [node.get("href") for node in original_soup.find_all("a")],
                [node.get("href") for node in exported_soup.find_all("a")],
            )
            self.assertEqual(
                [node.get("src") for node in original_soup.find_all("img")],
                [node.get("src") for node in exported_soup.find_all("img")],
            )
            self.assertEqual(
                original_soup.find("pre").get_text(),
                exported_soup.find("pre").get_text(),
            )
            self.assertIn("Intelligent Agent Guide", exported_soup.get_text())
            self.assertIn("Tool Invocation", exported_soup.get_text())

            report = artifacts["validation_report_md"].read_text(encoding="utf-8")
            self.assertIn("EPUB_STRUCTURE", report)
            self.assertIn("EPUB_ARTIFACT", report)

    def test_code_protection(self) -> None:
        """Test that code blocks are protected from translation."""
        parser = EpubParser()
        code_html = """
        <html><body>
            <h1>Code Protection Test</h1>
            <pre><code>def hello(): print("world")</code></pre>
            <p>Regular text here</p>
            <p>More text here</p>
        </body></html>
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "code.epub"
            self._write_epub_with_content(source, code_html)
            result = parser.parse("test_project", source)

            # Code blocks should not be extracted for translation
            code_blocks = [b for b in result.blocks if "def hello()" in b.source_text]
            self.assertEqual(len(code_blocks), 0)

            # Regular text should still be extracted
            regular_blocks = [b for b in result.blocks if "Regular text" in b.source_text]
            self.assertGreater(len(regular_blocks), 0)

    def test_special_character_handling(self) -> None:
        """Test that special characters are handled correctly."""
        parser = EpubParser()
        test_html = """
        <html><body>
            <h1>Special Characters</h1>
            <p>Hello & goodbye</p>
            <p>Unicode: 你好世界</p>
            <p>Emoji: 🎉🌟</p>
        </body></html>
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "special.epub"
            self._write_epub_with_content(source, test_html)
            result = parser.parse("test_project", source)

            # Should extract text with special characters
            self.assertGreater(len(result.blocks), 0)
            extracted_texts = [block.source_text for block in result.blocks]
            self.assertTrue(any("Hello & goodbye" in text for text in extracted_texts))
            self.assertTrue(any("你好世界" in text for text in extracted_texts))

    def test_nested_structure_handling(self) -> None:
        """Test handling of deeply nested HTML structures."""
        parser = EpubParser()
        nested_html = """
        <html><body>
            <h1>Nested Structure Test</h1>
            <div>
                <section>
                    <article>
                        <div>
                            <p>Deep nested text</p>
                        </div>
                    </article>
                </section>
            </div>
        </body></html>
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "nested.epub"
            self._write_epub_with_content(source, nested_html)
            result = parser.parse("test_project", source)

            # Should still extract text from deeply nested structures
            deep_blocks = [b for b in result.blocks if "Deep nested text" in b.source_text]
            self.assertGreater(len(deep_blocks), 0)

    def test_format_adapter_detection(self) -> None:
        """Test that the format adapter correctly identifies EPUB files."""
        adapter = EpubFormatAdapter()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # Test positive case
            epub_path = root / "test.epub"
            self.assertTrue(adapter.supports(epub_path))

            # Test negative cases
            txt_path = root / "test.txt"
            self.assertFalse(adapter.supports(txt_path))

            md_path = root / "test.md"
            self.assertFalse(adapter.supports(md_path))

            # Test case insensitivity
            epub_upper = root / "TEST.EPUB"
            self.assertTrue(adapter.supports(epub_upper))

    def test_multiple_chapters(self) -> None:
        """Test handling of EPUB files with multiple chapters."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "multi.epub"
            self._write_multi_chapter_epub(source)
            settings = Settings(database_path=root / "translate.db", workspace_path=root / "workspace")
            service = TranslationService(settings)

            parser = EpubParser()
            result = parser.parse("test_project", source)

            # Should have multiple documents
            self.assertGreater(len(result.documents), 1)

            # Each document should have valid metadata
            for doc in result.documents:
                self.assertIsNotNone(doc.item_id)
                self.assertIsNotNone(doc.href)
                self.assertGreaterEqual(doc.spine_index, 0)

    def _write_epub_with_content(self, path: Path, content: str) -> None:
        """Create an EPUB file with specific content for testing."""
        container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        opf = """<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="bookid" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:test-book</dc:identifier>
    <dc:title>Test EPUB</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>
"""
        nav = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Nav</title></head>
<body><nav epub:type="toc"><ol><li><a href="chapter1.xhtml">Chapter 1</a></li></ol></nav></body>
</html>
"""
        chapter = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Test</title></head>
  <body>{content}</body>
</html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", opf)
            archive.writestr("OEBPS/nav.xhtml", nav)
            archive.writestr("OEBPS/chapter1.xhtml", chapter)

    def _write_multi_chapter_epub(self, path: Path) -> None:
        """Create an EPUB file with multiple chapters for testing."""
        container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        opf = """<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="bookid" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:multi-chapter</dc:identifier>
    <dc:title>Multi-Chapter EPUB</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="chapter2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
    <itemref idref="chapter2"/>
  </spine>
</package>
"""
        nav = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body><nav epub:type="toc"><ol><li><a href="chapter1.xhtml">Chapter 1</a></li><li><a href="chapter2.xhtml">Chapter 2</a></li></ol></nav></body></html>
"""
        chapter1 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter 1</title></head>
  <body><h1>First Chapter</h1><p>Content of chapter one.</p></body>
</html>
"""
        chapter2 = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>Chapter 2</title></head>
  <body><h1>Second Chapter</h1><p>Content of chapter two.</p></body>
</html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", opf)
            archive.writestr("OEBPS/nav.xhtml", nav)
            archive.writestr("OEBPS/chapter1.xhtml", chapter1)
            archive.writestr("OEBPS/chapter2.xhtml", chapter2)

    def _write_sample_epub(self, path: Path) -> None:
        container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        opf = """<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="bookid" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:test-book</dc:identifier>
    <dc:title>Sample EPUB</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="css" href="styles.css" media-type="text/css"/>
    <item id="cover" href="images/cover.png" media-type="image/png"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>
"""
        nav = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body><nav epub:type="toc"><ol><li><a href="chapter1.xhtml">Start</a></li></ol></nav></body></html>
"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container)
            archive.writestr("OEBPS/content.opf", opf)
            archive.writestr("OEBPS/nav.xhtml", nav)
            archive.writestr("OEBPS/chapter1.xhtml", CHAPTER)
            archive.writestr("OEBPS/styles.css", "body { font-family: serif; }")
            archive.writestr("OEBPS/images/cover.png", b"fake-image")


if __name__ == "__main__":
    unittest.main()
