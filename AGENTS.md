# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a structured long-document translation system that supports Markdown, Jupyter Notebooks (`.ipynb`), EPUB, and DOCX formats. The architecture uses a **plugin-based format adapter system** where each format implements a common `FormatAdapter` protocol, allowing the core translation pipeline to remain format-agnostic.

### Core Translation Flow

```
Input File → FormatAdapter.detect() → FormatAdapter.parse() → DocumentBlock[]
→ FormatAdapter.plan_chunks() → TranslationChunk[] → ProtectionEngine.protect()
→ LLMProvider.translate() → ProtectionEngine.restore() → ValidationEngine.validate()
→ FormatAdapter.export() → Artifacts (translated file, bilingual comparison, logs)
```

The system is designed around **DocumentBlocks** (atomic translatable units) and **TranslationChunks** (groups of blocks sent together to the LLM for efficiency while preserving document structure).

## Document Translation Testing

**Important**: When testing document translation functionality, always use the CLI interface rather than writing custom test scripts. The CLI provides the complete translation pipeline including state management, error handling, and artifact generation that test scripts cannot replicate accurately.

### CLI Testing Examples

```bash
# Quick translation testing (uses configured provider from .env)
python -m llm_translate.cli run path/to/document.md --name test-project
python -m llm_translate.cli run path/to/document.docx --name test-docx
python -m llm_translate.cli run path/to/notebook.ipynb --name test-notebook
python -m llm_translate.cli run path/to/book.epub --name test-epub

# Step-by-step workflow for debugging
python -m llm_translate.cli create path/to/document.docx --name "Debug Test" --target-language zh
python -m llm_translate.cli parse <project_id>          # Check parsing output
python -m llm_translate.cli prepare <project_id>         # Check chunk creation
python -m llm_translate.cli translate <project_id>       # Test translation with real provider
python -m llm_translate.cli export <project_id>          # Generate artifacts

# Explicit provider selection
python -m llm_translate.cli translate <project_id> --provider litellm

# Using different environment configurations
python -m llm_translate.cli --env bigmodel translate <project_id>

# Project management
python -m llm_translate.cli list-projects               # View all projects
```

**Why CLI over custom scripts?**
- Complete state machine management (CREATED → PARSED → READY → TRANSLATING → EXPORTED)
- Proper SQLite persistence and project isolation
- Full artifact generation (translated file, bilingual comparison, validation reports, logs)
- Format-specific validation and error handling
- Consistent chunking and protection policies

**Artifacts Location**: All outputs are written to `.llm_translate/projects/<project_id>/artifacts/`

## Development Commands
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_docx_parser.py

# Run specific test
python -m pytest tests/test_docx_parser.py::DocxParserTest::test_code_detection -xvs

# Run tests for specific module
python -m pytest tests/test_epub_pipeline.py -v
```

### CLI Workflow (Primary Development Interface)
```bash
# Initialize database
python -m llm_translate.cli init-db

# Full translation workflow (parse → prepare → translate → export)
python -m llm_translate.cli run <file> --name <project-name> --provider mock

# Step-by-step workflow
python -m llm_translate.cli create <file> --name "Project Name" --target-language zh
python -m llm_translate.cli parse <project_id>
python -m llm_translate.cli prepare <project_id>
python -m llm_translate.cli translate <project_id> --provider litellm
python -m llm_translate.cli export <project_id>

# List projects
python -m llm_translate.cli list-projects
```

### Environment Configuration
The system uses `.env` files for configuration. Create from `.env.example`:
```bash
# For DeepSeek (default)
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek/deepseek-chat
LLM_API_BASE=https://api.deepseek.com
LLM_API_KEY=your-key

