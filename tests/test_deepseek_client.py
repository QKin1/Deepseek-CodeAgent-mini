import json

import httpx
import pytest

from code_agent.llm.deepseek import DeepSeekResponsesClient, ProviderError, response_text


def test_client_sends_expected_responses_payload_and_extracts_text():
    recorded = {}

    def handler(request):
        recorded["auth"] = request.headers["Authorization"]
        recorded["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]})

    transport = httpx.MockTransport(handler)
    client = DeepSeekResponsesClient("test-key", transport=transport)
    response = client.create_response(instructions="test", input_items="hello", tools=[{"type": "function", "name": "x"}])
    assert recorded["auth"] == "Bearer test-key"
    assert recorded["body"]["model"] == "deepseek-v4-pro"
    assert recorded["body"]["tool_choice"] == "auto"
    assert response_text(response) == "OK"


def test_client_redacts_key_from_api_error():
    def handler(_request):
        return httpx.Response(401, json={"error": {"message": "invalid test-secret"}})

    client = DeepSeekResponsesClient("test-secret", transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as error:
        client.create_response(instructions="test", input_items="hello")
    assert "test-secret" not in str(error.value)
    assert "[已隐藏]" in str(error.value)
    assert error.value.status_code == 401


def test_connection_probe_uses_small_non_reasoning_request():
    recorded = {}

    def handler(request):
        recorded["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]})

    client = DeepSeekResponsesClient("test-key", transport=httpx.MockTransport(handler))
    assert client.test_connection() == "OK"
    assert recorded["body"]["max_output_tokens"] == 256
    assert recorded["body"]["reasoning"] == {"effort": "none"}
    assert "tools" not in recorded["body"]


@pytest.mark.parametrize(
    ("reason", "message_fragment"),
    [
        ("max_output_tokens", "已达到输出 token 上限"),
        ("content_filter", "响应触发内容过滤"),
    ],
)
def test_client_explains_incomplete_response_reason(reason, message_fragment):
    response_body = {
        "status": "incomplete",
        "incomplete_details": {"reason": reason},
        "usage": {"output_tokens": 256, "output_tokens_details": {"reasoning_tokens": 0}},
        "output": [],
    }
    client = DeepSeekResponsesClient(
        "test-key",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=response_body)),
    )

    with pytest.raises(ProviderError) as error:
        client.test_connection()

    assert message_fragment in str(error.value)
    assert f"reason={reason}" in str(error.value)
    assert "输出 tokens=256" in str(error.value)
