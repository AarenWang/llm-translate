# llm-translate

`llm-translate` is a structured long-document translation workflow for Markdown, Jupyter Notebook, EPUB, DOCX, and HTML files. It preserves document structure by parsing source files into format-aware blocks, translating only natural-language content, and restoring protected code, links, paths, and placeholders after model calls. It writes reproducible project artifacts, including translated outputs, bilingual review files, translation logs, and validation reports.

## Supported Formats

- **Markdown (`.md`)**: Translates headings, paragraphs, lists, and tables while protecting code fences, inline code, URLs, file paths, and Markdown link targets. Exports `translated.md`, `bilingual.md`, `translation-log.json`, and validation reports.
- **Jupyter Notebook (`.ipynb`)**: Translates Markdown cells while preserving code cells, outputs, metadata, attachments, and cell structure. Exports both notebook artifacts (`translated.ipynb` or draft variants) and Markdown review artifacts.
- **EPUB (`.epub`)**: Translates XHTML text nodes from spine documents while preserving the EPUB container, manifest resources, links, images, and protected code/pre content. Exports `translated.epub` plus Markdown review and validation artifacts.
- **DOCX (`.docx`)**: Translates paragraphs, headings, and table content while preserving document structure and Word packaging. Exports translated DOCX artifacts together with bilingual review and validation files.
- **HTML (`.html`, `.htm`)**: Translates main DOM text nodes and writes them back into the original HTML so CSS, links, images, scripts, classes, IDs, and page layout are retained. When a browser-saved companion resource folder such as `<page>_files` exists, it is copied into the project source and exported artifacts so `translated.html` can load local assets.

## Internal Workflow

Each run creates an isolated project, copies the source file, detects the format adapter, parses the document into `DocumentBlock` records, and plans `TranslationChunk` requests. Before translation, the protection engine replaces non-translatable spans with placeholders; after the LLM response, placeholders are restored and chunk-level validation checks structural integrity. Finally, the format adapter exports translated files and review artifacts under `.llm_translate/projects/{project_id}/artifacts/`.

## Quick Start

```powershell
python -m llm_translate.cli init-db
python -m llm_translate.cli run fixtures\sample.md --name quick-start --provider mock
python -m llm_translate.cli list-projects
```

The `mock` provider does not perform real translation; it is useful for verifying parsing, chunking, validation, and artifact generation. To run a real provider, configure `.env` or an alternate environment file and omit `--provider mock`.

```powershell
python -m llm_translate.cli --env bigmodel run path\to\document.html --name quick-start
python -m llm_translate.cli --env bigmodel run path\to\document.docx --name quick-start-docx
python -m llm_translate.cli --env bigmodel run path\to\book.epub --name quick-start-epub
python -m llm_translate.cli --env bigmodel run path\to\notebook.ipynb --name quick-start-notebook
```

## Step-by-Step Workflow

```powershell
python -m llm_translate.cli create path\to\document.html --name quick-start --target-language zh-CN
python -m llm_translate.cli parse <project_id>
python -m llm_translate.cli prepare <project_id>
python -m llm_translate.cli translate <project_id>
python -m llm_translate.cli export <project_id>
```

## Environment Configuration

Create a `.env` file from `.env.example`:

```dotenv
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek/deepseek-chat
LLM_API_BASE=https://api.deepseek.com
LLM_API_KEY=your-api-key
```

Alternate environment files use the `.env-<name>` convention:

```powershell
python -m llm_translate.cli --env bigmodel run path\to\document.md --name quick-start
```
