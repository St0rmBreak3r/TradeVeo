from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.app.services import chart_providers as providers
from backend.app.services.chart_providers import (
    DEFAULT_MODEL,
    AnthropicChartProvider,
    CustomOpenAICompatibleProvider,
    OllamaChartProvider,
    OpenAIChartProvider,
    ProviderConfigurationError,
    ProviderInvalidResponseError,
    ProviderUnavailableError,
)


class FakeResponses:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, responses):
        self.responses = responses


def valid_payload():
    return json.dumps({
        "decision": "NO_TRADE", "symbol": None, "timeframe": None, "setup_type": None,
        "entry": None, "stop_loss": None, "targets": [], "confidence": "low",
        "confidence_note": "Unclear labels.", "observations": [], "rationale": "Cannot ground levels.",
        "invalidation": None, "warnings": ["No trade"],
    })


def test_openai_adapter_sends_in_memory_image_and_strict_schema():
    responses = FakeResponses(SimpleNamespace(status="completed", output_text=valid_payload()))
    provider = OpenAIChartProvider("not-a-real-secret", client=FakeClient(responses))
    result = asyncio.run(provider.analyze("data:image/png;base64,AAAA"))
    call = responses.kwargs
    assert result.decision == "NO_TRADE"
    assert call["model"] == DEFAULT_MODEL
    assert call["store"] is False
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["strict"] is True
    assert call["input"][0]["content"][1]["image_url"] == "data:image/png;base64,AAAA"
    assert "file_id" not in repr(call)


def test_openai_adapter_rejects_incomplete_response():
    provider = OpenAIChartProvider("secret", client=FakeClient(FakeResponses(SimpleNamespace(status="incomplete", output_text="{}"))))
    with pytest.raises(RuntimeError, match="incomplete"):
        asyncio.run(provider.analyze("data:image/png;base64,AAAA"))


def test_openai_adapter_rejects_malformed_or_unsafe_result():
    for output in ["not-json", valid_payload().replace('"decision": "NO_TRADE"', '"decision": "MAYBE"')]:
        provider = OpenAIChartProvider("secret", client=FakeClient(FakeResponses(SimpleNamespace(status="completed", output_text=output))))
        with pytest.raises(RuntimeError, match="schema"):
            asyncio.run(provider.analyze("data:image/png;base64,AAAA"))


def test_openai_adapter_does_not_leak_raw_provider_error():
    provider = OpenAIChartProvider("topsecret", client=FakeClient(FakeResponses(error=RuntimeError("request contained topsecret and chart bytes"))))
    with pytest.raises(RuntimeError) as error:
        asyncio.run(provider.analyze("data:image/png;base64,AAAA"))
    assert "topsecret" not in str(error.value)


def test_anthropic_adapter_uses_base64_image_and_schema(monkeypatch):
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=valid_payload())]))))
    provider = AnthropicChartProvider("anthropic-secret", "vision-model", client=client)
    result = asyncio.run(provider.analyze("data:image/png;base64,QUJD"))
    call = client.messages.create.await_args.kwargs
    image_block = call["messages"][0]["content"][0]
    assert result.decision == "NO_TRADE"
    assert call["model"] == "vision-model"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert image_block["source"]["media_type"] == "image/png"
    assert base64.b64decode(image_block["source"]["data"]) == b"ABC"
    assert "anthropic-secret" not in repr(call)


def test_anthropic_provider_error_is_redacted():
    client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("anthropic-secret and chart bytes"))))
    provider = AnthropicChartProvider("anthropic-secret", "vision-model", client=client)
    with pytest.raises(ProviderUnavailableError) as error:
        asyncio.run(provider.analyze("data:image/jpeg;base64,QUJD"))
    assert "anthropic-secret" not in str(error.value)
    assert "chart bytes" not in str(error.value)


def test_ollama_adapter_sends_image_bytes_and_json_schema():
    client = SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(message=SimpleNamespace(content=valid_payload()))))
    provider = OllamaChartProvider("local-vision-model", client=client)
    result = asyncio.run(provider.analyze("data:image/jpeg;base64,QUJD"))
    call = client.chat.await_args.kwargs
    assert result.decision == "NO_TRADE"
    assert call["model"] == "local-vision-model"
    assert call["format"]["type"] == "object"
    assert call["messages"][0]["images"] == [b"ABC"]
    assert "api_key" not in repr(call)


def test_ollama_missing_model_is_actionable():
    with pytest.raises(ProviderConfigurationError, match="Ollama vision model"):
        OllamaChartProvider("")


class FakeStreamResponse:
    status_code = 200
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")

    def __init__(self, chunks, content_type="application/json"):
        self.chunks = chunks if isinstance(chunks, (list, tuple)) else [chunks]
        self.headers = {"content-type": content_type}

    async def __aenter__(self): return self
    async def __aexit__(self, *args): return None
    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk


class FakeHttpClient:
    def __init__(self, body, content_type="application/json"):
        self.body = body
        self.content_type = content_type
        self.kwargs = None
        self.closed = False
    def stream(self, method, url, **kwargs):
        self.kwargs = (method, url, kwargs)
        return FakeStreamResponse(self.body, self.content_type)
    async def aclose(self): self.closed = True


