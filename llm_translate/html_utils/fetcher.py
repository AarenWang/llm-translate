"""HTML content fetcher module."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class HTMLContentFetcher(Protocol):
    """HTML content fetcher interface."""

    def fetch(self, source: str) -> str:
        """Fetch HTML content.

        Args:
            source: HTML content source, can be local file path or URL

        Returns:
            HTML content string

        Raises:
            FileNotFoundError: When local file doesn't exist
            RequestException: When network request fails
        """
        ...


class LocalHTMLFetcher:
    """Local HTML file fetcher."""

    def fetch(self, source: str) -> str:
        """Read HTML file from local file system.

        Args:
            source: Local HTML file path

        Returns:
            HTML content string

        Raises:
            FileNotFoundError: When file doesn't exist
            UnicodeDecodeError: When file encoding has issues
        """
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"HTML file not found: {source}")

        # Try multiple encodings
        encodings = ["utf-8", "gbk", "gb2312", "latin-1"]
        for encoding in encodings:
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue

        # If all encodings fail, use utf-8 and ignore errors
        return path.read_text(encoding="utf-8", errors="ignore")


class URLFetcher:
    """URL fetcher for static web pages."""

    def fetch(self, source: str) -> str:
        """Fetch static web page content via URL.

        Args:
            source: Web page URL

        Returns:
            HTML content string

        Raises:
            RequestException: When network request fails
        """
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests library is required for URL fetching. "
                "Install it with: pip install requests"
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
            )
        }

        response = requests.get(source, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text