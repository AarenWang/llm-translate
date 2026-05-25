from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable
from uuid import uuid4

from .domain import ProtectedSpan


PLACEHOLDER_RE = re.compile(r"__LT_[A-Z_]+_\d{6}__")


@dataclass
class ProtectionResult:
    protected_text: str
    spans: list[ProtectedSpan]


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    span_type: str


class ProtectionEngine:
    def protect(self, project_id: str, chunk_id: str, text: str) -> ProtectionResult:
        matches = self._collect_matches(text)
        accepted: list[Match] = []
        last_end = -1
        for match in sorted(matches, key=lambda item: (item.start, -(item.end - item.start))):
            if match.start < last_end:
                continue
            accepted.append(match)
            last_end = match.end

        spans: list[ProtectedSpan] = []
        cursor = 0
        parts: list[str] = []
        for sequence, match in enumerate(accepted, start=1):
            placeholder = f"__LT_{match.span_type}_{sequence:06d}__"
            original = text[match.start : match.end]
            parts.append(text[cursor : match.start])
            parts.append(placeholder)
            spans.append(
                ProtectedSpan(
                    id=f"ps_{uuid4().hex}",
                    project_id=project_id,
                    chunk_id=chunk_id,
                    placeholder=placeholder,
                    span_type=match.span_type,
                    original_text=original,
                    start_offset=match.start,
                    end_offset=match.end,
                )
            )
            cursor = match.end
        parts.append(text[cursor:])
        return ProtectionResult(protected_text="".join(parts), spans=spans)

    def restore(self, text: str, spans: Iterable[ProtectedSpan]) -> str:
        restored = text
        for span in spans:
            restored = restored.replace(span.placeholder, span.original_text)
        return restored

    def placeholders(self, text: str) -> set[str]:
        return set(PLACEHOLDER_RE.findall(text or ""))

    def _collect_matches(self, text: str) -> list[Match]:
        patterns: list[tuple[str, str]] = [
            ("CODE_BLOCK", r"```[\s\S]*?```|~~~[\s\S]*?~~~"),
            ("HTML_BLOCK", r"<([A-Za-z][A-Za-z0-9:-]*)(?:\s[^>]*)?>[\s\S]*?</\1>"),
            ("HTML_TAG", r"<[^>\n]+>"),
            ("INLINE_CODE", r"`[^`\n]+`"),
            ("IMAGE_PATH", r"!\[[^\]]*\]\(([^)\s]+)\)"),
            ("LINK_TARGET", r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)"),
            ("URL", r"https?://[^\s)>\]]+"),
            ("REF", r"\[\^?[A-Za-z0-9_.:-]+\]"),
            ("API_PATH", r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[A-Za-z0-9_./{}:-]+"),
            ("FILE_PATH", r"(?<!\w)(?:[A-Za-z]:\\[^\s`]+|/[A-Za-z0-9_./-]+|\./[A-Za-z0-9_./-]+)"),
        ]
        matches: list[Match] = []
        for span_type, pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.MULTILINE):
                if span_type == "HTML_BLOCK" and "```" in match.group(0):
                    continue
                if span_type in {"IMAGE_PATH", "LINK_TARGET"} and match.lastindex:
                    matches.append(Match(match.start(1), match.end(1), span_type))
                else:
                    matches.append(Match(match.start(), match.end(), span_type))
        return matches
