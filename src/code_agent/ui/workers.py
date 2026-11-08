from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from code_agent.application.service import GenerationService
from code_agent.llm.deepseek import DeepSeekResponsesClient


class ApiTestWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key

    def run(self) -> None:
        try:
            result = DeepSeekResponsesClient(self.api_key).test_connection()
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class GenerationWorker(QThread):
    progress = Signal(str)
    succeeded = Signal(object, object)
    failed = Signal(str)

    def __init__(self, *, api_key: str, documentation_path: str, view_path: str, output_directory: str, allow_overwrite: bool):
        super().__init__()
        self.api_key = api_key
        self.documentation_path = documentation_path
        self.view_path = view_path
        self.output_directory = output_directory
        self.allow_overwrite = allow_overwrite
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result, spec = GenerationService().run(
                api_key=self.api_key,
                documentation_path=self.documentation_path,
                view_path=self.view_path,
                output_directory=self.output_directory,
                allow_overwrite=self.allow_overwrite,
                cancel_event=self.cancel_event,
                on_event=self.progress.emit,
            )
            self.succeeded.emit(result, spec)
        except Exception as exc:
            self.failed.emit(str(exc))
