from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath


class PathPolicyError(ValueError):
    pass


def resolve_output_path(root: str | Path, relative_path: str) -> Path:
    """Resolve a model-provided relative path without allowing root escape."""
    if not relative_path or "\x00" in relative_path:
        raise PathPolicyError("文件路径不能为空或包含 NUL")
    normalized = relative_path.replace("\\", "/")
    windows_path = PureWindowsPath(relative_path)
    candidate_part = Path(normalized)
    if candidate_part.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        raise PathPolicyError("只允许输出目录内的相对路径")
    parts = normalized.split("/")
    if any(part in {"..", ".", ""} for part in parts):
        raise PathPolicyError("路径包含非法目录跳转")
    reserved_names = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    for part in parts:
        if ":" in part or part.endswith((".", " ")) or part.split(".", 1)[0].upper() in reserved_names:
            raise PathPolicyError("路径包含 Windows 保留名称或非法字符")

    root_path = Path(root).resolve(strict=True)
    target = root_path.joinpath(*normalized.split("/"))
    resolved = target.resolve(strict=False)
    root_norm = os.path.normcase(os.path.abspath(str(root_path)))
    target_norm = os.path.normcase(os.path.abspath(str(resolved)))
    try:
        common = os.path.commonpath([root_norm, target_norm])
    except ValueError as exc:
        raise PathPolicyError("目标路径与输出目录不在同一卷") from exc
    if common != root_norm:
        raise PathPolicyError("目标路径超出指定输出目录")

    cursor = root_path
    for part in normalized.split("/"):
        cursor = cursor / part
        if cursor.exists() and (cursor.is_symlink() or getattr(cursor, "is_junction", lambda: False)()):
            raise PathPolicyError("不允许通过符号链接或 junction 写入")
    return target


def ensure_safe_directory(root: str | Path, relative_path: str) -> Path:
    target = resolve_output_path(root, relative_path)
    target.mkdir(parents=True, exist_ok=True)
    # Re-check after creation to cover a path replaced between validation and mkdir.
    return resolve_output_path(root, relative_path)
