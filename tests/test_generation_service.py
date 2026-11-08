import json
from pathlib import Path

import pytest

from code_agent.application.service import GenerationService
from code_agent.documents.parser import DocumentError


class FakeProvider:
    def __init__(self, _api_key):
        self.calls = 0

    def create_response(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"output": [
                {"type": "function_call", "name": "write_file", "arguments": json.dumps({"path": "README.md", "content": "# Space Fractions"}), "call_id": "1"},
                {"type": "function_call", "name": "write_file", "arguments": json.dumps({"path": "package.json", "content": "{}"}), "call_id": "2"},
                {"type": "function_call", "name": "write_file", "arguments": json.dumps({"path": "src/index.js", "content": "export const start = () => true;"}), "call_id": "3"},
                {"type": "function_call", "name": "write_file", "arguments": json.dumps({"path": "tests/index.test.js", "content": "test('start', () => {});"}), "call_id": "4"},
            ]}
        return {"output": [
            {"type": "function_call", "name": "finish_task", "arguments": json.dumps({"summary": "基础项目已生成。"}), "call_id": "5"}
        ]}


def test_generation_service_parses_specs_and_generates_project(tmp_path: Path):
    architecture = tmp_path / "Architecture_Documentation.md"
    view = tmp_path / "Architecture_View.md"
    output = tmp_path / "generated"
    architecture.write_text("# Demo\n## Requirements\nFR-1: Start the app\n", encoding="utf-8")
    view.write_text("```plantuml\n@startuml Demo\nA -> B\n@enduml\n```\n", encoding="utf-8")

    result, spec = GenerationService(FakeProvider).run(
        api_key="fake",
        documentation_path=str(architecture),
        view_path=str(view),
        output_directory=str(output),
    )

    assert result.completed
    assert result.summary == "基础项目已生成。"
    assert spec["requirements"][0]["id"] == "FR-1"
    assert (output / "architecture.json").is_file()
    assert (output / "architecture_review.md").is_file()
    assert (output / "README.md").read_text(encoding="utf-8") == "# Space Fractions"
    assert (output / "src" / "index.js").exists()


def test_service_refuses_to_overwrite_input_with_reserved_report_name(tmp_path: Path):
    architecture = tmp_path / "Architecture_Documentation.md"
    view = tmp_path / "architecture_review.md"
    architecture.write_text("# Demo", encoding="utf-8")
    view.write_text("# UML", encoding="utf-8")
    with pytest.raises(DocumentError, match="文件名与输入文档冲突"):
        GenerationService(FakeProvider).run(
            api_key="fake",
            documentation_path=str(architecture),
            view_path=str(view),
            output_directory=str(tmp_path),
        )
    assert view.read_text(encoding="utf-8") == "# UML"
