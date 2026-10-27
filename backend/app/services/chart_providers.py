from __future__ import annotations

import base64
import json
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
from anthropic import AsyncAnthropic
from ollama import AsyncClient as OllamaAsyncClient
from openai import AsyncOpenAI

from backend.app.schemas.chart_analysis import ChartAnalysisResult
from backend.app.services.ai_settings import AiProviderConfig, validate_endpoint_resolution

DEFAULT_MODEL = "gpt-5.4-mini"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
REQUEST_TIMEOUT_SECONDS = 45.0
MAX_OUTPUT_TOKENS = 1800
# Reasoning-capable custom endpoints (e.g. NVIDIA NIM) count internal reasoning
# tokens against the same completion budget, so the custom adapter needs more
# headroom than MAX_OUTPUT_TOKENS or the final JSON answer is never produced.
MAX_CUSTOM_OUTPUT_TOKENS = 4096
MAX_CUSTOM_RESPONSE_BYTES = 256 * 1024

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["LONG", "SHORT", "NO_TRADE"]},
        "symbol": {"type": ["string", "null"]},
        "timeframe": {"type": ["string", "null"]},
        "setup_type": {"type": ["string", "null"]},
        "entry": {"anyOf": [
            {"type": "object", "properties": {"low": {"type": ["number", "null"]}, "high": {"type": ["number", "null"]}, "basis": {"type": ["string", "null"]}}, "required": ["low", "high", "basis"], "additionalProperties": False},
            {"type": "null"},
        ]},
        "stop_loss": {"anyOf": [
            {"type": "object", "properties": {"price": {"type": "number"}, "basis": {"type": "string"}}, "required": ["price", "basis"], "additionalProperties": False},
            {"type": "null"},
        ]},
        "targets": {"type": "array", "items": {"type": "object", "properties": {"price": {"type": "number"}, "basis": {"type": "string"}}, "required": ["price", "basis"], "additionalProperties": False}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "confidence_note": {"type": "string"},
        "observations": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
        "invalidation": {"type": ["string", "null"]},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "symbol", "timeframe", "setup_type", "entry", "stop_loss", "targets", "confidence", "confidence_note", "observations", "rationale", "invalidation", "warnings"],
    "additionalProperties": False,
}

INSTRUCTIONS = f"""You are a trader with 25 years of screen time. Read only this chart screenshot and give one trading entry setup. Return exactly one JSON object matching this JSON Schema: {json.dumps(RESULT_SCHEMA, separators=(',', ':'))}. Include all required fields, no additional fields, and no markdown or surrounding text. Write rationale as that veteran: direct, specific, and tied to the visible structure. Read symbol, timeframe, and price values only when clearly legible; never guess or invent exact prices. For LONG or SHORT, give the entry area, stop, and targets that the visible levels support, and explain the visual basis of each. If the image is blurry, cropped, conflicting, lacks a readable price scale, or does not support an entry, return decision NO_TRADE with null entry, null stop_loss, and empty targets. Confidence is a qualitative estimate, not a probability. Do not promise profit or place orders."""


class ProviderError(RuntimeError):
    """Safe, user-displayable provider failure with no upstream exception text."""


class ProviderTimeoutError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class ProviderConfigurationError(ProviderError):
    pass


class ProviderInvalidResponseError(ProviderError):
    pass


class ChartProvider(Protocol):
    async def analyze(self, image_data_url: str) -> ChartAnalysisResult: ...


def _parse_result(text: Any, provider_name: str) -> ChartAnalysisResult:
    if not isinstance(text, str) or not text.strip():
        raise ProviderInvalidResponseError(f"{provider_name} returned no chart analysis.")
    try:
        payload = json.loads(text)
        return ChartAnalysisResult.model_validate(payload)
    except (json.JSONDecodeError, ValueError, TypeError):
        raise ProviderInvalidResponseError(f"{provider_name} returned a result that did not match the chart schema.") from None


def _raise_safe_provider_error(provider_name: str, error: Exception) -> None:
    name = type(error).__name__.lower()
    status = getattr(error, "status_code", None)
    if isinstance(error, (TimeoutError, httpx.TimeoutException)) or "timeout" in name:
        raise ProviderTimeoutError(f"{provider_name} chart analysis timed out. Please try again.") from None
    if status == 429 or "ratelimit" in name or "rate_limit" in name:
        raise ProviderRateLimitError(f"{provider_name} rate limit reached. Wait and try again.") from None
    if status in {401, 403}:
        raise ProviderConfigurationError(f"{provider_name} rejected the credential or model configuration.") from None
    if status is not None or isinstance(error, (httpx.HTTPError, ConnectionError, OSError)):
        raise ProviderUnavailableError(f"{provider_name} is unavailable or rejected the request.") from None
    raise ProviderUnavailableError(f"{provider_name} could not return a valid chart analysis.") from None


