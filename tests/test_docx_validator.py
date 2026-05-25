"""DOCX validator tests."""

import unittest

from llm_translate.validators_docx import DocxValidator
from llm_translate.domain import TranslationChunk, ChunkStatus, GlossaryTerm, DocumentBlock


class DocxValidatorTest(unittest.TestCase):
    """Test cases for DOCX validator."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = DocxValidator()

    def _create_test_chunk(self, source_text: str, target_text: str, **kwargs) -> TranslationChunk:
        """Create a test translation chunk."""
        return TranslationChunk(
            id="test_chunk",
            project_id="test_project",
            chapter_id=None,
            chunk_order=0,
            block_ids=["block_1"],
            source_text=source_text,
            target_text=target_text,
            restored_text=target_text,
            status=ChunkStatus.DONE,
            **kwargs
        )

    def test_validate_successful_translation(self):
        """Test validation of successful translation."""
        chunk = self._create_test_chunk(
            source_text="This is a test paragraph.",
            target_text="这是一个测试段落。"
        )

        report = self.validator.validate_chunk(chunk, [])

        self.assertEqual(report.status, "PASS")
        self.assertEqual(len(report.issues), 0)

    def test_validate_missing_placeholder(self):
        """Test detection of missing placeholders."""
        chunk = self._create_test_chunk(
            source_text="Visit https://example.com for more info.",
            target_text="Visit [MISSING] for more info.",
            protected_text="Visit __LT_URL_000001__ for more info."
        )

        report = self.validator.validate_chunk(chunk, [])

        self.assertEqual(report.status, "FAIL")
        self.assertTrue(any(issue["type"] == "MISSING_PLACEHOLDER" for issue in report.issues))

    def test_validate_empty_output(self):
        """Test detection of empty output."""
        chunk = self._create_test_chunk(
            source_text="This is a test paragraph.",
            target_text=""
        )

        report = self.validator.validate_chunk(chunk, [])

        self.assertEqual(report.status, "FAIL")
        self.assertTrue(any(issue["type"] == "EMPTY_OUTPUT" for issue in report.issues))

    def test_validate_broken_code_patterns(self):
        """Test detection of broken code patterns."""
        chunk = self._create_test_chunk(
            source_text="Use data = {'key': 'value'} for processing.",
            target_text="Use data = {'key': 'value' for processing."  # Missing closing brace
        )

        report = self.validator.validate_chunk(chunk, [])

        self.assertEqual(report.status, "FAIL")
        self.assertTrue(any(issue["type"] == "BROKEN_CODE_PATTERNS" for issue in report.issues))

    def test_validate_glossary_term_missing(self):
        """Test detection of missing glossary terms."""
        chunk = self._create_test_chunk(
            source_text="Use the API endpoint for data.",
            target_text="使用数据端点。"  # Missing "API" -> "接口"
        )

        glossary_terms = [
            GlossaryTerm(
                id="term_1",
                project_id="test_project",
                source_term="API",
                target_term="接口",
                case_sensitive=False
            )
        ]

        report = self.validator.validate_chunk(chunk, glossary_terms)

        self.assertEqual(report.status, "FAIL")
        self.assertTrue(any(issue["type"] == "TERM_MISSING" for issue in report.issues))

    def test_validate_length_anomaly(self):
        """Test detection of length anomalies."""
        chunk = self._create_test_chunk(
            source_text="This is a normal paragraph with reasonable content.",
            target_text="短"  # Too short
        )

        report = self.validator.validate_chunk(chunk, [])

        self.assertEqual(report.status, "FAIL")
        self.assertTrue(any(issue["type"] == "LENGTH_ANOMALY" for issue in report.issues))

    def test_validate_document_integrity_success(self):
        """Test successful document integrity validation."""
        blocks = [
            DocumentBlock(
                id="block_1",
                project_id="test_project",
                parent_id=None,
                block_order=0,
                block_type="docx_paragraph",
                level=None,
                source_text="First paragraph.",
            ),
            DocumentBlock(
                id="block_2",
                project_id="test_project",
                parent_id=None,
                block_order=1,
                block_type="docx_paragraph",
                level=None,
                source_text="Second paragraph.",
            ),
        ]

        chunks = [
            TranslationChunk(
                id="chunk_1",
                project_id="test_project",
                chapter_id=None,
                chunk_order=0,
                block_ids=["block_1", "block_2"],
                source_text="First paragraph.\n\nSecond paragraph.",
                target_text="第一段。\n\n第二段。",
                status=ChunkStatus.DONE,
            )
        ]

        report = self.validator.validate_document_integrity(blocks, chunks)

        self.assertEqual(report.status, "PASS")
        self.assertEqual(len(report.issues), 0)

    def test_validate_document_integrity_missing_blocks(self):
        """Test detection of missing translations."""
        blocks = [
            DocumentBlock(
                id="block_1",
                project_id="test_project",
                parent_id=None,
                block_order=0,
                block_type="docx_paragraph",
                level=None,
                source_text="First paragraph.",
            ),
            DocumentBlock(
                id="block_2",
                project_id="test_project",
                parent_id=None,
                block_order=1,
                block_type="docx_paragraph",
                level=None,
                source_text="Second paragraph.",
            ),
        ]

        chunks = [
            TranslationChunk(
                id="chunk_1",
                project_id="test_project",
                chapter_id=None,
                chunk_order=0,
                block_ids=["block_1"],  # Missing block_2
                source_text="First paragraph.",
                target_text="第一段。",
                status=ChunkStatus.DONE,
            )
        ]

        report = self.validator.validate_document_integrity(blocks, chunks)

        self.assertEqual(report.status, "FAIL")
        self.assertTrue(any(issue["type"] == "MISSING_TRANSLATIONS" for issue in report.issues))

    def test_analyze_document_structure(self):
        """Test document structure analysis."""
        blocks = [
            DocumentBlock(
                id="block_1",
                project_id="test_project",
                parent_id=None,
                block_order=0,
                block_type="docx_heading_1",
                level=1,
                source_text="Title",
            ),
            DocumentBlock(
                id="block_2",
                project_id="test_project",
                parent_id=None,
                block_order=1,
                block_type="docx_paragraph",
                level=None,
                source_text="Paragraph 1",
            ),
            DocumentBlock(
                id="block_3",
                project_id="test_project",
                parent_id=None,
                block_order=2,
                block_type="docx_paragraph",
                level=None,
                source_text="Paragraph 2",
            ),
        ]

        structure = self.validator._analyze_document_structure(blocks)

        self.assertEqual(structure["total_blocks"], 3)
        self.assertEqual(structure["headings"], 1)
        self.assertEqual(structure["paragraphs"], 2)
        self.assertEqual(structure["heading_levels"], [1])

    def test_paragraph_count_unchanged(self):
        """Test paragraph count validation."""
        chunk = self._create_test_chunk(
            source_text="Line 1\nLine 2\nLine 3",
            target_text="第1行\n第2行\n第3行"
        )

        report = self.validator.validate_chunk(chunk, [])

        # Should pass because paragraph count is the same
        self.assertEqual(report.status, "PASS")

    def test_paragraph_count_changed_significantly(self):
        """Test detection of significant paragraph count changes."""
        chunk = self._create_test_chunk(
            source_text="Line 1\nLine 2\nLine 3\nLine 4\nLine 5",
            target_text="合并的内容"  # All paragraphs merged into one
        )

        report = self.validator.validate_chunk(chunk, [])

        # Should fail because paragraph count changed significantly
        self.assertEqual(report.status, "FAIL")
        self.assertTrue(any(issue["type"] == "PARAGRAPH_COUNT_CHANGED" for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
