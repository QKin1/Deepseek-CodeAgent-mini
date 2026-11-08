from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate as validate_json

from code_agent.security.paths import PathPolicyError, ensure_safe_directory, resolve_output_path


MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_OUTPUT_TOTAL_BYTES = 30 * 1024 * 1024
MAX_OUTPUT_FILES = 200
RESERVED_FILES = {"architecture.json", "architecture_review.md"}
DEPENDENCY_MANIFESTS = {"requirements.txt", "pyproject.toml", "package.json", "cargo.toml", "go.mod", "pom.xml", "build.gradle", "composer.json"}
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".cs", ".cpp", ".c", ".html", ".css", ".vue", ".svelte"}


class ToolExecutor:
    def __init__(self, *, input_files: list[str | Path], output_root: str | Path, allow_overwrite: bool = False):
        resolved_inputs = [Path(path).resolve(strict=True) for path in input_files]
        if len({path.name.casefold() for path in resolved_inputs}) != len(resolved_inputs):
            raise ValueError("输入文件名重复，工具无法唯一识别")
        self.input_files = {path.name: path for path in resolved_inputs}
        self._protected_inputs = {os.path.normcase(os.path.abspath(str(path))) for path in resolved_inputs}
        self.output_root = Path(output_root).resolve(strict=True)
        self.allow_overwrite = allow_overwrite
        self.finished = False
        self.summary = ""

    @staticmethod
    def definitions() -> list[dict[str, Any]]:
        return [
            {
                "type": "function", "name": "read_input_file",
                "description": "读取用户本次选择的架构输入文件。只能传入界面中显示的文件名。",
                "parameters": {"type": "object", "properties": {"document_name": {"type": "string"}}, "required": ["document_name"], "additionalProperties": False},
            },
            {
                "type": "function", "name": "list_output_files",
                "description": "列出指定输出目录内已生成的文件。",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "type": "function", "name": "read_output_file",
                "description": "读取输出目录中已经生成的文本文件，用于检查或继续编辑。",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
            },
            {
                "type": "function", "name": "write_file",
                "description": "在指定输出目录内创建或重写一个文本文件。路径必须是相对路径。",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False},
            },
            {
                "type": "function", "name": "finish_task",
                "description": "结束任务并返回生成摘要、检查结果和未解决问题。",
                "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False},
            },
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            definition = next((item for item in self.definitions() if item["name"] == name), None)
            if definition is None:
                return {"ok": False, "error": f"未知工具：{name}"}
            validate_json(instance=arguments, schema=definition["parameters"])
            if name == "read_input_file":
                return self._read_input(arguments)
            if name == "list_output_files":
                return self._list_output()
            if name == "read_output_file":
                return self._read_output(arguments)
            if name == "write_file":
                return self._write_file(arguments)
            if name == "finish_task":
                summary = arguments.get("summary")
                if not isinstance(summary, str):
                    raise ValueError("summary 必须是字符串")
                missing = self._missing_artifacts()
                if missing:
                    return {"ok": False, "finished": False, "error": "交付物不完整，请补齐后再结束。", "missing_artifacts": missing}
                self.finished = True
                self.summary = summary[:8000]
                return {"ok": True, "finished": True}
            return {"ok": False, "error": f"未知工具：{name}"}
        except (ValueError, OSError, PathPolicyError, ValidationError) as exc:
            return {"ok": False, "error": str(exc)[:1000]}

    def _read_input(self, args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("document_name")
        if not isinstance(name, str) or name not in self.input_files:
            raise ValueError("只能读取本次选择的输入文件")
        path = self.input_files[name]
        data = path.read_bytes()
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError("输入文件超过 2 MiB 限制")
        return {"ok": True, "document_name": name, "content": data.decode("utf-8-sig")}

    def _list_output(self) -> dict[str, Any]:
        files = sorted(str(path.relative_to(self.output_root)).replace("\\", "/") for path in self.output_root.rglob("*") if path.is_file())
        return {"ok": True, "files": files[:MAX_OUTPUT_FILES]}

    def _read_output(self, args: dict[str, Any]) -> dict[str, Any]:
        relative = args.get("path")
        if not isinstance(relative, str):
            raise ValueError("path 必须是字符串")
        path = resolve_output_path(self.output_root, relative)
        if not path.is_file():
            raise ValueError("文件不存在")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("文件超过 1 MiB 读取限制")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("只允许读取 UTF-8 文本文件") from exc
        return {"ok": True, "path": relative, "content": content}

    def _write_file(self, args: dict[str, Any]) -> dict[str, Any]:
        relative = args.get("path")
        content = args.get("content")
        if not isinstance(relative, str) or not isinstance(content, str):
            raise ValueError("path 和 content 必须是字符串")
        if relative.replace("\\", "/").lower() in RESERVED_FILES:
            raise ValueError("architecture.json 和 architecture_review.md 是本地审查产物，不能由模型覆盖")
        payload = content.encode("utf-8")
        if len(payload) > MAX_FILE_BYTES:
            raise ValueError("单个文件超过 1 MiB 限制")
        target = resolve_output_path(self.output_root, relative)
        if os.path.normcase(os.path.abspath(str(target.resolve(strict=False)))) in self._protected_inputs:
            raise ValueError("不能覆盖本次选定的架构输入文件")
        if target.exists() and not self.allow_overwrite:
            raise ValueError(f"文件已存在且本次未授权覆盖：{relative}")
        current_files = [path for path in self.output_root.rglob("*") if path.is_file()]
        if not target.exists() and len(current_files) >= MAX_OUTPUT_FILES:
            raise ValueError("输出文件数达到 200 个限制")
        current_bytes = sum(path.stat().st_size for path in current_files if path != target)
        if current_bytes + len(payload) > MAX_OUTPUT_TOTAL_BYTES:
            raise ValueError("输出目录总大小超过 30 MiB 限制")
        parent_relative = Path(relative.replace("\\", "/")).parent.as_posix()
        if parent_relative not in {"", "."}:
            ensure_safe_directory(self.output_root, parent_relative)
        target = resolve_output_path(self.output_root, relative)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=target.parent, prefix=".codeagent-", suffix=".tmp", delete=False) as handle:
                handle.write(payload)
                temporary_path = Path(handle.name)
            os.replace(temporary_path, target)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
        return {"ok": True, "path": relative, "bytes_written": len(payload)}

    def _missing_artifacts(self) -> list[str]:
        files = [path for path in self.output_root.rglob("*") if path.is_file() and not path.is_symlink()]
        relative_files = [path.relative_to(self.output_root).as_posix() for path in files]
        lower_names = {Path(path).name.lower() for path in relative_files}
        missing: list[str] = []
        if "readme.md" not in lower_names:
            missing.append("README.md")
        if not lower_names.intersection(DEPENDENCY_MANIFESTS):
            missing.append("依赖声明文件（如 package.json 或 requirements.txt）")
        if not any(Path(path).suffix.lower() in CODE_SUFFIXES for path in relative_files):
            missing.append("至少一个项目源代码文件")
        if not any(
            "/tests/" in f"/{path.lower()}/" or Path(path).name.lower().startswith("test_") or ".test." in Path(path).name.lower()
            for path in relative_files
        ):
            missing.append("至少一个配套测试用例文件")
        return missing
