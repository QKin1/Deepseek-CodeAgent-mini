import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from code_agent.ui.main_window import MainWindow


def test_main_window_builds_without_loading_user_credentials(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    assert window.windowTitle() == "DeepSeek Code Agent"
    assert window.api_key_edit.echoMode() == window.api_key_edit.EchoMode.Password
    assert not window.documentation_edit.text()
    assert not window.view_edit.text()
    window.close()
