from __future__ import annotations

from pathlib import Path
import traceback

from PySide6.QtCore import QThread, Signal

from llm_translate.config import DEFAULT_STYLE_GUIDE
from llm_translate.gui.settings import GuiSettings
from llm_translate.llm import provider_from_name
from llm_translate.prompt import PromptBuilder
from llm_translate.protection import ProtectionEngine
from llm_translate.service import TranslationService


class TextTranslationThread(QThread):
    status_changed = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, source_text: str, target_language: str, settings: GuiSettings):
        super().__init__()
        self.source_text = source_text
        self.target_language = target_language
        self.settings = settings

    def run(self) -> None:
        try:
            self.status_changed.emit("正在保护文本片段...")
            protected = ProtectionEngine().protect("quick_text", "quick_text_chunk", self.source_text)
            prompt = (
                PromptBuilder()
                .add_style_guide(DEFAULT_STYLE_GUIDE)
                .add_translation_prompt(
                    protected.protected_text,
                    document_format="plain_text",
                    target_language=self.target_language,
                )
                .add_glossary([])
                .build()
            )

            self.status_changed.emit("正在调用模型翻译...")
            provider = provider_from_name(
                self.settings.provider,
                model_name=self.settings.model or None,
                api_base=self.settings.api_base or None,
                api_key=self.settings.api_key or None,
            )
            translated = provider.translate(prompt)
            restored = ProtectionEngine().restore(translated, protected.spans)
            self.finished_ok.emit(restored)
        except Exception:
            self.failed.emit(traceback.format_exc())


class DocumentTranslationThread(QThread):
    status_changed = Signal(str, int)
    log_line = Signal(str)
    finished_ok = Signal(str, dict)
    failed = Signal(str)

    def __init__(
        self,
        source_path: Path,
        project_name: str,
        target_language: str,
        settings: GuiSettings,
    ):
        super().__init__()
        self.source_path = source_path
        self.project_name = project_name
        self.target_language = target_language
        self.settings = settings

    def run(self) -> None:
        project_id = ""
        try:
            service = TranslationService(self.settings.to_service_settings())
            provider = provider_from_name(
                self.settings.provider,
                model_name=self.settings.model or None,
                api_base=self.settings.api_base or None,
                api_key=self.settings.api_key or None,
            )

            self.status_changed.emit("创建项目", 8)
            project = service.create_project(
                self.source_path,
                self.project_name,
                target_language=self.target_language,
            )
            project_id = project.id
            self.log_line.emit(f"项目已创建: {project.id}")

            self.status_changed.emit("解析文档结构", 22)
            service.parse_project(project.id)
            self.log_line.emit("解析完成")

            self.status_changed.emit("规划翻译分块", 35)
            service.prepare_project(project.id)
            chunks = service.store.list_chunks(project.id)
            self.log_line.emit(f"已生成 {len(chunks)} 个翻译块")

            self.status_changed.emit("调用模型翻译文档", 45)
            service.translate_project(project.id, provider, enable_batching=False)
            self.log_line.emit("翻译完成，正在导出")

            self.status_changed.emit("生成输出文件", 90)
            artifacts = service.export_project(project.id)
            payload = {name: str(path) for name, path in artifacts.items()}
            self.status_changed.emit("完成", 100)
            self.finished_ok.emit(project.id, payload)
        except Exception:
            if project_id:
                self.log_line.emit(f"项目保留在工作区，可稍后重试: {project_id}")
            self.failed.emit(traceback.format_exc())
