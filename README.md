# llm-translate

Structured long-document translation MVP.

The first implementation focuses on the V1.0 Markdown workflow:

1. create a project
2. parse Markdown into blocks
3. chunk by document structure
4. protect non-translatable spans
5. translate with a pluggable LLM provider
6. validate placeholders and basic structure
7. export translated and bilingual Markdown artifacts

The default provider is loaded from `.env` and is intended for DeepSeek. Local
acceptance can still run without API keys by passing `--provider mock`. Real
model calls use a LiteLLM-backed adapter, so the underlying model can be swapped
without changing the translation pipeline.

## Quick Start

```powershell
python -m llm_translate.cli init-db
python -m llm_translate.cli run fixtures\sample.md --name sample --provider mock
python -m llm_translate.cli list-projects
```

Artifacts are written under `.llm_translate/projects/{project_id}/artifacts`.

## DeepSeek Configuration

Create a `.env` file from `.env.example`:

```dotenv
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek/deepseek-chat
LLM_API_BASE=https://api.deepseek.com
LLM_API_KEY=your-api-key
```

Then run without `--provider mock`:

```powershell
python -m llm_translate.cli run docs\some-book.md --name book-zh
```
