from __future__ import annotations

from pathlib import Path
import sys
import types
import unittest

from llm_translate.pdf_cleanliness import PdfCleanlinessChecker


class FakeRect:
    def __init__(self, width: float = 600, height: float = 800):
        self.width = width
        self.height = height


class FakePage:
    def __init__(
        self,
        text: str,
        blocks: list[tuple],
        images: list[dict] | None = None,
    ):
        self.rect = FakeRect()
        self._text = text
        self._blocks = blocks
        self._images = images or []

    def get_text(self, mode: str):
        if mode == "text":
            return self._text
        if mode == "blocks":
            return self._blocks
        raise ValueError(mode)

    def get_image_info(self, xrefs: bool = True):
        return self._images


class FakeDoc:
    is_encrypted = False
    needs_pass = False

    def __init__(self, pages: list[FakePage]):
        self.pages = pages

    def __len__(self) -> int:
        return len(self.pages)

    def __getitem__(self, index: int) -> FakePage:
        return self.pages[index]

    def close(self) -> None:
        pass


class PdfCleanlinessCheckerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_pymupdf = sys.modules.get("pymupdf")

    def tearDown(self) -> None:
        if self._previous_pymupdf is None:
            sys.modules.pop("pymupdf", None)
        else:
            sys.modules["pymupdf"] = self._previous_pymupdf

    def test_clean_text_pdf_is_accepted_for_phase1(self) -> None:
        text = ("This clean technical paper has normal words and paragraphs. " * 20).strip()
        blocks = [(50, 120, 540, 500, text, 0, 0)]
        self._install_fake_pymupdf([FakePage(text, blocks), FakePage(text, blocks)])

        report = PdfCleanlinessChecker().check(Path("clean.pdf"))

        self.assertEqual(report.level, "VERY_CLEAN")
        self.assertTrue(report.can_translate_phase1)
        self.assertGreaterEqual(report.avg_text_chars_per_page, 500)
        self.assertEqual(report.large_image_page_ratio, 0)

    def test_scanned_like_pdf_is_rejected(self) -> None:
        text = "Page 1"
        blocks = [(50, 120, 540, 140, text, 0, 0)]
        full_page_image = [{"bbox": (0, 0, 600, 800)}]
        self._install_fake_pymupdf(
            [
                FakePage(text, blocks, full_page_image),
                FakePage(text, blocks, full_page_image),
            ]
        )

        report = PdfCleanlinessChecker().check(Path("scan.pdf"))

        self.assertEqual(report.level, "NOT_RECOMMENDED")
        self.assertFalse(report.can_translate_phase1)
        self.assertEqual(report.large_image_page_ratio, 1)
        self.assertTrue(any("Large-image page ratio" in problem for problem in report.problems))

    def test_multi_column_pdf_is_scored_but_not_phase1_clean(self) -> None:
        line = "This paragraph is long enough to count as a real text block."
        blocks = [
            (45, 100, 260, 140, line, 0, 0),
            (45, 150, 260, 190, line, 0, 0),
            (45, 200, 260, 240, line, 0, 0),
            (345, 100, 560, 140, line, 0, 0),
            (345, 150, 560, 190, line, 0, 0),
            (345, 200, 560, 240, line, 0, 0),
        ]
        text = "\n".join(block[4] for block in blocks) * 3
        self._install_fake_pymupdf([FakePage(text, blocks)])

        report = PdfCleanlinessChecker().check(Path("two-column.pdf"))

        self.assertEqual(report.suspected_multi_column_ratio, 1)
        self.assertFalse(report.can_translate_phase1)
        self.assertIn(report.level, {"CLEAN", "NEEDS_CLEANING"})

    def test_garbled_text_is_detected(self) -> None:
        checker = PdfCleanlinessChecker()

        self.assertGreater(checker._garbled_ratio("abc\ufffd\ue000"), 0)
        self.assertEqual(checker._garbled_ratio("normal text"), 0)

    def _install_fake_pymupdf(self, pages: list[FakePage]) -> None:
        module = types.ModuleType("pymupdf")
        module.open = lambda _path: FakeDoc(pages)
        sys.modules["pymupdf"] = module


if __name__ == "__main__":
    unittest.main()
