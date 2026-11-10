from __future__ import annotations

import json
from typing import Any

import httpx


API_URL = "https://api.deepseek.com/responses"
MODEL_ID = "deepseek-v4-pro"
DEFAULT_MAX_OUTPUT_TOKENS = 65_536


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class DeepSeekResponsesClient:
    def __init__(self, api_key: str, *, timeout: float = 90.0, base_url: str = API_URL, transport: httpx.BaseTransport | None = None):
        if not api_key.strip():
            raise ProviderError("请先配置 DeepSeek API Key")
        self._api_key = api_key.strip()
        self._timeout = timeout
        self._base_url = base_url
        self._transport = transport

    def create_response(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]] | str,
        tools: list[dict[str, Any]] | None = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        reasoning_effort: str = "high",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": MODEL_ID,
            "instructions": instructions,
            "input": input_items,
            "max_output_tokens": max_output_tokens,
            "reasoning": {"effort": reasoning_effort},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    self._base_url,
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("DeepSeek 请求超时，请检查网络后重试", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"无法连接 DeepSeek API：{type(exc).__name__}", retryable=True) from exc

        if response.status_code >= 400:
            message = "DeepSeek API 请求失败"
            try:
                body = response.json()
                message = body.get("error", {}).get("message") or body.get("message") or message
            except (ValueError, AttributeError):
                pass
            safe_message = str(message).replace(self._api_key, "[已隐藏]")[:500]
            retryable = response.status_code == 429 or response.status_code >= 500
            raise ProviderError(f"{safe_message}（HTTP {response.status_code}）", status_code=response.status_code, retryable=retryable)
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("DeepSeek 返回了无效 JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("output"), list):
            raise ProviderError("DeepSeek 响应缺少 output 列表")
        status = data.get("status")
        if status == "incomplete":
            details = data.get("incomplete_details")
            reason = details.get("reason") if isinstance(details, dict) else None
            usage = data.get("usage") or {}
            output_tokens = usage.get("output_tokens")
            token_details = usage.get("output_tokens_details") or {}
            reasoning_tokens = token_details.get("reasoning_tokens") if isinstance(token_details, dict) else None
            reason_text = {
                "max_output_tokens": "已达到输出 token 上限",
                "content_filter": "响应触发内容过滤",
            }.get(reason, "服务端未提供具体原因")
            usage_text = ""
            if isinstance(output_tokens, int):
                usage_text = f"；输出 tokens={output_tokens}"
                if isinstance(reasoning_tokens, int):
                    usage_text += f"（其中推理 tokens={reasoning_tokens}）"
            raise ProviderError(
                f"DeepSeek 响应不完整：{reason_text}（reason={reason or 'unknown'}）{usage_text}"
            )
        if status == "failed":
            error = data.get("error")
            message = error.get("message") if isinstance(error, dict) else None
            detail = f"：{message}" if message else ""
            raise ProviderError(f"DeepSeek 响应失败{detail}")
        return data

    def test_connection(self) -> str:
        result = self.create_response(
            instructions="你正在测试 API 连通性。请只回复 OK。",
            input_items="请只回复 OK。",
            tools=None,
            max_output_tokens=256,
            reasoning_effort="none",
        )
        return response_text(result) or "API 已连接，但模型没有返回文本。"


def response_text(response: dict[str, Any]) -> str:
    text: list[str] = []
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                text.append(content["text"])
    return "\n".join(text).strip()
