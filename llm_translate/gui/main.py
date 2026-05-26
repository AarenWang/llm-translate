from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from llm_translate.gui.settings import GuiSettings, default_settings_path
from llm_translate.gui.workers import DocumentTranslationThread, TextTranslationThread
from llm_translate.llm import provider_from_name
from llm_translate.prompt import Prompt
from llm_translate.service import TranslationService


LANGUAGES = {
    "中文（简体）": "zh-CN",
    "English": "en",
    "日本語": "ja",
    "한국어": "ko",
    "Deutsch": "de",
    "Français": "fr",
    "Español": "es",
}

PROVIDERS = {
    "DeepSeek": "deepseek",
    "LiteLLM": "litellm",
    "ChatGPT": "chatgpt",
    "Mock": "mock",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings_path = default_settings_path()
        self.gui_settings = GuiSettings.load(self.settings_path)
        self.text_thread: TextTranslationThread | None = None
        self.document_thread: DocumentTranslationThread | None = None
        self.selected_document: Path | None = None
        self.artifact_paths: dict[str, str] = {}

        self.setWindowTitle("LLM Translate")
        self._apply_window_icon()
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)
        self._build_ui()
        self._apply_style()
        self._load_settings_to_controls()
        self.refresh_history()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(180)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 18, 16, 18)
        sidebar_layout.setSpacing(8)

        brand = QLabel("LLM Translate")
        brand.setObjectName("Brand")
        sidebar_layout.addWidget(brand)
        sidebar_layout.addSpacing(12)

        self.nav_buttons: list[QPushButton] = []
        for label, index in [
            ("文本翻译", 0),
            ("文档翻译", 1),
            ("翻译历史", 2),
            ("设置", 3),
        ]:
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked, page=index: self.set_page(page))
            sidebar_layout.addWidget(button)
            self.nav_buttons.append(button)
        sidebar_layout.addStretch()

        self.stack = QStackedWidget()
        self.stack.addWidget(self._text_page())
        self.stack.addWidget(self._document_page())
        self.stack.addWidget(self._history_page())
        self.stack.addWidget(self._settings_page())

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.set_page(0)

    def _text_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        top = QHBoxLayout()
        title = QLabel("文本翻译")
        title.setObjectName("PageTitle")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("源语言"))
        self.text_source_language = QComboBox()
        self.text_source_language.addItems(["自动检测", *LANGUAGES.keys()])
        top.addWidget(self.text_source_language)
        top.addWidget(QLabel("目标语言"))
        self.text_target_language = QComboBox()
        self.text_target_language.addItems(LANGUAGES.keys())
        top.addWidget(self.text_target_language)
        self.text_translate_button = QPushButton("翻译")
        self.text_translate_button.clicked.connect(self.translate_text)
        top.addWidget(self.text_translate_button)
        layout.addLayout(top)

        panes = QHBoxLayout()
        self.source_text = QPlainTextEdit()
        self.source_text.setPlaceholderText("输入或粘贴要翻译的原始文本")
        self.target_text = QPlainTextEdit()
        self.target_text.setPlaceholderText("翻译结果会显示在这里")
        self.target_text.setReadOnly(True)
        panes.addWidget(self._labeled_panel("原文", self.source_text), 1)
        panes.addWidget(self._labeled_panel("译文", self.target_text), 1)
        layout.addLayout(panes, 1)

        bottom = QHBoxLayout()
        self.text_status = QLabel("就绪")
        bottom.addWidget(self.text_status)
        bottom.addStretch()
        copy_button = QPushButton("复制结果")
        copy_button.clicked.connect(self.copy_text_result)
        clear_button = QPushButton("清空")
        clear_button.clicked.connect(self.clear_text_translation)
        bottom.addWidget(copy_button)
        bottom.addWidget(clear_button)
        layout.addLayout(bottom)
        return page

    def _document_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        title = QLabel("文档翻译")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        drop = QFrame()
        drop.setObjectName("DropZone")
        drop_layout = QVBoxLayout(drop)
        drop_layout.setContentsMargins(24, 28, 24, 28)
        drop_layout.setSpacing(10)
        hint = QLabel("选择 Markdown、DOCX、EPUB、Notebook、HTML、PDF、字幕或纯文本文件")
        hint.setAlignment(Qt.AlignCenter)
        self.document_path_label = QLabel("尚未选择文件")
        self.document_path_label.setAlignment(Qt.AlignCenter)
        choose = QPushButton("选择文件")
        choose.clicked.connect(self.choose_document)
        drop_layout.addWidget(hint)
        drop_layout.addWidget(self.document_path_label)
        drop_layout.addWidget(choose, alignment=Qt.AlignCenter)
        layout.addWidget(drop)

        form_host = QFrame()
        form_host.setObjectName("Panel")
        form = QFormLayout(form_host)
        form.setContentsMargins(18, 18, 18, 18)
        self.project_name = QLineEdit()
        self.document_target_language = QComboBox()
        self.document_target_language.addItems(LANGUAGES.keys())
        self.document_output_mode = QComboBox()
        self.document_output_mode.addItems(["译文 + 双语对照", "仅译文"])
        form.addRow("项目名称", self.project_name)
        form.addRow("目标语言", self.document_target_language)
        form.addRow("输出", self.document_output_mode)
        layout.addWidget(form_host)

        actions = QHBoxLayout()
        self.document_translate_button = QPushButton("开始翻译")
        self.document_translate_button.clicked.connect(self.translate_document)
        actions.addWidget(self.document_translate_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.document_progress = QProgressBar()
        self.document_progress.setRange(0, 100)
        layout.addWidget(self.document_progress)
        self.document_status = QLabel("等待文档")
        layout.addWidget(self.document_status)

        self.document_log = QPlainTextEdit()
        self.document_log.setReadOnly(True)
        self.document_log.setMaximumHeight(130)
        layout.addWidget(self.document_log)

        self.artifact_list = QListWidget()
        self.artifact_list.itemDoubleClicked.connect(self.open_artifact_item)
        layout.addWidget(self._labeled_panel("输出文件", self.artifact_list), 1)

        output_actions = QHBoxLayout()
        open_folder = QPushButton("打开输出目录")
        open_folder.clicked.connect(self.open_artifact_folder)
        output_actions.addStretch()
        output_actions.addWidget(open_folder)
        layout.addLayout(output_actions)
        return page

    def _history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        title = QLabel("翻译历史")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        self.history_list = QListWidget()
        layout.addWidget(self.history_list, 1)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh_history)
        layout.addWidget(refresh, alignment=Qt.AlignRight)
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        title = QLabel("设置")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        panel = QFrame()
        panel.setObjectName("Panel")
        form = QFormLayout(panel)
        form.setContentsMargins(22, 22, 22, 22)
        form.setSpacing(12)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDERS.keys())
        self.model_edit = QLineEdit()
        self.api_base_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.default_target_language = QComboBox()
        self.default_target_language.addItems(LANGUAGES.keys())
        self.workspace_edit = QLineEdit()
        self.keep_format_checkbox = QCheckBox("保留原文格式")
        self.keep_format_checkbox.setChecked(True)
        self.bilingual_checkbox = QCheckBox("生成双语对照文件")
        self.bilingual_checkbox.setChecked(True)

        form.addRow("默认供应商", self.provider_combo)
        form.addRow("模型", self.model_edit)
        form.addRow("API Base", self.api_base_edit)
        form.addRow("API Key", self.api_key_edit)
        form.addRow("默认目标语言", self.default_target_language)
        form.addRow("工作区", self.workspace_edit)
        form.addRow("文档策略", self.keep_format_checkbox)
        form.addRow("", self.bilingual_checkbox)
        layout.addWidget(panel)

        actions = QHBoxLayout()
        test_button = QPushButton("测试连接")
        test_button.clicked.connect(self.test_provider)
        save_button = QPushButton("保存设置")
        save_button.clicked.connect(self.save_settings)
        actions.addStretch()
        actions.addWidget(test_button)
        actions.addWidget(save_button)
        layout.addLayout(actions)
        layout.addStretch()
        return page

    def _labeled_panel(self, title: str, child: QWidget) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 14)
        label = QLabel(title)
        label.setObjectName("PanelTitle")
        layout.addWidget(label)
        layout.addWidget(child)
        return panel

    def set_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        if index == 2:
            self.refresh_history()

    def translate_text(self) -> None:
        source = self.source_text.toPlainText().strip()
        if not source:
            QMessageBox.information(self, "提示", "请先输入原始文本。")
            return
        target = self._combo_language_value(self.text_target_language)
        self.save_settings(silent=True, sync_targets=False)
        self.text_translate_button.setEnabled(False)
        self.text_status.setText("正在翻译...")
        self.target_text.clear()
        self.text_thread = TextTranslationThread(source, target, self.gui_settings)
        self.text_thread.status_changed.connect(self.text_status.setText)
        self.text_thread.finished_ok.connect(self.on_text_translated)
        self.text_thread.failed.connect(self.on_text_failed)
        self.text_thread.finished.connect(lambda: self.text_translate_button.setEnabled(True))
        self.text_thread.start()

    def on_text_translated(self, text: str) -> None:
        self.target_text.setPlainText(text)
        self.text_status.setText("完成")

    def on_text_failed(self, detail: str) -> None:
        self.text_status.setText("翻译失败")
        QMessageBox.critical(self, "翻译失败", detail)

    def copy_text_result(self) -> None:
        QApplication.clipboard().setText(self.target_text.toPlainText())
        self.text_status.setText("已复制")

    def clear_text_translation(self) -> None:
        self.source_text.clear()
        self.target_text.clear()
        self.text_status.setText("就绪")

    def choose_document(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择要翻译的文档",
            str(Path.cwd()),
            "Documents (*.md *.markdown *.docx *.epub *.ipynb *.html *.htm *.pdf *.txt *.srt *.vtt *.tex);;All files (*.*)",
        )
        if not path:
            return
        self.selected_document = Path(path)
        self.document_path_label.setText(str(self.selected_document))
        if not self.project_name.text().strip():
            self.project_name.setText(self.selected_document.stem)

    def translate_document(self) -> None:
        if self.selected_document is None:
            QMessageBox.information(self, "提示", "请先选择要翻译的文档。")
            return
        project_name = self.project_name.text().strip() or self.selected_document.stem
        target = self._combo_language_value(self.document_target_language)
        self.save_settings(silent=True, sync_targets=False)
        self.artifact_list.clear()
        self.artifact_paths.clear()
        self.document_log.clear()
        self.document_progress.setValue(0)
        self.document_translate_button.setEnabled(False)
        self.document_thread = DocumentTranslationThread(
            self.selected_document,
            project_name,
            target,
            self.gui_settings,
        )
        self.document_thread.status_changed.connect(self.on_document_status)
        self.document_thread.log_line.connect(self.document_log.appendPlainText)
        self.document_thread.finished_ok.connect(self.on_document_finished)
        self.document_thread.failed.connect(self.on_document_failed)
        self.document_thread.finished.connect(lambda: self.document_translate_button.setEnabled(True))
        self.document_thread.start()

    def on_document_status(self, status: str, progress: int) -> None:
        self.document_status.setText(status)
        self.document_progress.setValue(progress)

    def on_document_finished(self, project_id: str, artifacts: dict) -> None:
        self.artifact_paths = dict(artifacts)
        self.artifact_list.clear()
        for name, path in self.artifact_paths.items():
            item = QListWidgetItem(f"{name}: {path}")
            item.setData(Qt.UserRole, path)
            self.artifact_list.addItem(item)
        self.document_status.setText(f"完成: {project_id}")
        self.refresh_history()

    def on_document_failed(self, detail: str) -> None:
        self.document_status.setText("翻译失败")
        QMessageBox.critical(self, "文档翻译失败", detail)
        self.refresh_history()

    def open_artifact_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_artifact_folder(self) -> None:
        first = next(iter(self.artifact_paths.values()), "")
        if not first:
            QMessageBox.information(self, "提示", "还没有可打开的输出目录。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(first).parent)))

    def refresh_history(self) -> None:
        if not hasattr(self, "history_list"):
            return
        try:
            service = TranslationService(self.gui_settings.to_service_settings())
            service.init_db()
            projects = service.store.list_projects()
        except Exception:
            projects = []
        self.history_list.clear()
        for project in projects:
            total = project.get("total_chunks") or 0
            done = project.get("done_chunks") or 0
            failed = project.get("failed_chunks") or 0
            text = (
                f"{project['name']}  |  {project['status']}  |  "
                f"{done}/{total} 完成, {failed} 异常  |  {project['source_file_name']}"
            )
            self.history_list.addItem(text)

    def test_provider(self) -> None:
        self.save_settings(silent=True)
        try:
            provider = provider_from_name(
                self.gui_settings.provider,
                model_name=self.gui_settings.model or None,
                api_base=self.gui_settings.api_base or None,
                api_key=self.gui_settings.api_key or None,
            )
            prompt = Prompt(
                system="You are a translation engine. Return translated text only.",
                user="Translate to zh-CN: Hello",
            )
            result = provider.translate(prompt)
            QMessageBox.information(self, "连接成功", result[:500] or "供应商已响应。")
        except Exception as exc:
            QMessageBox.critical(self, "连接失败", str(exc))

    def save_settings(self, silent: bool = False, sync_targets: bool = True) -> None:
        self.gui_settings = GuiSettings(
            provider=PROVIDERS[self.provider_combo.currentText()],
            model=self.model_edit.text().strip(),
            api_base=self.api_base_edit.text().strip(),
            api_key=self.api_key_edit.text().strip(),
            target_language=self._combo_language_value(self.default_target_language),
            workspace_path=self.workspace_edit.text().strip() or ".llm_translate",
        )
        self.gui_settings.save(self.settings_path)
        if sync_targets:
            self._sync_target_language_controls()
        if not silent:
            QMessageBox.information(self, "已保存", "设置已保存。")

    def _load_settings_to_controls(self) -> None:
        self._set_combo_by_value(self.provider_combo, PROVIDERS, self.gui_settings.provider)
        self.model_edit.setText(self.gui_settings.model or "")
        self.api_base_edit.setText(self.gui_settings.api_base or "")
        self.api_key_edit.setText(self.gui_settings.api_key or "")
        self.workspace_edit.setText(self.gui_settings.workspace_path or ".llm_translate")
        self._set_language_combo(self.default_target_language, self.gui_settings.target_language)
        self._sync_target_language_controls()

    def _sync_target_language_controls(self) -> None:
        self._set_language_combo(self.text_target_language, self.gui_settings.target_language)
        self._set_language_combo(self.document_target_language, self.gui_settings.target_language)

    def _combo_language_value(self, combo: QComboBox) -> str:
        return LANGUAGES.get(combo.currentText(), self.gui_settings.target_language)

    def _set_language_combo(self, combo: QComboBox, code: str) -> None:
        for label, value in LANGUAGES.items():
            if value == code:
                combo.setCurrentText(label)
                return

    def _set_combo_by_value(self, combo: QComboBox, values: dict[str, str], current: str) -> None:
        for label, value in values.items():
            if value == current:
                combo.setCurrentText(label)
                return

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 13px;
                color: #1f2933;
                background: #f6f7f9;
            }
            #Sidebar {
                background: #202833;
            }
            #Sidebar QLabel {
                color: #ffffff;
                background: transparent;
            }
            #Brand {
                font-size: 20px;
                font-weight: 700;
            }
            #Sidebar QPushButton {
                color: #d9e2ec;
                background: transparent;
                border: 0;
                border-radius: 6px;
                padding: 10px 12px;
                text-align: left;
            }
            #Sidebar QPushButton:hover {
                background: #2f3b49;
            }
            #Sidebar QPushButton:checked {
                color: #ffffff;
                background: #3b82f6;
            }
            #PageTitle {
                font-size: 24px;
                font-weight: 700;
                color: #111827;
            }
            #Panel, #DropZone {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                border-radius: 8px;
            }
            #DropZone {
                border-style: dashed;
            }
            #PanelTitle {
                color: #52606d;
                font-weight: 600;
                background: transparent;
            }
            QPlainTextEdit, QLineEdit, QComboBox, QListWidget {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 7px;
                selection-background-color: #bfdbfe;
            }
            QPlainTextEdit {
                line-height: 1.35;
            }
            QPushButton {
                background: #2563eb;
                color: #ffffff;
                border: 0;
                border-radius: 6px;
                padding: 8px 14px;
                min-width: 84px;
            }
            QPushButton:hover {
                background: #1d4ed8;
            }
            QPushButton:disabled {
                background: #94a3b8;
            }
            QProgressBar {
                background: #e5e7eb;
                border: 0;
                border-radius: 5px;
                height: 10px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #10b981;
                border-radius: 5px;
            }
            """
        )

    def _apply_window_icon(self) -> None:
        icon_path = _asset_path("assets/app_icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))


def launch_gui() -> int:
    if "--bundle-data-smoke-test" in sys.argv:
        if hasattr(sys, "_MEIPASS"):
            litellm_dir = Path(sys._MEIPASS) / "litellm"
        else:
            import litellm

            litellm_dir = Path(litellm.__file__).parent
        required = litellm_dir / "model_prices_and_context_window_backup.json"
        return 0 if required.exists() else 2

    if "--tokenizer-smoke-test" in sys.argv:
        import tiktoken

        tiktoken.get_encoding("cl100k_base")
        return 0

    if "--icon-smoke-test" in sys.argv:
        return 0 if _asset_path("assets/app_icon.ico").exists() else 3

    _set_windows_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName("LLM Translate")
    app.setApplicationDisplayName("LLM Translate")
    app.setOrganizationName("LLM Translate")
    icon_path = _asset_path("assets/app_icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    if "--smoke-test" in sys.argv:
        window.close()
        return 0
    window.show()
    return app.exec()


def _asset_path(relative_path: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parents[2] / relative_path


def _set_windows_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        app_id = "LLMTranslate.Desktop.TranslateClient"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


if __name__ == "__main__":
    raise SystemExit(launch_gui())
