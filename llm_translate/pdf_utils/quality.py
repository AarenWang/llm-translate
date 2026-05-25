"""Text quality checking utilities for PDF processing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class CidReport:
    """Report for CID character detection."""

    cid_count: int
    cid_ratio: float
    severity: str
    can_translate: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "cid_count": self.cid_count,
            "cid_ratio": self.cid_ratio,
            "severity": self.severity,
            "can_translate": self.can_translate,
        }


class CidResolver:
    """CID character identification and handling."""

    def __init__(self, max_cid_ratio: float = 0.01):
        self.max_cid_ratio = max_cid_ratio

    def detect_cid_issues(self, text: str) -> CidReport:
        """Detect CID character problems in text."""
        cid_pattern = r"\(cid:\d+\)"
        cid_matches = re.findall(cid_pattern, text)
        total_words = len(text.split()) if text.strip() else 1

        cid_count = len(cid_matches)
        cid_ratio = cid_count / max(1, total_words)
        severity = self.assess_severity(cid_count, text)
        can_translate = severity != "critical"

        return CidReport(
            cid_count=cid_count,
            cid_ratio=cid_ratio,
            severity=severity,
            can_translate=can_translate,
        )

    def assess_severity(self, cid_count: int, text: str) -> str:
        """Assess severity of CID issues."""
        if cid_count == 0:
            return "none"
        elif cid_count <= 3:
            return "minor"
        elif cid_count <= 10:
            return "moderate"
        else:
            return "critical"

    def has_critical_cid_issues(self, text: str) -> bool:
        """Check if text has critical CID issues."""
        report = self.detect_cid_issues(text)
        return report.severity == "critical"

    def clean_cid_markers(self, text: str) -> str:
        """Clean CID markers from text."""
        cid_pattern = r"\(cid:\d+\)"
        return re.sub(cid_pattern, "[UNKNOWN_CHAR]", text)


class TextQualityChecker:
    """Check text quality for translation suitability."""

    def __init__(self):
        self.cid_resolver = CidResolver()

    def check_text_quality(self, text: str) -> dict[str, Any]:
        """Comprehensive text quality check."""
        return {
            "cid_report": self.cid_resolver.detect_cid_issues(text).to_dict(),
            "garbled_ratio": self._calculate_garbled_ratio(text),
            "printable_ratio": self._calculate_printable_ratio(text),
            "avg_word_length": self._calculate_avg_word_length(text),
            "can_translate": self._can_translate(text),
        }

    def _calculate_garbled_ratio(self, text: str) -> float:
        """Calculate ratio of garbled characters."""
        if not text:
            return 1.0

        garbled_chars = 0
        for ch in text:
            code = ord(ch)
            if ch == "�":  # Unicode replacement character
                garbled_chars += 1
            elif 0xE000 <= code <= 0xF8FF:  # Private use area
                garbled_chars += 1
            elif code < 32 and ch not in "\n\r\t":  # Control characters
                garbled_chars += 1

        return garbled_chars / max(1, len(text))

    def _calculate_printable_ratio(self, text: str) -> float:
        """Calculate ratio of printable characters."""
        if not text:
            return 0.0

        printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t")
        return printable / max(1, len(text))

    def _calculate_avg_word_length(self, text: str) -> float:
        """Calculate average word length."""
        words = text.split()
        if not words:
            return 0.0

        total_length = sum(len(word.strip(".,!?;:\"'")) for word in words)
        return total_length / len(words)

    def _can_translate(self, text: str) -> bool:
        """Check if text is suitable for translation."""
        cid_report = self.cid_resolver.detect_cid_issues(text)
        garbled_ratio = self._calculate_garbled_ratio(text)

        return (
            cid_report.severity != "critical"
            and garbled_ratio < 0.1
            and self._calculate_printable_ratio(text) > 0.8
        )
