from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from code_agent.agent.runtime import AgentResult, AgentRuntime
from code_agent.agent.tools import ToolExecutor
from code_agent.documents.parser import DocumentError, parse_architecture_documents, render_review_report
from code_agent.llm.deepseek import DeepSeekResponsesClient


def _atomic_text_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


class GenerationService:
    def __init__(self, provider_factory=DeepSeekResponsesClient):
        self.provider_factory = provider_factory

    def run(
        self,
        *,
        api_key: str,
        documentation_path: str,
        view_path: str,
        output_directory: str,
        allow_overwrite: bool = False,
        cancel_event=None,
        on_event: Callable[[str], None] | None = None,
    ) -> tuple[AgentResult, dict]:
        if on_event:
            on_event("正在检查架构文档…")
        docs = [Path(documentation_path), Path(view_path)]
        if docs[0].resolve(strict=True) == docs[1].resolve(strict=True):
            raise DocumentError("架构文档和架构视图必须是两个不同文件")
        if any(path.suffix.lower() not in {".md", ".markdown"} for path in docs):
            raise DocumentError("当前版本只支持 .md 或 .markdown 输入文件")
        output = Path(output_directory).resolve()
        output.mkdir(parents=True, exist_ok=True)
        protected_inputs = {path.resolve(strict=True) for path in docs}
        if any((output / reserved).resolve(strict=False) in protected_inputs for reserved in ("architecture.json", "architecture_review.md")):
            raise DocumentError("输出目录中的审查文件名与输入文档冲突，请选择其他输出目录")
        spec = parse_architecture_documents(docs)
        _atomic_text_write(output / "architecture.json", json.dumps(spec, ensure_ascii=False, indent=2))
        _atomic_text_write(output / "architecture_review.md", render_review_report(spec))

        compact_spec = {key: value for key, value in spec.items() if key != "source_text"}
        prompt = (
            "请根据已选架构资料生成对应软件项目的完整基础实现。"
            "必须输出完整源代码文件、依赖声明、README 和配套测试用例。"
            "请先阅读输出目录的 architecture_review.md；对冲突内容以明确的开放问题处理，不要隐藏。"
            "生成前列出文件计划；最终必须调用 finish_task。\n\n"
            f"用户选择的输入文件：{docs[0].name}、{docs[1].name}\n"
            f"目标输出目录由工具限制。\n\n结构化架构规格：\n{json.dumps(compact_spec, ensure_ascii=False, indent=2)}"
        )
        if on_event:
            on_event("结构化规格已保存，开始单 Agent 代码生成…")
        tools = ToolExecutor(input_files=docs, output_root=output, allow_overwrite=allow_overwrite)
        provider = self.provider_factory(api_key)
        result = AgentRuntime(provider).run(user_prompt=prompt, tool_executor=tools, cancel_event=cancel_event, on_event=on_event)
        return result, spec
