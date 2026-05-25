from __future__ import annotations

from pathlib import Path

from .base import FormatAdapter
from .epub import EpubFormatAdapter
from .ipynb import IpynbFormatAdapter
from .markdown import MarkdownFormatAdapter


class FormatRegistry:
    def __init__(self, adapters: list[FormatAdapter]):
        self.adapters = {adapter.format_name: adapter for adapter in adapters}

    def detect_name(self, path: Path) -> str:
        for adapter in self.adapters.values():
            if adapter.supports(path):
                return adapter.format_name
        raise ValueError(f"unsupported input format: {path.suffix}")

    def get(self, input_format: str) -> FormatAdapter:
        try:
            return self.adapters[input_format]
        except KeyError as exc:
            raise ValueError(f"unsupported input format: {input_format}") from exc


def default_format_registry(
    soft_input_tokens: int = 2200,
    max_input_tokens: int = 3000,
) -> FormatRegistry:
    return FormatRegistry(
        [
            MarkdownFormatAdapter(soft_input_tokens, max_input_tokens),
            IpynbFormatAdapter(soft_input_tokens, max_input_tokens),
            EpubFormatAdapter(soft_input_tokens, max_input_tokens),
        ]
    )