def _decode_data_url(image_data_url: str) -> tuple[str, bytes]:
    try:
        header, encoded = image_data_url.split(",", 1)
        mime = header.removeprefix("data:").removesuffix(";base64")
        if mime not in {"image/png", "image/jpeg"}:
            raise ValueError
        return mime, base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ProviderConfigurationError("The validated chart image could not be prepared for the selected provider.") from None


class OpenAIChartProvider:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS, client: AsyncOpenAI | None = None):
        self._client = client or AsyncOpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)
        self.model = model

    async def analyze(self, image_data_url: str) -> ChartAnalysisResult:
        try:
            response = await self._client.responses.create(
                model=self.model,
                store=False,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                input=[{"role": "user", "content": [
                    {"type": "input_text", "text": INSTRUCTIONS},
                    {"type": "input_image", "image_url": image_data_url, "detail": "high"},
                ]}],
                text={"format": {"type": "json_schema", "name": "chart_analysis", "strict": True, "schema": RESULT_SCHEMA}},
            )
        except Exception as exc:
            _raise_safe_provider_error("OpenAI", exc)
        if getattr(response, "status", "completed") != "completed":
            raise ProviderInvalidResponseError("OpenAI returned an incomplete chart analysis.")
        return _parse_result(getattr(response, "output_text", None), "OpenAI")


class AnthropicChartProvider:
    def __init__(self, api_key: str, model: str, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS, client: AsyncAnthropic | None = None):
        if not model:
            raise ProviderConfigurationError("Choose an Anthropic vision model in Settings.")
        self._client = client or AsyncAnthropic(api_key=api_key, timeout=timeout_seconds, max_retries=0)
        self.model = model

    async def analyze(self, image_data_url: str) -> ChartAnalysisResult:
        mime, image_bytes = _decode_data_url(image_data_url)
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=INSTRUCTIONS,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(image_bytes).decode("ascii")}},
                    {"type": "text", "text": "Analyze this chart screenshot and return the structured chart result."},
                ]}],
                output_config={"format": {"type": "json_schema", "schema": RESULT_SCHEMA}},
            )
        except Exception as exc:
            _raise_safe_provider_error("Anthropic", exc)
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise ProviderInvalidResponseError("Anthropic returned an incomplete chart analysis.")
        texts = [getattr(block, "text", None) for block in getattr(response, "content", []) if getattr(block, "type", None) == "text"]
        if not texts:
            raise ProviderInvalidResponseError("Anthropic returned no chart analysis.")
        return _parse_result("\n".join(texts), "Anthropic")


class OllamaChartProvider:
    def __init__(self, model: str, client: OllamaAsyncClient | None = None, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS):
        if not model:
            raise ProviderConfigurationError("Choose an installed Ollama vision model in Settings.")
        self.model = model
        self._client = client or OllamaAsyncClient(host=OLLAMA_BASE_URL, timeout=timeout_seconds)

    async def analyze(self, image_data_url: str) -> ChartAnalysisResult:
        _mime, image_bytes = _decode_data_url(image_data_url)
        try:
            response = await self._client.chat(
                model=self.model,
                messages=[{"role": "user", "content": INSTRUCTIONS, "images": [image_bytes]}],
                format=RESULT_SCHEMA,
                stream=False,
                options={"temperature": 0, "num_predict": MAX_OUTPUT_TOKENS},
            )
        except Exception as exc:
            _raise_safe_provider_error("Ollama", exc)
        message = getattr(response, "message", None)
        return _parse_result(getattr(message, "content", None), "Ollama")