# Alternative environments
python -m llm_translate.cli --env bigmodel translate <project_id>
```

## Architecture Key Points

### Format Adapter Protocol (Critical)
All format support is implemented through the `FormatAdapter` protocol in `llm_translate/formats/base.py`. When adding new format support or modifying existing formats, implement these methods:

- `supports(path: Path) -> bool` - File format detection
- `parse(project, context) -> list[DocumentBlock]` - Extract translatable content
- `plan_chunks(project_id, blocks) -> list[TranslationChunk]` - Create translation chunks
- `prompt_document_format() -> str` - Describe format for LLM context
- `export(project, context, blocks, chunks, reports, draft) -> tuple[dict, list, bool]` - Generate outputs

**Important**: The core `TranslationService` should never contain format-specific logic. All format concerns belong in format adapters.

### Domain Model Architecture
The system uses a clear separation of concerns:

- **DocumentBlock**: Atomic translatable units with metadata (format-specific structure)
- **TranslationChunk**: Groups of blocks sent together to LLM (optimizes token usage)
- **ProtectedSpan**: Non-translatable content (URLs, code blocks, etc.) replaced with placeholders
- **ValidationReport**: Quality checks for placeholder integrity and structure preservation

### Chunking Strategy
The `ChunkingEngine` in `chunking.py` implements format-aware chunking:

- **Markdown/IPYNB**: Generic chunking with heading-based chapter breaks
- **IPYNB**: Cell-level chunking with translatable cell detection
- **DOCX**: Paragraph-level chunking with heading hierarchy preservation

Chunking respects token limits (`soft_input_tokens: 2200`, `max_input_tokens: 3000`) and document structure (headings, chapters).

### Protection System
The `ProtectionEngine` protects non-translatable content using regex-based pattern matching:

- **Placeholders**: Format: `__LT_<TYPE>_<SEQUENCE>__` (e.g., `__LT_URL_000001__`)
- **Protected Types**: Code blocks, HTML tags, inline code, image paths, URLs, API paths, file paths
- **Restoration**: After translation, placeholders are replaced with original content

Format adapters can add format-specific protection patterns by extending the base protection logic.

### LLM Provider Integration
The system supports pluggable LLM providers through the `LLMProvider` protocol:

- **mock**: Returns source text (for testing)
- **litellm**: Generic LiteLLM integration (supports 100+ models)
- **deepseek**: Specialized DeepSeek provider

Providers are selected via `--provider` flag or environment configuration.

## Implementation Patterns

### Adding New Format Support
1. Create format adapter in `llm_translate/formats/<format>.py`
2. Implement `FormatAdapter` protocol
3. Add parser to extract format-specific structure
4. Implement format-specific chunking strategy if needed
5. Create exporter to generate translated files
6. Add to `default_format_registry()` in `formats/registry.py`
7. Create comprehensive tests in `tests/test_<format>_*.py`

### Testing Strategy
- **Unit tests**: Test individual components (parsers, exporters, validators)
- **Integration tests**: Test full format pipelines (e.g., `test_epub_pipeline.py`)
- **Real-world tests**: Test with actual documents in project structure

Current test coverage includes:
- `test_docx_*.py`: DOCX format (31 tests)
- `test_epub_*.py`: EPUB format
- `test_ipynb_*.py`: Jupyter Notebook format
- `test_pipeline.py`: Core translation pipeline

### Error Handling and State Management
Projects use a state machine with statuses: `CREATED → PARSED → READY → TRANSLATING → COMPLETED → EXPORTED`. The `TranslationService` enforces valid state transitions and stores all state in SQLite via `SQLiteStore`.

### Code Quality Standards
- Use `from __future__ import annotations` for forward compatibility
- Prefer dataclasses for value objects
- Use `StrEnum` for status enums
- Format metadata as `dict[str, Any]` with format-specific keys
- Include comprehensive docstrings for public APIs

## Important File Locations

- **Core service**: `llm_translate/service.py` - Main translation orchestration
- **Domain model**: `llm_translate/domain.py` - Core data structures
- **Format adapters**: `llm_translate/formats/` - Format-specific implementations
- **Parsers**: `llm_translate/parser/` - Format parsing logic
- **Chunking**: `llm_translate/chunking.py` - Chunk creation logic
- **Protection**: `llm_translate/protection.py` - Content protection engine
- **Validation**: `llm_translate/validation.py` - Quality validation
- **CLI**: `llm_translate/cli.py` - Command-line interface
- **Storage**: `llm_translate/storage.py` - SQLite persistence

## Current Format Support Status

- ✅ **Markdown**: Full support with code block protection
- ✅ **Jupyter Notebooks**: Preserves code cells, outputs, metadata, attachments
- ✅ **EPUB**: Preserves container structure, spine, resources, images
- ✅ **DOCX**: Full support with paragraph/heading/table extraction and preservation

All formats produce: translated file, bilingual comparison, translation log, validation reports.