def test_custom_adapter_uses_openai_compatible_image_and_bounds(monkeypatch):
    monkeypatch.setattr(providers, "validate_endpoint_resolution", lambda url: None)
    client = FakeHttpClient(json.dumps({"choices": [{"message": {"content": valid_payload()}}]}).encode())
    provider = CustomOpenAICompatibleProvider("https://api.example.com/v1", "custom-vision", "custom-secret", client=client)
    result = asyncio.run(provider.analyze("data:image/png;base64,QUJD"))
    method, url, call = client.kwargs
    assert result.decision == "NO_TRADE"
    assert method == "POST" and url == "https://api.example.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer custom-secret"
    assert call["json"]["model"] == "custom-vision"
    assert call["json"]["stream"] is False
    assert "decision" in call["json"]["messages"][0]["content"][0]["text"]
    assert "response_format" not in call["json"]
    assert call["json"]["messages"][0]["content"][1]["image_url"]["url"] == "data:image/png;base64,QUJD"
    assert call["json"]["max_tokens"] == providers.MAX_CUSTOM_OUTPUT_TOKENS
    assert "custom-secret" not in json.dumps(call["json"])


def test_custom_adapter_collects_streamed_content_and_ignores_reasoning(monkeypatch):
    monkeypatch.setattr(providers, "validate_endpoint_resolution", lambda url: None)
    events = [
        {"choices": [{"delta": {"reasoning_content": "internal reasoning that is not JSON"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": valid_payload()[:42]}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": valid_payload()[42:]}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
    encoded = body.encode()
    client = FakeHttpClient([encoded[:31], encoded[31:119], encoded[119:]], "text/event-stream")
    provider = CustomOpenAICompatibleProvider("https://api.example.com/v1", "custom-vision", client=client)

    result = asyncio.run(provider.analyze("data:image/png;base64,QUJD"))

    assert result.decision == "NO_TRADE"
    assert "internal reasoning" not in repr(result)
    assert client.kwargs[2]["json"]["stream"] is False


def test_custom_adapter_rejects_truncated_non_streamed_response(monkeypatch):
    monkeypatch.setattr(providers, "validate_endpoint_resolution", lambda url: None)
    truncated = valid_payload()[:25]
    client = FakeHttpClient(json.dumps({"choices": [{"message": {"content": truncated}, "finish_reason": "length"}]}).encode())
    provider = CustomOpenAICompatibleProvider("https://api.example.com/v1", "model", client=client)

    with pytest.raises(ProviderInvalidResponseError, match="incomplete"):
        asyncio.run(provider.analyze("data:image/png;base64,QUJD"))


def test_custom_adapter_accepts_text_blocks_and_rejects_reasoning_only():
    content = [{"type": "reasoning", "text": "internal reasoning"}, {"type": "text", "text": valid_payload()}]
    parsed = CustomOpenAICompatibleProvider._extract_message_content({"choices": [{"message": {"content": content}}]})
    assert providers._parse_result(parsed, "Custom provider").decision == "NO_TRADE"

    with pytest.raises(ProviderInvalidResponseError, match="no chart analysis"):
        CustomOpenAICompatibleProvider._extract_message_content({"choices": [{"message": {"content": None, "reasoning": "internal reasoning"}}]})


def test_custom_adapter_rejects_truncated_stream(monkeypatch):
    monkeypatch.setattr(providers, "validate_endpoint_resolution", lambda url: None)
    event = {"choices": [{"delta": {"content": valid_payload()[:25]}, "finish_reason": "length"}]}
    client = FakeHttpClient((f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n").encode(), "text/event-stream")
    provider = CustomOpenAICompatibleProvider("https://api.example.com/v1", "model", client=client)

    with pytest.raises(ProviderInvalidResponseError, match="incomplete"):
        asyncio.run(provider.analyze("data:image/png;base64,QUJD"))


def test_custom_endpoint_rejects_unsafe_address_before_request(monkeypatch):
    monkeypatch.setattr(providers, "validate_endpoint_resolution", lambda url: (_ for _ in ()).throw(ValueError("unsafe")))
    provider = CustomOpenAICompatibleProvider("https://private.example/v1", "model", client=FakeHttpClient(b"{}"))
    with pytest.raises(ProviderConfigurationError, match="unsafe"):
        asyncio.run(provider.analyze("data:image/png;base64,QUJD"))


def test_custom_http_error_does_not_leak_credentials(monkeypatch):
    monkeypatch.setattr(providers, "validate_endpoint_resolution", lambda url: None)
    class ErrorClient(FakeHttpClient):
        def stream(self, method, url, **kwargs):
            response = FakeStreamResponse(b"")
            response.status_code = 401
            response.request = httpx.Request("POST", url)
            return response
    client = ErrorClient(b"")
    provider = CustomOpenAICompatibleProvider("https://api.example.com/v1", "model", "custom-secret", client=client)
    with pytest.raises(ProviderConfigurationError) as error:
        asyncio.run(provider.analyze("data:image/png;base64,QUJD"))
    assert "custom-secret" not in str(error.value)


def test_custom_adapter_rejects_invalid_response_schema(monkeypatch):
    monkeypatch.setattr(providers, "validate_endpoint_resolution", lambda url: None)
    client = FakeHttpClient(b'{"choices":[{"message":{"content":"not-json"}}]}')
    provider = CustomOpenAICompatibleProvider("https://api.example.com/v1", "model", client=client)
    with pytest.raises(ProviderInvalidResponseError):
        asyncio.run(provider.analyze("data:image/png;base64,QUJD"))
