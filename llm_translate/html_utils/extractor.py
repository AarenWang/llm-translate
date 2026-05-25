"""HTML core content extractor module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtractedContent:
    """Extracted web page core content.

    Attributes:
        title: Web page title
        author: Author information
        date: Publication date
        text: Extracted main text content
        raw_html: Original HTML content
        metadata: Additional metadata
    """

    title: str | None
    author: str | None
    date: str | None
    text: str
    raw_html: str
    metadata: dict[str, Any]


class HTMLContentExtractor:
    """HTML core content extractor using Trafilatura to extract web page main content.

    This class wraps the Trafilatura library to provide core content extraction from HTML.
    """

    def __init__(
        self,
        include_comments: bool = False,
        include_tables: bool = True,
        favor_precision: bool = True,
    ):
        """Initialize HTML content extractor.

        Args:
            include_comments: Whether to include comment content
            include_tables: Whether to include table content
            favor_precision: Whether to prioritize precision (extract less but more accurately)
        """
        self.include_comments = include_comments
        self.include_tables = include_tables
        self.favor_precision = favor_precision

    def extract(self, html: str, url: str | None = None) -> ExtractedContent:
        """Extract core content from HTML.

        Args:
            html: HTML content string
            url: Optional original URL for relative link resolution

        Returns:
            ExtractedContent object containing extracted core content
        """
        try:
            import trafilatura
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError(
                "trafilatura library is required for HTML content extraction. "
                "Install it with: pip install trafilatura beautifulsoup4"
            )

        # Pre-process HTML to preserve code blocks through trafilatura's
        # whitespace normalization.
        html, code_blocks = self._preserve_code_blocks(html)

        # Use trafilatura for structured extraction
        result = trafilatura.bare_extraction(
            html,
            url=url,
            include_comments=self.include_comments,
            include_tables=self.include_tables,
            favor_precision=self.favor_precision,
            no_fallback=False,  # Allow fallback extraction methods
        )

        # Check extraction results
        # trafilatura.bare_extraction returns a Document object
        if not result or not result.text:
            # If structured extraction fails, use basic text extraction as fallback
            text = trafilatura.extract(
                html,
                include_comments=self.include_comments,
                include_tables=self.include_tables,
                favor_precision=self.favor_precision,
            )

            processed_text = self._restore_code_block_placeholders(text or "", code_blocks)
            return ExtractedContent(
                title=None,
                author=None,
                date=None,
                text=processed_text,
                raw_html=html,
                metadata={"extraction_method": "fallback"},
            )

        # Extraction successful, build result object
        # Post-process to restore code block markers
        processed_text = self._restore_code_block_placeholders(result.text or "", code_blocks)
        if not code_blocks:
            processed_text = self._restore_code_block_markers(processed_text)

        # Access Document object attributes
        return ExtractedContent(
            title=result.title,
            author=result.author,
            date=result.date,
            text=processed_text,
            raw_html=html,
            metadata={
                "language": result.language,
                "url": result.url,
                "hostname": result.hostname,
                "description": result.description,
                "categories": result.categories,
                "tags": result.tags,
                "extraction_method": "structured_with_code_blocks",
            },
        )

    def _preserve_code_blocks(self, html: str) -> tuple[str, dict[str, str]]:
        """Pre-process HTML to preserve code block structure.

        Args:
            html: Original HTML content

        Returns:
            Tuple of processed HTML and placeholder-to-Markdown-code mapping
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, 'html.parser')
        code_blocks: dict[str, str] = {}

        # Find all astro-code blocks
        pre_tags = soup.find_all('pre', class_=lambda x: x and 'astro-code' in ' '.join(x) if isinstance(x, list) else 'astro-code' in str(x))

        for i, pre in enumerate(pre_tags):
            # Extract code language
            language = pre.get('data-language', 'python')  # Default to python

            # Extract code content
            code_tag = pre.find('code')
            if code_tag:
                # Get all text content, preserving line structure
                code_lines = []
                for line in code_tag.find_all('span', class_='line'):
                    line_text = line.get_text(strip=False)
                    code_lines.append(line_text)

                code_text = '\n'.join(code_lines)

                # Store a Markdown-style code block behind a stable text marker.
                # Plain text nodes with embedded newlines are normalized by
                # trafilatura, so the marker must be restored after extraction.
                markdown_code = f"```{language}\n{code_text}\n```"
                placeholder = f"LLM_TRANSLATE_CODE_BLOCK_{i + 1:06d}"
                code_blocks[placeholder] = markdown_code

                new_node = soup.new_tag("p")
                new_node.string = placeholder
                pre.replace_with(new_node)

        return str(soup), code_blocks

    def _restore_code_block_placeholders(self, text: str, code_blocks: dict[str, str]) -> str:
        """Restore fenced code blocks that were protected before extraction."""
        restored = text
        for placeholder, code_block in code_blocks.items():
            restored = restored.replace(placeholder, f"\n{code_block}\n")
        return restored

    def _restore_code_block_markers(self, text: str) -> str:
        """Restore and fix code block markers in extracted text.

        Args:
            text: Text extracted by trafilatura

        Returns:
            Text with properly formatted code blocks
        """
        import re

        # Look for patterns that indicate code but might be missing markers
        lines = text.split('\n')
        result = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Detect common code patterns
            code_patterns = [
                r'^\s*(async\s+)?def\s+\w+\s*\(',  # Python function definitions
                r'^\s*class\s+\w+.*:',  # Python class definitions
                r'^\s*import\s+\w+',  # Python imports
                r'^\s*from\s+\w+\s+import',  # Python from imports
                r'^\s*\w+\s*=\s*\w+\(',  # Object assignments
                r'^\s*await\s+\w+',  # Async calls
                r'^\s*if\s+__name__\s*==\s*["\']__main__["\']',  # Main guard
            ]

            # Check if this line looks like code
            is_code = any(re.match(pattern, line) for pattern in code_patterns)

            if is_code:
                # Look ahead to see if there are more code lines
                code_lines = [line]
                j = i + 1

                while j < len(lines):
                    next_line = lines[j].strip()
                    # Continue if next line looks like code or is empty
                    if not next_line or any(
                        re.match(pattern, lines[j]) for pattern in code_patterns
                    ) or next_line.startswith(('"""', "'''", '#', '    ', '\t')):
                        code_lines.append(lines[j])
                        j += 1
                    else:
                        break

                # Determine language from content
                language = self._detect_code_language('\n'.join(code_lines))

                # Add code block markers if not already present
                if not result or result[-1].strip() != '```':
                    result.append(f"```{language}")

                result.extend(code_lines)

                if j < len(lines) and lines[j].strip() != '```':
                    result.append("```")

                i = j - 1  # Will be incremented to j

            result.append(line)
            i += 1

        return '\n'.join(result)

    def _detect_code_language(self, code: str) -> str:
        """Detect programming language from code content.

        Args:
            code: Code content

        Returns:
            Detected language identifier
        """
        if 'def ' in code or 'import ' in code or 'class ' in code:
            return 'python'
        elif 'function ' in code or 'const ' in code or 'let ' in code:
            return 'javascript'
        elif '{' in code and '}' in code and ';' in code:
            return 'c'
        else:
            return 'python'  # Default to python for this context
