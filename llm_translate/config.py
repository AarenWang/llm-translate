from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    database_path: Path
    workspace_path: Path
    llm_provider: str = "deepseek"
    llm_model: str | None = None
    llm_api_base: str | None = None
    llm_api_key: str | None = None
    default_target_language: str = "zh-CN"
    soft_input_tokens: int = 2200
    max_input_tokens: int = 3000
    max_retry_count: int = 3
    prompt_version: str = "prompt-v1"
    glossary_version: str = "glossary-v1"
    style_guide_version: str = "style-v1"
    protection_policy_version: str = "protection-v1"

    @classmethod
    def from_env(cls) -> "Settings":
        env = load_dotenv(Path(".env"))
        workspace = Path(os.getenv("LLM_TRANSLATE_WORKSPACE", ".llm_translate"))
        database = Path(os.getenv("LLM_TRANSLATE_DB", workspace / "translate.db"))
        return cls(
            database_path=database,
            workspace_path=workspace,
            llm_provider=_first(env, "LLM_PROVIDER", "DEEPSEEK_PROVIDER") or "deepseek",
            llm_model=_first(env, "LLM_MODEL", "DEEPSEEK_MODEL"),
            llm_api_base=_first(env, "LLM_API_BASE", "LLM_BASE_URL", "DEEPSEEK_API_BASE", "DEEPSEEK_BASE_URL"),
            llm_api_key=_first(env, "LLM_API_KEY", "DEEPSEEK_API_KEY"),
        )


def load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
        os.environ.setdefault(key.strip(), value)
    return values


def _first(env: Mapping[str, str], *keys: str) -> str | None:
    for key in keys:
        value = os.getenv(key) or env.get(key)
        if value:
            return value
    return None


DEFAULT_STYLE_GUIDE = (
    "Translate into clear, professional Simplified Chinese for technical "
    "readers. Preserve Markdown structure. Keep terminology consistent with "
    "the glossary. Do not add commentary or expand beyond the source."
)
