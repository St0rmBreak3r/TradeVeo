from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import SecretStr
from ollama import AsyncClient as OllamaAsyncClient

from backend.app.schemas.chart_analysis import ChartAnalysisResult
from backend.app.services.ai_settings import AiProviderConfig, config_warning, load_provider_config, save_provider_config
from backend.app.services.chart_images import MAX_CHART_BYTES, validate_chart_image
from backend.app.services.chart_providers import (
    DEFAULT_MODEL,
    ProviderConfigurationError,
    ProviderError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    create_chart_provider,
)
from backend.app.services.credentials import CredentialSource, delete_saved_api_key, resolve_api_key, save_api_key

router = APIRouter(prefix="/api", tags=["chart-analysis"])


def _status() -> dict[str, Any]:
    config = load_provider_config()
    provider = config.provider
    model = {
        "openai": config.models.openai,
        "anthropic": config.models.anthropic,
        "ollama": config.models.ollama,
        "custom_openai_compatible": config.custom_endpoint.model,
    }[provider]
    if provider == "ollama":
        configured = bool(model)
        source: CredentialSource | str = "local_service"
        endpoint_label = "127.0.0.1:11434"
    elif provider == "custom_openai_compatible":
        api_key, source = resolve_api_key(provider)
        configured = bool(config.custom_endpoint.base_url and config.custom_endpoint.model)
        if not api_key:
            source = "none"
        endpoint_label = None
        if config.custom_endpoint.base_url:
            from urllib.parse import urlsplit
            endpoint_label = urlsplit(config.custom_endpoint.base_url).hostname or "custom endpoint"
    else:
        api_key, source = resolve_api_key(provider)
        configured = bool(api_key) and bool(model)
        endpoint_label = None
    result: dict[str, Any] = {
        "provider": provider,
        "configured": configured,
        "model": model or None,
        "credential_source": source,
    }
    if endpoint_label:
        result["endpoint_label"] = endpoint_label
    warning = config_warning()
    if warning:
        result["warning"] = warning
    return result


@router.get("/ai/status")
def ai_status() -> dict[str, Any]:
    return _status()


@router.get("/ai/provider")
def get_ai_provider() -> dict[str, Any]:
    return load_provider_config().model_dump(mode="json")


@router.put("/ai/provider")
def set_ai_provider(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        config = AiProviderConfig.model_validate(payload)
        return save_provider_config(config).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except OSError:
        raise HTTPException(status_code=503, detail="Provider settings could not be saved locally.") from None


@router.put("/ai/credential")
def set_ai_credential(payload: dict[str, Any]) -> dict[str, Any]:
    provider = payload.get("provider", "openai")
    value = payload.get("api_key")
    if provider not in {"openai", "anthropic", "custom_openai_compatible"}:
        raise HTTPException(status_code=422, detail="Choose a credential-based provider.")
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail="Enter an API key.")
    try:
        save_api_key(SecretStr(value), provider=provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"configured": True, "credential_source": "credential_manager", "provider": provider}


@router.delete("/ai/credential")
def clear_ai_credential(provider: str = Query(default="openai")) -> dict[str, Any]:
    if provider not in {"openai", "anthropic", "custom_openai_compatible"}:
        raise HTTPException(status_code=422, detail="Choose a credential-based provider.")
    try:
        delete_saved_api_key(provider)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    key, _source = resolve_api_key(provider)
    response = {"configured": bool(key)}
    if provider != "openai":
        response["provider"] = provider
    return response


@router.get("/ai/models")
async def ollama_models() -> dict[str, Any]:
    try:
        response = await OllamaAsyncClient(host="http://127.0.0.1:11434", timeout=3.0).list()
        models = sorted({getattr(model, "model", None) or getattr(model, "name", "") for model in response.models} - {""})
        return {"available": True, "models": models}
    except Exception:
        return {"available": False, "models": []}


@router.post("/chart-analysis", response_model=ChartAnalysisResult)
async def analyze_chart(
    request: Request,
    consent: bool = Form(default=False),
    image: UploadFile = File(...),
) -> ChartAnalysisResult:
    config = load_provider_config()
    if consent is not True:
        raise HTTPException(status_code=400, detail=f"Confirm that this chart image will be sent to {_provider_label(config.provider)} before analysis.")
    provider_id = config.provider
    if provider_id == "ollama":
        api_key, _source = None, "none"
    else:
        api_key, _source = resolve_api_key(provider_id)
    if provider_id in {"openai", "anthropic"} and not api_key:
        variable = "OPENAI_API_KEY" if provider_id == "openai" else "ANTHROPIC_API_KEY"
        raise HTTPException(status_code=503, detail=f"Configure the selected provider's API key in Settings or {variable} before analysis.")
    try:
        data = await image.read(MAX_CHART_BYTES + 1)
        if len(data) > MAX_CHART_BYTES:
            raise OverflowError("Chart image must be 10 MiB or smaller.")
        _mime, image_data_url = validate_chart_image(data, image.content_type or "")
    except OverflowError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None
    except TypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    finally:
        await image.close()

    try:
        provider = request.app.state.chart_provider_factory(api_key)
        return await provider.analyze(image_data_url)
    except ProviderTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from None
    except ProviderRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except ProviderInvalidResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    except Exception:
        raise HTTPException(status_code=502, detail="The selected provider could not return a valid chart analysis.") from None


def _provider_label(provider: str) -> str:
    return {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "ollama": "your local Ollama model",
        "custom_openai_compatible": "the configured custom provider",
    }.get(provider, "the selected provider")
