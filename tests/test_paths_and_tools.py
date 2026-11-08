from pathlib import Path

import pytest

from code_agent.agent.tools import ToolExecutor
from code_agent.security.paths import PathPolicyError, resolve_output_path


def test_output_paths_reject_escape_and_windows_special_names(tmp_path: Path):
    root = tmp_path / "output"
    root.mkdir()
    for path in ("../outside.txt", "C:\\outside.txt", "\\\\server\\share\\x", "foo/./bar", "CON.txt", "dir/aux", "x:stream"):
        with pytest.raises(PathPolicyError):
            resolve_output_path(root, path)


def test_output_paths_allow_unicode_spaces_and_dot_in_directory_name(tmp_path: Path):
    root = tmp_path / "output"
    root.mkdir()
    target = resolve_output_path(root, "子目录 v1.2/hello world.md")
    assert target == root / "子目录 v1.2" / "hello world.md"


def test_symlink_escape_is_rejected(tmp_path: Path):
    root = tmp_path / "output"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "jump"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("当前环境不允许创建 symlink")
    with pytest.raises(PathPolicyError):
        resolve_output_path(root, "jump/file.txt")


def test_tools_read_only_selected_inputs_and_write_only_below_output(tmp_path: Path):
    source = tmp_path / "source.md"
    source.write_text("架构内容", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    tools = ToolExecutor(input_files=[source], output_root=output)

    assert tools.execute("read_input_file", {"document_name": "source.md"})["content"] == "架构内容"
    assert not tools.execute("read_input_file", {"document_name": "other.md"})["ok"]
    created = tools.execute("write_file", {"path": "sub.dir/hello.md", "content": "你好"})
    assert created["ok"]
    assert (output / "sub.dir" / "hello.md").read_text(encoding="utf-8") == "你好"
    assert not tools.execute("write_file", {"path": "../escaped.txt", "content": "bad"})["ok"]
    assert not (tmp_path / "escaped.txt").exists()
    assert not tools.execute("write_file", {"path": "architecture.json", "content": "{}"})["ok"]
    assert tools.execute("read_output_file", {"path": "sub.dir/hello.md"})["content"] == "你好"


def test_tools_do_not_overwrite_without_permission(tmp_path: Path):
    source = tmp_path / "source.md"
    source.write_text("x", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    (output / "README.md").write_text("original", encoding="utf-8")
    tools = ToolExecutor(input_files=[source], output_root=output)
    result = tools.execute("write_file", {"path": "README.md", "content": "replacement"})
    assert not result["ok"]
    assert (output / "README.md").read_text(encoding="utf-8") == "original"
    assert not tools.execute("list_output_files", {"unexpected": True})["ok"]


def test_tools_cannot_overwrite_selected_input_even_with_overwrite_permission(tmp_path: Path):
    source = tmp_path / "source.md"
    source.write_text("keep", encoding="utf-8")
    tools = ToolExecutor(input_files=[source], output_root=tmp_path, allow_overwrite=True)
    result = tools.execute("write_file", {"path": "source.md", "content": "replace"})
    assert not result["ok"]
    assert source.read_text(encoding="utf-8") == "keep"


def test_finish_task_requires_readme_code_dependency_and_tests(tmp_path: Path):
    output = tmp_path / "output"
    output.mkdir()
    source = tmp_path / "source.md"
    source.write_text("x", encoding="utf-8")
    tools = ToolExecutor(input_files=[source], output_root=output)
    result = tools.execute("finish_task", {"summary": "done"})
    assert not result["ok"]
    assert set(result["missing_artifacts"]) == {
        "README.md", "依赖声明文件（如 package.json 或 requirements.txt）", "至少一个项目源代码文件", "至少一个配套测试用例文件"
    }
    for name, content in {
        "README.md": "# Demo",
        "package.json": "{}",
        "src/index.js": "console.log('x')",
        "tests/index.test.js": "test('x')",
    }.items():
        assert tools.execute("write_file", {"path": name, "content": content})["ok"]
    result = tools.execute("finish_task", {"summary": "done"})
    assert result["finished"] and tools.finished
