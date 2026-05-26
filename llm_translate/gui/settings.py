from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from llm_translate.config import Settings


@dataclass
class GuiSettings:
    provider: str = "deepseek"
    model: str = "deepseek/deepseek-chat"
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    target_language: str = "zh-CN"
    workspace_path: str = ".llm_translate"

    @classmethod
    def load(cls, path: Path) -> "GuiSettings":
        if not path.exists():
            env_settings = Settings.from_env()
            return cls(
                provider=env_settings.llm_provider,
                model=env_settings.llm_model or "deepseek/deepseek-chat",
                api_base=env_settings.llm_api_base or "https://api.deepseek.com",
                api_key=env_settings.llm_api_key or "",
                target_language=env_settings.default_target_language,
                workspace_path=str(env_settings.workspace_path),
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{**asdict(cls()), **data})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    def to_service_settings(self) -> Settings:
        workspace = Path(self.workspace_path or ".llm_translate")
        return Settings(
            database_path=workspace / "translate.db",
            workspace_path=workspace,
            llm_provider=self.provider,
            llm_model=self.model or None,
            llm_api_base=self.api_base or None,
            llm_api_key=self.api_key or None,
            default_target_language=self.target_language,
        )


def default_settings_path() -> Path:
    return Path(".llm_translate") / "gui_settings.json"

