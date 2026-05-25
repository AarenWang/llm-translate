from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class PdfCleanlinessReport:
    file: str
    page_count: int
    encrypted: bool

    total_text_chars: int
    avg_text_chars_per_page: float
    english_word_ratio: float
    garbled_ratio: float
    cid_marker_count: int

    image_count: int
    large_image_page_ratio: float

    avg_blocks_per_page: float
    suspected_multi_column_ratio: float
    repeated_header_footer_candidates: int
    paragraph_fragmentation_ratio: float

    score: float
    level: str
    can_translate_phase1: bool
    problems: list[str]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PdfCleanlinessChecker:
    """Estimate whether a PDF is suitable for phase-1 structured translation."""

    def __init__(
        self,
        min_avg_chars_per_page: int = 500,
        max_garbled_ratio: float = 0.01,
        min_english_word_ratio: float = 0.45,
        max_large_image_page_ratio: float = 0.35,
        max_multi_column_ratio: float = 0.30,
        max_paragraph_fragmentation_ratio: float = 0.55,
    ):
        self.min_avg_chars_per_page = min_avg_chars_per_page
        self.max_garbled_ratio = max_garbled_ratio
        self.min_english_word_ratio = min_english_word_ratio
        self.max_large_image_page_ratio = max_large_image_page_ratio
        self.max_multi_column_ratio = max_multi_column_ratio
        self.max_paragraph_fragmentation_ratio = max_paragraph_fragmentation_ratio

    def check(self, pdf_path: str | Path) -> PdfCleanlinessReport:
        pdf_path = Path(pdf_path)
        problems: list[str] = []

        try:
            pymupdf = self._load_pymupdf()
            doc = pymupdf.open(pdf_path)
        except Exception as exc:
            return self._broken_report(pdf_path, f"PDF could not be opened: {exc}")

        try:
            return self._check_open_document(pdf_path, doc, problems)
        finally:
            close = getattr(doc, "close", None)
            if callable(close):
                close()

    def is_clean_for_phase1(self, report: PdfCleanlinessReport) -> bool:
        return (
            report.level in {"VERY_CLEAN", "CLEAN"}
            and not report.encrypted
            and report.avg_text_chars_per_page >= self.min_avg_chars_per_page
            and report.garbled_ratio <= self.max_garbled_ratio
            and report.cid_marker_count == 0
            and report.large_image_page_ratio <= self.max_large_image_page_ratio
            and report.suspected_multi_column_ratio <= self.max_multi_column_ratio
        )

    def _check_open_document(
        self,
        pdf_path: Path,
        doc: Any,
        problems: list[str],
    ) -> PdfCleanlinessReport:
        encrypted = bool(getattr(doc, "is_encrypted", False) or getattr(doc, "needs_pass", False))
        if encrypted:
            problems.append("PDF is encrypted; exclude it from phase-1 translation.")

        try:
            page_count = len(doc)
        except Exception as exc:
            return self._broken_report(pdf_path, f"PDF page count could not be read: {exc}")

        if page_count == 0:
            problems.append("PDF has zero pages.")

        all_text_parts: list[str] = []
        page_text_lengths: list[int] = []
        page_block_counts: list[int] = []
        page_fragmentation_ratios: list[float] = []
        large_image_pages = 0
        image_count = 0
        suspected_multi_column_pages = 0
        header_footer_lines: list[str] = []

        for page_index in range(page_count):
            try:
                page = doc[page_index]
                page_width = float(page.rect.width)
                page_height = float(page.rect.height)
                page_area = page_width * page_height

                text = page.get_text("text") or ""
                all_text_parts.append(text)
                page_text_lengths.append(len(text))

                blocks = page.get_text("blocks") or []
                text_blocks = [
                    block
                    for block in blocks
                    if len(block) >= 5 and isinstance(block[4], str) and block[4].strip()
                ]
                page_block_counts.append(len(text_blocks))
                page_fragmentation_ratios.append(self._paragraph_fragmentation_ratio(text_blocks))

                if self._looks_multi_column(text_blocks, page_width):
                    suspected_multi_column_pages += 1

                images = self._image_info(page)
                image_count += len(images)
                if self._has_large_image(images, page_area):
                    large_image_pages += 1

                header_footer_lines.extend(
                    self._extract_header_footer_candidates(text_blocks, page_height)
                )
            except Exception as exc:
                problems.append(f"Page {page_index + 1} could not be analyzed: {exc}")

        full_text = "\n".join(all_text_parts)
        total_text_chars = len(full_text)
        avg_text_chars_per_page = statistics.mean(page_text_lengths) if page_text_lengths else 0
        english_word_ratio = self._english_word_ratio(full_text)
        garbled_ratio = self._garbled_ratio(full_text)
        cid_marker_count = len(re.findall(r"\(cid:\d+\)|cid:\d+", full_text, flags=re.I))

        large_image_page_ratio = large_image_pages / page_count if page_count else 1
        avg_blocks_per_page = statistics.mean(page_block_counts) if page_block_counts else 0
        suspected_multi_column_ratio = (
            suspected_multi_column_pages / page_count if page_count else 1
        )
        repeated_header_footer_candidates = self._count_repeated_lines(header_footer_lines)
        paragraph_fragmentation_ratio = (
            statistics.mean(page_fragmentation_ratios) if page_fragmentation_ratios else 1
        )

        cross_check = self._cross_validate_extractors(pdf_path, full_text)
        academic_markers = self._detect_academic_markers(full_text)

        score = self._score(
            encrypted=encrypted,
            page_count=page_count,
            avg_text_chars_per_page=avg_text_chars_per_page,
            garbled_ratio=garbled_ratio,
            cid_marker_count=cid_marker_count,
            english_word_ratio=english_word_ratio,
            large_image_page_ratio=large_image_page_ratio,
            suspected_multi_column_ratio=suspected_multi_column_ratio,
            repeated_header_footer_candidates=repeated_header_footer_candidates,
            paragraph_fragmentation_ratio=paragraph_fragmentation_ratio,
            extractor_length_similarity=cross_check.get("length_similarity"),
            problems=problems,
        )
        level = self._level(score)

        details = {
            "page_text_lengths": page_text_lengths,
            "page_block_counts": page_block_counts,
            "page_fragmentation_ratios": page_fragmentation_ratios,
            "large_image_pages": large_image_pages,
            "suspected_multi_column_pages": suspected_multi_column_pages,
            "extractor_cross_check": cross_check,
            "academic_markers": academic_markers,
        }

        report = PdfCleanlinessReport(
            file=str(pdf_path),
            page_count=page_count,
            encrypted=encrypted,
            total_text_chars=total_text_chars,
            avg_text_chars_per_page=avg_text_chars_per_page,
            english_word_ratio=english_word_ratio,
            garbled_ratio=garbled_ratio,
            cid_marker_count=cid_marker_count,
            image_count=image_count,
            large_image_page_ratio=large_image_page_ratio,
            avg_blocks_per_page=avg_blocks_per_page,
            suspected_multi_column_ratio=suspected_multi_column_ratio,
            repeated_header_footer_candidates=repeated_header_footer_candidates,
            paragraph_fragmentation_ratio=paragraph_fragmentation_ratio,
            score=max(0.0, min(100.0, score)),
            level=level,
            can_translate_phase1=False,
            problems=problems,
            details=details,
        )
        report.can_translate_phase1 = self.is_clean_for_phase1(report)
        return report

    def _score(
        self,
        *,
        encrypted: bool,
        page_count: int,
        avg_text_chars_per_page: float,
        garbled_ratio: float,
        cid_marker_count: int,
        english_word_ratio: float,
        large_image_page_ratio: float,
        suspected_multi_column_ratio: float,
        repeated_header_footer_candidates: int,
        paragraph_fragmentation_ratio: float,
        extractor_length_similarity: float | None,
        problems: list[str],
    ) -> float:
        score = 100.0

        if encrypted:
            score -= 30
        if page_count == 0:
            score -= 50

        if avg_text_chars_per_page < self.min_avg_chars_per_page:
            score -= 25
            problems.append(
                f"Average text chars per page is low: {avg_text_chars_per_page:.1f}."
            )

        if garbled_ratio > self.max_garbled_ratio:
            score -= 20
            problems.append(f"Garbled character ratio is high: {garbled_ratio:.3%}.")

        if cid_marker_count > 0:
            score -= min(20, cid_marker_count * 2)
            problems.append(f"CID-like garbling markers detected: {cid_marker_count}.")

        if english_word_ratio < self.min_english_word_ratio:
            score -= 15
            problems.append(f"English word ratio is low: {english_word_ratio:.3%}.")

        if large_image_page_ratio > self.max_large_image_page_ratio:
            score -= 25
            problems.append(
                f"Large-image page ratio is high: {large_image_page_ratio:.3%}."
            )

        if suspected_multi_column_ratio > self.max_multi_column_ratio:
            score -= 15
            problems.append(
                f"Suspected multi-column page ratio is high: {suspected_multi_column_ratio:.3%}."
            )

        if repeated_header_footer_candidates > max(2, page_count // 3):
            score -= 5
            problems.append(
                f"Repeated header/footer candidates detected: {repeated_header_footer_candidates}."
            )

        if paragraph_fragmentation_ratio > self.max_paragraph_fragmentation_ratio:
            score -= 10
            problems.append(
                f"Paragraph fragmentation ratio is high: {paragraph_fragmentation_ratio:.3%}."
            )

        if extractor_length_similarity is not None and extractor_length_similarity < 0.6:
            score -= 10
            problems.append(
                f"Extractor text lengths differ significantly: {extractor_length_similarity:.3%}."
            )

        return score

    def _english_word_ratio(self, text: str) -> float:
        if not text.strip():
            return 0.0
        words = re.findall(r"[A-Za-z][A-Za-z'\-]{1,}", text)
        tokens = re.findall(r"\S+", text)
        return len(words) / len(tokens) if tokens else 0.0

    def _garbled_ratio(self, text: str) -> float:
        if not text:
            return 1.0
        garbled_chars = 0
        for ch in text:
            code = ord(ch)
            if ch == "\ufffd":
                garbled_chars += 1
            elif 0xE000 <= code <= 0xF8FF:
                garbled_chars += 1
            elif code < 32 and ch not in "\n\r\t":
                garbled_chars += 1
        return garbled_chars / max(1, len(text))

    def _looks_multi_column(self, blocks: list[tuple[Any, ...]], page_width: float) -> bool:
        if len(blocks) < 6:
            return False

        x_positions = []
        for block in blocks:
            x0, _y0, _x1, _y1, text = block[:5]
            if len(text.strip()) < 30:
                continue
            x_positions.append(float(x0))

        if len(x_positions) < 6:
            return False

        left_band = middle_band = right_band = 0
        for x in x_positions:
            ratio = x / page_width if page_width else 0
            if ratio < 0.33:
                left_band += 1
            elif ratio < 0.66:
                middle_band += 1
            else:
                right_band += 1

        return left_band >= 3 and (middle_band + right_band) >= 3

    def _paragraph_fragmentation_ratio(self, blocks: list[tuple[Any, ...]]) -> float:
        longish_blocks = 0
        fragmented_blocks = 0

        for block in blocks:
            text = str(block[4]).strip()
            if len(text) < 80:
                continue
            longish_blocks += 1
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            short_lines = [line for line in lines if len(line) < 55]
            if len(lines) >= 4 and len(short_lines) / len(lines) > 0.65:
                fragmented_blocks += 1

        if not longish_blocks:
            return 0.0
        return fragmented_blocks / longish_blocks

    def _extract_header_footer_candidates(
        self,
        blocks: list[tuple[Any, ...]],
        page_height: float,
    ) -> list[str]:
        candidates = []
        for block in blocks:
            _x0, y0, _x1, y1, text = block[:5]
            in_top = float(y1) < page_height * 0.12
            in_bottom = float(y0) > page_height * 0.88
            if in_top or in_bottom:
                line = self._normalize_line(text)
                if 2 <= len(line) <= 120:
                    candidates.append(line)
        return candidates

    def _normalize_line(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text.strip())
        text = re.sub(r"\bpage\s+\d+\b", "page #", text, flags=re.I)
        text = re.sub(r"^\d+$", "#", text)
        return text.lower()

    def _count_repeated_lines(self, lines: list[str]) -> int:
        counts: dict[str, int] = {}
        for line in lines:
            counts[line] = counts.get(line, 0) + 1
        return sum(1 for count in counts.values() if count >= 2)

    def _level(self, score: float) -> str:
        if score >= 90:
            return "VERY_CLEAN"
        if score >= 75:
            return "CLEAN"
        if score >= 60:
            return "NEEDS_CLEANING"
        return "NOT_RECOMMENDED"

    def _image_info(self, page: Any) -> list[dict[str, Any]]:
        get_image_info = getattr(page, "get_image_info", None)
        if callable(get_image_info):
            return list(get_image_info(xrefs=True) or [])

        get_images = getattr(page, "get_images", None)
        if callable(get_images):
            return [{"xref": image[0]} for image in get_images(full=True)]
        return []

    def _has_large_image(self, images: list[dict[str, Any]], page_area: float) -> bool:
        for image in images:
            bbox = image.get("bbox")
            if not bbox:
                continue
            x0, y0, x1, y1 = bbox
            image_area = max(0, x1 - x0) * max(0, y1 - y0)
            if page_area > 0 and image_area / page_area > 0.65:
                return True
        return False

    def _cross_validate_extractors(self, pdf_path: Path, pymupdf_text: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "pymupdf_chars": len(pymupdf_text),
            "pypdf_available": False,
            "pdfplumber_available": False,
        }

        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf_path))
            pypdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            result["pypdf_available"] = True
            result["pypdf_chars"] = len(pypdf_text)
            result["length_similarity"] = self._length_similarity(
                len(pymupdf_text), len(pypdf_text)
            )
        except Exception as exc:
            result["pypdf_error"] = str(exc)

        try:
            import pdfplumber

            total_chars = 0
            pages_with_chars = 0
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    chars = page.chars
                    total_chars += len(chars)
                    if chars:
                        pages_with_chars += 1
                result["pdfplumber_page_count"] = len(pdf.pages)
            result["pdfplumber_available"] = True
            result["pdfplumber_total_chars"] = total_chars
            result["pdfplumber_pages_with_chars"] = pages_with_chars
        except Exception as exc:
            result["pdfplumber_error"] = str(exc)

        return result

    def _length_similarity(self, first: int, second: int) -> float:
        if max(first, second) == 0:
            return 0.0
        return min(first, second) / max(first, second)

    def _detect_academic_markers(self, text: str) -> dict[str, bool]:
        return {
            "has_abstract": bool(re.search(r"\babstract\b", text, re.I)),
            "has_references": bool(re.search(r"\breferences\b", text, re.I)),
            "has_formula_like_lines": len(re.findall(r"[=<>+\-*/]|sum|sqrt|log", text, re.I)) > 8,
            "has_citations": bool(re.search(r"\[[0-9,\s-]{1,20}\]|\([A-Z][A-Za-z]+,\s+\d{4}\)", text)),
        }

    def _load_pymupdf(self) -> Any:
        try:
            import pymupdf

            return pymupdf
        except ImportError:
            try:
                import fitz

                return fitz
            except ImportError as exc:
                raise RuntimeError(
                    "PyMuPDF is required for PDF cleanliness checks. "
                    "Install it with: pip install pymupdf"
                ) from exc

    def _broken_report(self, pdf_path: Path, problem: str) -> PdfCleanlinessReport:
        return PdfCleanlinessReport(
            file=str(pdf_path),
            page_count=0,
            encrypted=False,
            total_text_chars=0,
            avg_text_chars_per_page=0,
            english_word_ratio=0,
            garbled_ratio=1,
            cid_marker_count=0,
            image_count=0,
            large_image_page_ratio=1,
            avg_blocks_per_page=0,
            suspected_multi_column_ratio=1,
            repeated_header_footer_candidates=0,
            paragraph_fragmentation_ratio=1,
            score=0,
            level="BROKEN",
            can_translate_phase1=False,
            problems=[problem],
            details={},
        )