class CustomOpenAICompatibleProvider:
    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS, max_tokens: int = MAX_CUSTOM_OUTPUT_TOKENS, client: httpx.AsyncClient | None = None):
        if not base_url or not model:
            raise ProviderConfigurationError("Configure a custom endpoint URL and model in Settings.")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self._client = client

    @property
    def endpoint_url(self) -> str:
        parsed = urlsplit(self.base_url)
        if parsed.path.rstrip("/").endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    async def analyze(self, image_data_url: str) -> ChartAnalysisResult:
        try:
            validate_endpoint_resolution(self.base_url)
        except ValueError:
            raise ProviderConfigurationError("Custom provider URL is unsafe or cannot be resolved to an allowed address.") from None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": INSTRUCTIONS},
                {"type": "image_url", "image_url": {"url": image_data_url, "detail": "high"}},
            ]}],
            "temperature": 1,
            "top_p": 0.95,
            "max_tokens": self.max_tokens,
            "stream": False,
            "seed": 42,
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False, trust_env=False)
        try:
            async with client.stream("POST", self.endpoint_url, headers=headers, json=payload) as response:
                if response.status_code >= 300:
                    error = httpx.HTTPStatusError("provider request failed", request=response.request, response=response)
                    error.status_code = response.status_code
                    _raise_safe_provider_error("Custom provider", error)
                content_type = response.headers.get("content-type", "").lower()
                if "text/event-stream" in content_type:
                    content = await self._read_stream(response)
                else:
                    raw_response = await self._read_bounded(response)
                    try:
                        data = json.loads(raw_response)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        raise ProviderInvalidResponseError("Custom provider returned an invalid chart-analysis response.") from None
                    content = self._extract_message_content(data)
        except ProviderError:
            raise
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise ProviderInvalidResponseError("Custom provider returned no valid chart analysis.") from None
        except Exception as exc:
            _raise_safe_provider_error("Custom provider", exc)
        finally:
            if owns_client:
                await client.aclose()
        return _parse_result(content, "Custom provider")

    async def _read_bounded(self, response: Any) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_CUSTOM_RESPONSE_BYTES:
                raise ProviderInvalidResponseError("Custom provider returned an oversized response.")
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _extract_message_content(data: Any) -> str:
        if not isinstance(data, dict):
            raise ProviderInvalidResponseError("Custom provider returned an invalid chart-analysis response.")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderInvalidResponseError("Custom provider returned no chart analysis.")
        if choices[0].get("finish_reason") == "length":
            raise ProviderInvalidResponseError("Custom provider returned an incomplete chart analysis.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderInvalidResponseError("Custom provider returned no chart analysis.")
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text = "".join(
                part["text"]
                for part in content
                if isinstance(part, dict)
                and part.get("type") in {"text", "output_text"}
                and isinstance(part.get("text"), str)
            ).strip()
            if text:
                return text
        raise ProviderInvalidResponseError("Custom provider returned no chart analysis.")

    async def _read_stream(self, response: Any) -> str:
        pending = b""
        content_parts: list[str] = []
        size = 0
        finished = False
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_CUSTOM_RESPONSE_BYTES:
                raise ProviderInvalidResponseError("Custom provider returned an oversized response.")
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                line = line.rstrip(b"\r")
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    finished = True
                    continue
                try:
                    event = json.loads(payload)
                    choice = event["choices"][0]
                    finish_reason = choice.get("finish_reason")
                    if finish_reason == "length":
                        raise ProviderInvalidResponseError("Custom provider returned an incomplete chart analysis.")
                    delta = choice.get("delta") or {}
                    fragment = delta.get("content")
                    if isinstance(fragment, str):
                        content_parts.append(fragment)
                    elif isinstance(fragment, list):
                        content_parts.extend(part.get("text", "") for part in fragment if isinstance(part, dict) and isinstance(part.get("text"), str))
                except ProviderError:
                    raise
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    raise ProviderInvalidResponseError("Custom provider returned an invalid chart-analysis stream.") from None
        if pending.strip():
            raise ProviderInvalidResponseError("Custom provider returned a truncated chart-analysis stream.")
        if not finished:
            raise ProviderInvalidResponseError("Custom provider ended the chart-analysis stream prematurely.")
        return "".join(content_parts)


def create_chart_provider(config: AiProviderConfig, api_key: str | None) -> ChartProvider:
    provider = config.provider
    if provider == "openai":
        if not api_key:
            raise ProviderConfigurationError("Configure an OpenAI API key in Settings or OPENAI_API_KEY before analysis.")
        return OpenAIChartProvider(api_key, config.models.openai)
    if provider == "anthropic":
        if not api_key:
            raise ProviderConfigurationError("Configure an Anthropic API key in Settings or ANTHROPIC_API_KEY before analysis.")
        return AnthropicChartProvider(api_key, config.models.anthropic)
    if provider == "ollama":
        return OllamaChartProvider(config.models.ollama)
    if provider == "custom_openai_compatible":
        return CustomOpenAICompatibleProvider(
            config.custom_endpoint.base_url,
            config.custom_endpoint.model,
            api_key,
            timeout_seconds=180.0,
            max_tokens=MAX_CUSTOM_OUTPUT_TOKENS,
        )
    raise ProviderConfigurationError("Choose a supported chart-analysis provider in Settings.")
