from __future__ import annotations

import json

import pytest

from backend.app.services import ai_settings


def test_default_config_keeps_openai_and_existing_model(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_settings, "settings_path", lambda: tmp_path / "providers.json")
    config = ai_settings.load_provider_config()
    assert config.provider == "openai"
    assert config.models.openai == "gpt-5.4-mini"
    assert config.custom_endpoint.base_url == ""


def test_provider_config_round_trips_without_secrets(tmp_path, monkeypatch):
    path = tmp_path / "providers.json"
    monkeypatch.setattr(ai_settings, "settings_path", lambda: path)
    config = ai_settings.AiProviderConfig.model_validate({"version": 1, "provider": "custom_openai_compatible", "models": {"openai": "gpt-5.4-mini", "anthropic": "claude-model", "ollama": "llava"}, "custom_endpoint": {"base_url": "https://api.example.com/v1", "model": "vision-model"}})
    ai_settings.save_provider_config(config)
    assert "api_key" not in path.read_text(encoding="utf-8")
    assert ai_settings.load_provider_config() == config


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@example.com/v1", "https://example.com/v1?token=private", "https://example.com/v1#fragment", "http://example.com/v1", "http://192.168.1.20/v1", "http://[::1]:8080/v1"])
def test_rejects_unsafe_custom_endpoint_urls(url):
    with pytest.raises(ValueError):
        ai_settings.validate_custom_endpoint_url(url)


@pytest.mark.parametrize("url", ["https://api.example.com/v1", "http://127.0.0.1:8000/v1", "http://localhost:11434/v1"])
def test_accepts_https_remote_and_loopback_http(url):
    assert ai_settings.validate_custom_endpoint_url(url) == url.rstrip("/")


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        ai_settings.AiProviderConfig.model_validate({"version": 1, "provider": "unsupported"})


def test_non_global_resolved_custom_endpoint_rejected(monkeypatch):
    monkeypatch.setattr(ai_settings.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("10.0.0.8", 443))])
    with pytest.raises(ValueError, match="public address"):
        ai_settings.validate_endpoint_resolution("https://api.example.com/v1")


def test_global_resolved_custom_endpoint_allowed(monkeypatch):
    monkeypatch.setattr(ai_settings.socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))])
    ai_settings.validate_endpoint_resolution("https://api.example.com/v1")


def test_existing_model_becomes_a_choice_without_rewriting_the_file(tmp_path, monkeypatch):
    path = tmp_path / "providers.json"
    path.write_text(json.dumps({"version": 1, "provider": "custom_openai_compatible", "models": {"openai": "gpt-5.4-mini", "anthropic": "claude-model", "ollama": "llava"}, "custom_endpoint": {"base_url": "https://api.example.com/v1", "model": "z-ai/glm-5.3"}}), encoding="utf-8")
    monkeypatch.setattr(ai_settings, "settings_path", lambda: path)
    config = ai_settings.load_provider_config()
    assert config.custom_endpoint.model == "z-ai/glm-5.3"
    assert config.custom_endpoint.choices == ["z-ai/glm-5.3"]
    assert config.models.anthropic_choices == ["claude-model"]
    assert "choices" not in path.read_text(encoding="utf-8")


def test_model_choices_drop_duplicates_and_keep_the_selected_model():
    config = ai_settings.AiProviderConfig.model_validate({"version": 1, "provider": "openai", "models": {"openai": "gpt-a", "openai_choices": [" gpt-a ", "gpt-a", "gpt-b"], "anthropic": "", "ollama": ""}})
    assert config.models.openai_choices == ["gpt-a", "gpt-b"]


def test_model_choice_list_is_limited():
    with pytest.raises(ValueError, match="30 models"):
        ai_settings.AiProviderConfig.model_validate({"version": 1, "provider": "openai", "models": {"openai": "m0", "openai_choices": [f"m{i}" for i in range(31)], "anthropic": "", "ollama": ""}})


def test_corrupt_config_falls_back_without_overwriting_file(tmp_path, monkeypatch):
    path = tmp_path / "providers.json"
    path.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(ai_settings, "settings_path", lambda: path)
    config = ai_settings.load_provider_config()
    assert config.provider == "openai"
    assert path.read_text(encoding="utf-8") == "not json"
    assert ai_settings.config_warning() is not None
