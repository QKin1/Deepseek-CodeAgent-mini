from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from code_agent.agent.runtime import AgentResult
from code_agent.security.secrets import SecretStoreError, WindowsSecretStore
from code_agent.ui.workers import ApiTestWorker, GenerationWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeepSeek Code Agent")
        self.resize(900, 760)
        self._api_worker: ApiTestWorker | None = None
        self._task_worker: GenerationWorker | None = None
        self._secret_store = WindowsSecretStore() if os.name == "nt" else None
        self._build_ui()
        self._load_saved_key()

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        title = QLabel("Code Agent")
        title.setObjectName("title")
        subtitle = QLabel("选择架构文档，使用 DeepSeek 生成可交付的软件项目。")
        subtitle.setObjectName("subtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        api_group = QGroupBox("模型连接")
        api_layout = QGridLayout(api_group)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("粘贴 DeepSeek API Key")
        self.save_key_check = QCheckBox("在本机加密保存 Key")
        self.test_api_button = QPushButton("测试连接")
        self.clear_key_button = QPushButton("清除已保存 Key")
        self.api_status = QLabel("未连接")
        self.api_status.setObjectName("muted")
        api_layout.addWidget(QLabel("API Key"), 0, 0)
        api_layout.addWidget(self.api_key_edit, 0, 1, 1, 3)
        api_layout.addWidget(self.save_key_check, 1, 1)
        api_layout.addWidget(self.test_api_button, 1, 2)
        api_layout.addWidget(self.clear_key_button, 1, 3)
        api_layout.addWidget(self.api_status, 2, 1, 1, 3)
        outer.addWidget(api_group)

        files_group = QGroupBox("任务输入与输出")
        files_layout = QGridLayout(files_group)
        self.documentation_edit = self._add_path_row(files_layout, 0, "架构文档")
        self.view_edit = self._add_path_row(files_layout, 1, "架构视图")
        self.output_edit = self._add_path_row(files_layout, 2, "输出目录", directory=True)
        files_layout.addWidget(QLabel("模型"), 3, 0)
        model_display = QLabel("DeepSeek V4 Pro（官方 API）")
        model_display.setObjectName("muted")
        files_layout.addWidget(model_display, 3, 1, 1, 3)
        outer.addWidget(files_group)

        controls = QHBoxLayout()
        self.start_button = QPushButton("开始生成")
        self.start_button.setObjectName("primary")
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setEnabled(False)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        controls.addWidget(self.start_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.progress_bar, 1)
        outer.addLayout(controls)

        log_group = QGroupBox("任务进度")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("任务阶段、工具执行结果和错误会显示在这里。")
        log_layout.addWidget(self.log_view)
        outer.addWidget(log_group, 1)

        footer = QLabel("架构文件会发送至 DeepSeek 官方 API；请勿提交不适合外传的敏感资料。生成代码不会自动执行。")
        footer.setObjectName("muted")
        footer.setWordWrap(True)
        outer.addWidget(footer)

        self.setCentralWidget(central)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f4f7fb; color: #17263c; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 10pt; }
            QLabel#title { font-size: 22pt; font-weight: 700; color: #13233a; }
            QLabel#subtitle { color: #52657e; margin-bottom: 4px; }
            QLabel#muted { color: #65758b; }
            QGroupBox { background: white; border: 1px solid #d9e2ed; border-radius: 12px; margin-top: 10px; padding: 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; }
            QLineEdit, QPlainTextEdit { background: #fbfdff; border: 1px solid #cbd7e5; border-radius: 7px; padding: 8px; selection-background-color: #2878d0; }
            QPlainTextEdit { font-family: Consolas, 'Microsoft YaHei UI'; }
            QPushButton { background: #e8eef6; border: 1px solid #ced9e6; border-radius: 7px; padding: 8px 14px; min-height: 18px; }
            QPushButton:hover { background: #dce8f5; }
            QPushButton#primary { background: #1769c2; color: white; border-color: #1769c2; font-weight: 700; }
            QPushButton#primary:hover { background: #0e58a8; }
            QPushButton:disabled { color: #8a97a9; background: #edf1f5; }
            QProgressBar { border: none; background: #e0e8f1; border-radius: 4px; min-height: 9px; max-height: 9px; }
            QProgressBar::chunk { background: #2a83d8; border-radius: 4px; }
        """)

        self.test_api_button.clicked.connect(self._test_api)
        self.clear_key_button.clicked.connect(self._clear_saved_key)
        self.start_button.clicked.connect(self._start_task)
        self.cancel_button.clicked.connect(self._cancel_task)
        self._log("就绪。请配置 API Key 并选择两份架构文件。")

    def _add_path_row(self, layout: QGridLayout, row: int, label: str, directory: bool = False) -> QLineEdit:
        edit = QLineEdit()
        edit.setReadOnly(True)
        edit.setPlaceholderText("选择目录" if directory else "选择 Markdown 文件")
        button = QPushButton("浏览…")
        button.clicked.connect(lambda _checked=False, target=edit, is_directory=directory: self._browse(target, is_directory))
        layout.addWidget(QLabel(label), row, 0)
        layout.addWidget(edit, row, 1, 1, 2)
        layout.addWidget(button, row, 3)
        return edit

    def _browse(self, edit: QLineEdit, directory: bool) -> None:
        if directory:
            selected = QFileDialog.getExistingDirectory(self, "选择输出目录", edit.text())
        else:
            selected, _ = QFileDialog.getOpenFileName(self, "选择 Markdown 文件", edit.text(), "Markdown (*.md *.markdown);;所有文件 (*.*)")
        if selected:
            edit.setText(selected)

    def _load_saved_key(self) -> None:
        if not self._secret_store:
            self.save_key_check.setEnabled(False)
            self.clear_key_button.setEnabled(False)
            return
        try:
            saved = self._secret_store.load()
            if saved:
                self.api_key_edit.setText(saved)
                self.save_key_check.setChecked(True)
                self.api_status.setText("已从 Windows DPAPI 加密存储读取 Key")
        except SecretStoreError as exc:
            self.api_status.setText(str(exc))

    def _persist_key_after_success(self) -> None:
        if self.save_key_check.isChecked() and self._secret_store:
            try:
                self._secret_store.save(self.api_key_edit.text().strip())
                self._log("API Key 已使用当前 Windows 用户 DPAPI 加密保存。")
            except SecretStoreError as exc:
                QMessageBox.warning(self, "无法保存 Key", str(exc))

    def _test_api(self) -> None:
        key = self.api_key_edit.text().strip()
        if not key:
            QMessageBox.information(self, "需要 API Key", "请先输入 DeepSeek API Key。")
            return
        self.test_api_button.setEnabled(False)
        self.api_status.setText("正在测试连接…")
        self._api_worker = ApiTestWorker(key)
        self._api_worker.succeeded.connect(self._api_test_succeeded)
        self._api_worker.failed.connect(self._api_test_failed)
        self._api_worker.finished.connect(lambda: self.test_api_button.setEnabled(True))
        self._api_worker.start()

    def _api_test_succeeded(self, response: str) -> None:
        self.api_status.setText(f"连接成功：{response[:100]}")
        self._persist_key_after_success()
        self._log("DeepSeek API 连通性测试成功。")

    def _api_test_failed(self, message: str) -> None:
        self.api_status.setText("连接失败")
        self._log(f"API 测试失败：{message}")
        QMessageBox.warning(self, "API 测试失败", message)

    def _clear_saved_key(self) -> None:
        if not self._secret_store:
            return
        try:
            self._secret_store.delete()
            self.save_key_check.setChecked(False)
            self.api_key_edit.clear()
            self.api_status.setText("已清除本机保存的 Key")
            self._log("已删除加密保存的 API Key。")
        except SecretStoreError as exc:
            QMessageBox.warning(self, "清除失败", str(exc))

    def _start_task(self) -> None:
        key = self.api_key_edit.text().strip()
        documentation = self.documentation_edit.text().strip()
        view = self.view_edit.text().strip()
        output = self.output_edit.text().strip()
        missing = [label for label, value in (("API Key", key), ("架构文档", documentation), ("架构视图", view), ("输出目录", output)) if not value]
        if missing:
            QMessageBox.information(self, "信息不完整", "请先填写：" + "、".join(missing))
            return
        for label, path in (("架构文档", documentation), ("架构视图", view)):
            if not Path(path).is_file():
                QMessageBox.warning(self, "输入文件不存在", f"{label}不存在：\n{path}")
                return
        output_path = Path(output)
        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "输出目录不可用", str(exc))
            return
        has_files = any(output_path.iterdir())
        allow_overwrite = False
        if has_files:
            answer = QMessageBox.question(
                self,
                "输出目录已有内容",
                "Agent 将在该目录生成文件，并可能覆盖同名文件。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            allow_overwrite = True
        if self.save_key_check.isChecked() and self._secret_store:
            try:
                self._secret_store.save(key)
            except SecretStoreError as exc:
                QMessageBox.warning(self, "无法保存 Key", str(exc))
                return

        self._set_running(True)
        self._log("开始处理任务。架构内容将发送到 DeepSeek 官方 API。")
        self._task_worker = GenerationWorker(
            api_key=key,
            documentation_path=documentation,
            view_path=view,
            output_directory=output,
            allow_overwrite=allow_overwrite,
        )
        self._task_worker.progress.connect(self._log)
        self._task_worker.succeeded.connect(self._task_succeeded)
        self._task_worker.failed.connect(self._task_failed)
        self._task_worker.finished.connect(lambda: self._set_running(False))
        self._task_worker.start()

    def _cancel_task(self) -> None:
        if self._task_worker and self._task_worker.isRunning():
            self._task_worker.cancel()
            self.cancel_button.setEnabled(False)
            self._log("已请求取消；当前 API 请求返回后将停止后续 Agent 操作。")

    def _task_succeeded(self, result: AgentResult, spec: dict) -> None:
        state = "完成" if result.completed else "未完成"
        self._log(f"任务{state}：轮数 {result.turns}，工具调用 {result.tool_calls}，输入/输出 tokens {result.usage.get('input_tokens', 0)}/{result.usage.get('output_tokens', 0)}。")
        self._log(f"输出目录：{self.output_edit.text()}")
        if spec.get("conflicts"):
            self._log(f"架构审查发现 {len(spec['conflicts'])} 项冲突或缺项，详见 architecture_review.md。")
        summary = result.summary or result.final_text or "Agent 未提供摘要。"
        QMessageBox.information(self, f"任务{state}", summary[:4000])

    def _task_failed(self, message: str) -> None:
        self._log(f"任务失败：{message}")
        QMessageBox.critical(self, "任务失败", message)

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.progress_bar.setRange(0, 0) if running else self.progress_bar.setRange(0, 1)
        if not running:
            self.progress_bar.setValue(0)

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {message}")


def run_app() -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
