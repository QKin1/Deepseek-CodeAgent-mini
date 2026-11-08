from pathlib import Path

import pytest

from code_agent.documents.parser import DocumentError, parse_architecture_documents, render_review_report


ROOT = Path(__file__).resolve().parents[1]


def test_current_architecture_inputs_are_extracted_and_conflicts_reported():
    spec = parse_architecture_documents([
        ROOT / "Architecture_Documentation.md",
        ROOT / "Architecture_View.md",
    ])
    assert len(spec["diagrams"]) == 13
    assert "ASR-2" in {item["id"] for item in spec["requirements"]}
    assert any(item["type"] == "traceability_gap" and "ASR-2" in item["requirement_ids"] for item in spec["conflicts"])
    assert any(item["type"] == "component_view_mismatch" and "AdminComponent" in item["component_names"] for item in spec["conflicts"])
    assert set(spec["artifact_candidates"]) == {"sql/question_ddl.sql", "sql/game_ddl.sql"}
    assert any(item["type"] == "diagram_count_mismatch" and item["declared_counts"] == [11] for item in spec["conflicts"])
    assert spec["open_questions"]
    assert all(item["is_balanced"] for item in spec["diagrams"])
    report = render_review_report(spec)
    assert "traceability_gap" in report
    assert "AdminComponent" in report


def test_utf8_bom_and_unclosed_plantuml_are_supported(tmp_path: Path):
    doc = tmp_path / "arch.md"
    view = tmp_path / "view.md"
    doc.write_bytes("\ufeff# 架构\r\nFR-7: 登录\r\n".encode("utf-8"))
    view.write_text("```plantuml\n@startuml Example\nA -> B\n```\n", encoding="utf-8")
    spec = parse_architecture_documents([doc, view])
    assert spec["requirements"][0]["id"] == "FR-7"
    assert not spec["diagrams"][0]["is_balanced"]
    assert any("缺少 @startuml 或 @enduml" in warning for warning in spec["warnings"])


def test_non_utf8_and_oversized_inputs_fail(tmp_path: Path):
    invalid = tmp_path / "invalid.md"
    invalid.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(DocumentError, match="UTF-8"):
        parse_architecture_documents([invalid])

    large = tmp_path / "large.md"
    large.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(DocumentError, match="2 MiB"):
        parse_architecture_documents([large])


def test_duplicate_document_basenames_are_rejected(tmp_path: Path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    first = left / "same.md"
    second = right / "same.md"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    with pytest.raises(DocumentError, match="文件名重复"):
        parse_architecture_documents([first, second])
