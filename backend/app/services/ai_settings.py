from __future__ import annotations

import ipaddress
import json
import os
import socket
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.config import database_path
DEFAULT_MODEL = "gpt-5.4-mini"

ProviderId = Literal["openai", "anthropic", "ollama", "custom_openai_compatible"]
MAX_CONFIG_BYTES = 32 * 1024
MAX_MODEL_LENGTH = 200
MAX_MODEL_CHOICES = 30
_config_warning: str | None = None


def _merge_model_choices(selected: str, choices: list[str]) -> tuple[str, list[str]]:
    selected = selected.strip()
    cleaned: list[str] = []
    for item in choices:
        if not isinstance(item, str):
            raise ValueError("Enter a model id up to 200 characters.")
        name = item.strip()
        if not name:
            continue
        if len(name) > MAX_MODEL_LENGTH or any(ord(char) < 32 for char in name):
            raise ValueError("Enter a model id up to 200 characters.")
        if name not in cleaned:
            cleaned.append(name)
    if selected and (len(selected) > MAX_MODEL_LENGTH or any(ord(char) < 32 for char in selected)):
        raise ValueError("Enter a model id up to 200 characters.")
    if selected and selected not in cleaned:
        cleaned.insert(0, selected)
    if len(cleaned) > MAX_MODEL_CHOICES:
        raise ValueError("Save up to 30 models for a provider.")
    return selected, cleaned


class ProviderModels(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    openai: str = Field(default=DEFAULT_MODEL, max_length=MAX_MODEL_LENGTH)
    anthropic: str = Field(default="", max_length=MAX_MODEL_LENGTH)
    ollama: str = Field(default="", max_length=MAX_MODEL_LENGTH)
    openai_choices: list[str] = Field(default_factory=list)
    anthropic_choices: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_choices(self) -> "ProviderModels":
        self.openai, self.openai_choices = _merge_model_choices(self.openai, self.openai_choices)
        self.anthropic, self.anthropic_choices = _merge_model_choices(self.anthropic, self.anthropic_choices)
        return self


class CustomEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    base_url: str = Field(default="", max_length=2048)
    model: str = Field(default="", max_length=MAX_MODEL_LENGTH)
    choices: list[str] = Field(default_factory=list)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        return validate_custom_endpoint_url(value) if value else ""

    @model_validator(mode="after")
    def sync_choices(self) -> "CustomEndpoint":
        self.model, self.choices = _merge_model_choices(self.model, self.choices)
        return self


class AiProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: Literal[1] = 1
    provider: ProviderId = "openai"
    models: ProviderModels = Field(default_factory=ProviderModels)
    custom_endpoint: CustomEndpoint = Field(default_factory=CustomEndpoint)

    @model_validator(mode="after")
    def require_selected_model(self) -> "AiProviderConfig":
        if self.provider == "openai" and not self.models.openai:
            raise ValueError("Choose an OpenAI model in Settings.")
        if self.provider == "anthropic" and not self.models.anthropic:
            raise ValueError("Choose an Anthropic vision model in Settings.")
        if self.provider == "ollama" and not self.models.ollama:
            raise ValueError("Choose an installed Ollama vision model in Settings.")
        if self.provider == "custom_openai_compatible":
            if not self.custom_endpoint.base_url:
                raise ValueError("Enter a custom provider endpoint URL in Settings.")
            if not self.custom_endpoint.model:
                raise ValueError("Choose a custom provider model in Settings.")
        return self


def settings_path() -> Path:
    return database_path().parent / "ai-provider-settings.json"


def config_warning() -> str | None:
    return _config_warning


def load_provider_config() -> AiProviderConfig:
    global _config_warning
    path = settings_path()
    if not path.exists():
        _config_warning = None
        return AiProviderConfig()
    try:
        if path.stat().st_size > MAX_CONFIG_BYTES:
            raise ValueError("Provider settings file is too large.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        config = AiProviderConfig.model_validate(payload)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        _config_warning = "Saved provider settings could not be read; using OpenAI defaults. Settings were not overwritten."
        return AiProviderConfig()
    _config_warning = None
    return config


def save_provider_config(config: AiProviderConfig) -> AiProviderConfig:
    validated = AiProviderConfig.model_validate(config.model_dump(mode="json"))
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".ai-provider-", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(validated.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
    return validated


def validate_custom_endpoint_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Enter a valid custom provider endpoint URL.")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid custom provider endpoint URL.") from exc
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("Custom provider URL must use HTTPS or loopback HTTP.")
    if parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.query:
        raise ValueError("Custom provider URL cannot include credentials, a query, or a fragment.")
    host = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host.strip("[]"))
        is_loopback = address.is_loopback
    except ValueError:
        is_loopback = host == "localhost" or host.endswith(".localhost")
    if parsed.scheme == "http" and (not is_loopback or host not in {"localhost", "127.0.0.1"}):
        raise ValueError("Remote custom providers must use HTTPS; HTTP is allowed only on localhost or 127.0.0.1.")
    if isinstance(locals().get("address"), ipaddress.IPv6Address):
        raise ValueError("Use 127.0.0.1 or localhost for loopback HTTP endpoints.")
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("Custom provider URL has an invalid port.")
    return value.strip().rstrip("/")


def validate_endpoint_resolution(base_url: str) -> None:
    validated = validate_custom_endpoint_url(base_url)
    parsed = urlsplit(validated)
    hostname = parsed.hostname or ""
    try:
        literal = ipaddress.ip_address(hostname.strip("[]"))
        addresses = [literal]
    except ValueError:
        if hostname == "localhost" or hostname.endswith(".localhost"):
            return
        try:
            results = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError("Custom provider hostname could not be resolved.") from exc
        addresses = []
        for result in results:
            try:
                addresses.append(ipaddress.ip_address(result[4][0].split("%", 1)[0]))
            except ValueError as exc:
                raise ValueError("Custom provider returned an invalid network address.") from exc
    if not addresses:
        raise ValueError("Custom provider hostname returned no network addresses.")
    for address in addresses:
        if address.is_loopback:
            if parsed.scheme != "http" and parsed.scheme != "https":
                raise ValueError("Custom provider scheme is invalid.")
            continue
        if not address.is_global:
            raise ValueError("Custom provider hostname must resolve to a public address or loopback.")
