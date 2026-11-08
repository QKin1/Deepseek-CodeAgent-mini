import json
from copy import deepcopy
import threading

from code_agent.llm.deepseek import ProviderError

from code_agent.agent.runtime import AgentRuntime


class FakeTools:
    def __init__(self):
        self.calls = []
        self.finished = False
        self.summary = "生成完成"

    @staticmethod
    def definitions():
        return [{"type": "function", "name": "write_file"}, {"type": "function", "name": "finish_task"}]

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "finish_task":
            self.finished = True
            self.summary = arguments["summary"]
        return {"ok": True}


class FakeProvider:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def create_response(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        return self.responses.pop(0)


def call(name, args, call_id):
    return {"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": call_id}


def test_agent_executes_tool_then_finishes_with_full_history():
    provider = FakeProvider([
        {"output": [call("write_file", {"path": "README.md", "content": "hello"}, "c1")]},
        {"output": [call("finish_task", {"summary": "完成 README"}, "c2")]},
    ])
    tools = FakeTools()
    result = AgentRuntime(provider).run(user_prompt="生成项目", tool_executor=tools)
    assert result.completed
    assert result.summary == "完成 README"
    assert result.tool_calls == 2
    second_history = provider.requests[1]["input_items"]
    assert any(item.get("type") == "function_call_output" and item["call_id"] == "c1" for item in second_history)


def test_agent_rejects_malformed_tool_arguments_and_recovers():
    provider = FakeProvider([
        {"output": [{"type": "function_call", "name": "write_file", "arguments": "[]", "call_id": "bad"}]},
        {"output": [call("finish_task", {"summary": "已停止。"}, "done")]},
    ])
    result = AgentRuntime(provider).run(user_prompt="x", tool_executor=FakeTools())
    assert result.completed
    tool_output = next(item for item in provider.requests[1]["input_items"] if item.get("type") == "function_call_output")
    assert "工具调用参数无效" in tool_output["output"]


def test_agent_stops_at_turn_limit_and_handles_empty_response():
    provider = FakeProvider([{"output": [call("write_file", {"path": "a", "content": "b"}, "1")]}])
    result = AgentRuntime(provider, max_turns=1).run(user_prompt="x", tool_executor=FakeTools())
    assert not result.completed
    assert "最大 Agent 轮数" in result.summary

    empty = AgentRuntime(FakeProvider([{"output": []}])).run(user_prompt="x", tool_executor=FakeTools())
    assert not empty.completed
    assert "空响应" in empty.summary


def test_retryable_provider_error_is_retried_and_context_is_bounded():
    class FastEvent(threading.Event):
        def wait(self, timeout=None):
            return self.is_set()

    class FlakyProvider:
        def __init__(self):
            self.calls = 0

        def create_response(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ProviderError("temporary", retryable=True)
            return {"output": [call("finish_task", {"summary": "done"}, "done")]}

    provider = FlakyProvider()
    result = AgentRuntime(provider).run(user_prompt="x", tool_executor=FakeTools(), cancel_event=FastEvent())
    assert provider.calls == 2
    assert result.completed

    never_called = FakeProvider([])
    bounded = AgentRuntime(never_called, max_history_bytes=1).run(user_prompt="x", tool_executor=FakeTools())
    assert not bounded.completed
    assert "上下文达到" in bounded.summary
    assert not never_called.requests
