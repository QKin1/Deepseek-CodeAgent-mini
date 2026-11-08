from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from jsonschema import validate as validate_json


MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
REQUIREMENT_ID = re.compile(r"\b(?:FR|NFR|ASR|SEC|DR)-\d+\b", re.IGNORECASE)
COMPONENT_NAME = re.compile(r"\b[A-Z][A-Za-z0-9]*Component\b")
DDL_PATH = re.compile(r"(?<![\w.-])(?:[\w.-]+/)*[\w.-]*ddl[\w.-]*\.sql\b", re.IGNORECASE)
FENCE_OPEN = re.compile(r"^\s*```\s*([\w+-]*)\s*$")


class DocumentError(ValueError):
    """Raised when an input document cannot safely be read."""


def _read_document(path: Path) -> tuple[str, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DocumentError(f"无法读取文件 {path.name}: {exc}") from exc
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise DocumentError(f"文件 {path.name} 超过 2 MiB 限制")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentError(f"文件 {path.name} 不是有效的 UTF-8 文本") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n"), hashlib.sha256(raw).hexdigest()


def _section_at(lines: list[str], index: int) -> str:
    for cursor in range(index, -1, -1):
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", lines[cursor])
        if match:
            return match.group(1).strip()
    return "(文档开头)"


def _extract_fenced_blocks(name: str, lines: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    blocks: list[dict[str, Any]] = []
    warnings: list[str] = []
    index = 0
    while index < len(lines):
        match = FENCE_OPEN.match(lines[index])
        if not match:
            index += 1
            continue
        language = match.group(1).lower()
        start_line = index + 1
        content_lines: list[str] = []
        index += 1
        while index < len(lines) and not re.match(r"^\s*```\s*$", lines[index]):
            content_lines.append(lines[index])
            index += 1
        if index == len(lines):
            warnings.append(f"{name}:{start_line}: 代码围栏未闭合")
            break
        content = "\n".join(content_lines)
        looks_like_plantuml = language in {"plantuml", "puml"} or "@startuml" in content.lower()
        if looks_like_plantuml:
            title_match = re.search(r"@startuml\s+([^\s]+)?", content, flags=re.IGNORECASE)
            title = title_match.group(1) if title_match and title_match.group(1) else f"diagram_{len(blocks) + 1}"
            blocks.append({
                "name": title,
                "language": language or "plantuml",
                "source_file": name,
                "line_start": start_line,
                "line_end": index + 1,
                "source": content,
                "is_balanced": "@startuml" in content.lower() and "@enduml" in content.lower(),
            })
            if "@startuml" not in content.lower() or "@enduml" not in content.lower():
                warnings.append(f"{name}:{start_line}: PlantUML 块缺少 @startuml 或 @enduml")
        index += 1
    return blocks, warnings


def _requirements(documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    found: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for document in documents:
        lines = document["text"].splitlines()
        in_traceability = False
        matrix_section = ""
        for number, line in enumerate(lines, 1):
            heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
            if heading:
                in_traceability = bool(re.search(r"traceability|追踪|可追溯", heading.group(1), re.IGNORECASE))
                matrix_section = heading.group(1) if in_traceability else ""
            ids = REQUIREMENT_ID.findall(line)
            for raw_id in ids:
                req_id = raw_id.upper()
                item = found.setdefault(req_id, {
                    "id": req_id,
                    "mentions": [],
                    "in_traceability_matrix": False,
                    "traceability_section": None,
                })
                item["mentions"].append({
                    "source_file": document["name"],
                    "section": _section_at(lines, number - 1),
                    "line": number,
                    "text": line.strip()[:500],
                })
                if in_traceability and "|" in line:
                    item["in_traceability_matrix"] = True
                    item["traceability_section"] = matrix_section
        missing = sorted(req_id for req_id, item in found.items() if not item["in_traceability_matrix"])
        if missing:
            conflicts.append({
                "type": "traceability_gap",
                "source_file": document["name"],
                "message": "发现正文中提及但未在需求追踪表中识别到的 ID。",
                "requirement_ids": missing,
            })
    return list(found.values()), conflicts


def _overview_components(documents: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    overview: set[str] = set()
    in_diagrams: set[str] = set()
    for document in documents:
        text = document["text"]
        match = re.search(
            r"(?:^|\n)\s*#{0,3}\s*(?:[A-Z]\.\s*)?(?:Architecture Overview|架构概览)(.*?)(?=\n\s*#{1,3}\s|\Z)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            overview.update(COMPONENT_NAME.findall(match.group(1)))
        for block in document["diagrams"]:
            in_diagrams.update(COMPONENT_NAME.findall(block["source"]))
    return overview, in_diagrams


def _extract_open_questions(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for document in documents:
        lines = document["text"].splitlines()
        active = False
        for number, line in enumerate(lines, 1):
            heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
            if heading:
                active = bool(re.search(r"open questions|unresolved|待确认|开放问题", heading.group(1), re.IGNORECASE))
            if active and re.match(r"^\s*[-*+]\s+", line):
                questions.append({"source_file": document["name"], "line": number, "text": line.strip()[1:].strip()})
    return questions


def parse_architecture_documents(document_paths: list[str | Path]) -> dict[str, Any]:
    if not document_paths:
        raise DocumentError("至少需要选择一份架构文档")
    basenames = [Path(path).name.casefold() for path in document_paths]
    if len(set(basenames)) != len(basenames):
        raise DocumentError("输入文件名重复，请选择名称不同的文档")
    documents: list[dict[str, Any]] = []
    warnings: list[str] = []
    diagrams: list[dict[str, Any]] = []
    for raw_path in document_paths:
        path = Path(raw_path)
        text, digest = _read_document(path)
        lines = text.splitlines()
        blocks, block_warnings = _extract_fenced_blocks(path.name, lines)
        warnings.extend(block_warnings)
        document = {
            "name": path.name,
            "sha256": digest,
            "line_count": len(lines),
            "text": text,
            "diagrams": blocks,
        }
        documents.append(document)
        diagrams.extend(blocks)

    requirements, conflicts = _requirements(documents)
    overview_components, diagram_components = _overview_components(documents)
    missing_components = sorted(diagram_components - overview_components)
    if missing_components:
        conflicts.append({
            "type": "component_view_mismatch",
            "message": "组件图中出现但架构概览中未列出的组件。",
            "component_names": missing_components,
        })

    ddl_paths: set[str] = set()
    for document in documents:
        ddl_paths.update(DDL_PATH.findall(document["text"]))
    if len(ddl_paths) > 1:
        conflicts.append({
            "type": "artifact_name_mismatch",
            "message": "文档中提到多个 DDL 文件名，请确认最终交付名称。",
            "paths": sorted(ddl_paths),
        })

    all_components = sorted(overview_components | diagram_components)
    open_questions = _extract_open_questions(documents)
    declared_diagram_counts: set[int] = set()
    for document in documents:
        declared_diagram_counts.update(
            int(match.group(1))
            for match in re.finditer(r"\b(\d+)\s+(?:PlantUML|UML)\s+(?:diagrams?|图)", document["text"], re.IGNORECASE)
        )
    if declared_diagram_counts and any(count != len(diagrams) for count in declared_diagram_counts):
        conflicts.append({
            "type": "diagram_count_mismatch",
            "message": "文档声明的图数量与实际提取的 PlantUML 图块数量不一致。",
            "declared_counts": sorted(declared_diagram_counts),
            "extracted_count": len(diagrams),
        })
    result = {
        "schema_version": "1.0",
        "source_documents": [
            {key: value for key, value in document.items() if key not in {"text", "diagrams"}}
            for document in documents
        ],
        "requirements": requirements,
        "components": [{"name": name} for name in all_components],
        "diagrams": diagrams,
        "traceability": [
            {"requirement_id": item["id"], "included": item["in_traceability_matrix"]}
            for item in requirements
        ],
        "artifact_candidates": sorted(ddl_paths),
        "open_questions": open_questions,
        "conflicts": conflicts,
        "warnings": warnings,
        "source_text": {document["name"]: document["text"] for document in documents},
    }
    from .schema import ARCHITECTURE_SCHEMA
    validate_json(instance=result, schema=ARCHITECTURE_SCHEMA)
    return result


def render_review_report(spec: dict[str, Any]) -> str:
    lines = [
        "# 架构输入审查报告",
        "",
        "本报告由本地确定性检查生成。报告指出文档线索，不会替用户裁定架构冲突。",
        "",
        "## 输入文件",
    ]
    for document in spec["source_documents"]:
        lines.append(f"- `{document['name']}`：{document['line_count']} 行，SHA-256 `{document['sha256'][:12]}`")
    lines.extend(["", "## PlantUML 图块"])
    if spec["diagrams"]:
        lines.extend(f"- `{item['name']}`：{item['source_file']}:{item['line_start']}，平衡={item['is_balanced']}" for item in spec["diagrams"])
    else:
        lines.append("- 未识别到 PlantUML fenced block。")
    lines.extend(["", "## 冲突与缺项"])
    if spec["conflicts"]:
        for conflict in spec["conflicts"]:
            details = []
            if conflict.get("requirement_ids"):
                details.append("ID: " + ", ".join(conflict["requirement_ids"]))
            if conflict.get("component_names"):
                details.append("组件: " + ", ".join(conflict["component_names"]))
            if conflict.get("paths"):
                details.append("路径: " + ", ".join(f"`{path}`" for path in conflict["paths"]))
            if conflict.get("declared_counts") is not None:
                details.append(f"文档声明 {conflict['declared_counts']}，实际提取 {conflict.get('extracted_count')} 个")
            suffix = f"（{'；'.join(details)}）" if details else ""
            lines.append(f"- **{conflict['type']}**：{conflict['message']}{suffix}")
    else:
        lines.append("- 未检测到规则化冲突；这不代表架构已经完整或正确。")
    lines.extend(["", "## 开放问题"])
    if spec["open_questions"]:
        for item in spec["open_questions"]:
            lines.append(f"- {item['text']}（{item['source_file']}:{item['line']}）")
    else:
        lines.append("- 未识别到开放问题列表。")
    if spec["warnings"]:
        lines.extend(["", "## 解析警告"])
        lines.extend(f"- {warning}" for warning in spec["warnings"])
    lines.extend(["", "## 需求 ID"])
    if spec["requirements"]:
        lines.extend(
            f"- `{item['id']}`：追踪表中{'已识别' if item['in_traceability_matrix'] else '未识别'}，提及 {len(item['mentions'])} 次。"
            for item in spec["requirements"]
        )
    else:
        lines.append("- 未识别到标准需求 ID（FR/NFR/ASR/SEC/DR-n）。")
    return "\n".join(lines) + "\n"
