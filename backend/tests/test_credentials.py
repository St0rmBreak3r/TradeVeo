from __future__ import annotations

import pytest
from pydantic import SecretStr

from backend.app.services import credentials


def test_environment_key_precedes_credential_manager(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "environment-secret")
    monkeypatch.setattr(credentials, "read_saved_api_key", lambda provider="openai": "saved-secret")
    key, source = credentials.resolve_api_key()
    assert key == "environment-secret"
    assert source == "environment"


def test_saved_key_used_when_environment_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(credentials, "read_saved_api_key", lambda provider="openai": "saved-secret")
    assert credentials.resolve_api_key() == ("saved-secret", "credential_manager")


def test_no_key_has_non_secret_status(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(credentials, "read_saved_api_key", lambda provider="openai": None)
    assert credentials.resolve_api_key() == (None, "none")


def test_save_fails_closed_if_verified_windows_backend_unavailable(monkeypatch):
    monkeypatch.setattr(credentials, "_verified_keyring", lambda: None)
    with pytest.raises(RuntimeError, match="not saved"):
        credentials.save_api_key(SecretStr("user-key"))


def test_invalid_key_rejected_without_echo(monkeypatch):
    monkeypatch.setattr(credentials, "_verified_keyring", lambda: object())
    with pytest.raises(ValueError) as error:
        credentials.save_api_key(SecretStr("has whitespace"))
    assert "has whitespace" not in str(error.value)


def test_provider_keys_have_separate_environment_and_credential_entries(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "claude-env-key")
    monkeypatch.setenv("TRADEVEO_CUSTOM_API_KEY", "custom-env-key")
    saved = {"openai": "openai-saved", "anthropic": "claude-saved", "custom_openai_compatible": "custom-saved"}
    monkeypatch.setattr(credentials, "read_saved_api_key", lambda provider="openai": saved[provider])
    assert credentials.resolve_api_key() == ("openai-saved", "credential_manager")
    assert credentials.resolve_api_key("anthropic") == ("claude-env-key", "environment")
    assert credentials.resolve_api_key("custom_openai_compatible") == ("custom-env-key", "environment")


def test_provider_secret_storage_uses_separate_credential_names(monkeypatch):
    recorded = []
    fake_backend = type("FakeBackend", (), {"set_password": staticmethod(lambda service, username, value: recorded.append((service, username, value)))})
    monkeypatch.setattr(credentials, "_verified_keyring", lambda: fake_backend)
    credentials.save_api_key(SecretStr("claude-key"), provider="anthropic")
    credentials.save_api_key(SecretStr("custom-key"), provider="custom_openai_compatible")
    assert [item[1] for item in recorded] == ["anthropic-api-key", "custom-openai-compatible-api-key"]
    assert all(item[0] == credentials.SERVICE_NAME for item in recorded)


def test_saved_key_resolver_receives_provider(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    requested = []
    monkeypatch.setattr(credentials, "read_saved_api_key", lambda provider="openai": requested.append(provider) or "saved")
    assert credentials.resolve_api_key("anthropic") == ("saved", "credential_manager")
    assert requested == ["anthropic"]


def test_unsupported_provider_is_rejected_without_secret_storage():
    with pytest.raises(ValueError):
        credentials.save_api_key(SecretStr("secret"), provider="mystery")
    with pytest.raises(ValueError):
        credentials.resolve_api_key("mystery")


def test_delete_saved_key_targets_only_requested_provider(monkeypatch):
    deleted = []
    class Errors:
        class PasswordDeleteError(Exception):
            pass
    fake_backend = type("FakeBackend", (), {"errors": Errors, "delete_password": staticmethod(lambda service, username: deleted.append((service, username)))})
    monkeypatch.setattr(credentials, "_verified_keyring", lambda: fake_backend)
    credentials.delete_saved_api_key("anthropic")
    assert deleted == [(credentials.SERVICE_NAME, "anthropic-api-key")]


def test_environment_override_does_not_cross_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-env")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(credentials, "read_saved_api_key", lambda provider="openai": f"{provider}-saved")
    assert credentials.resolve_api_key("anthropic") == ("anthropic-saved", "credential_manager")
    assert credentials.resolve_api_key("openai") == ("openai-env", "environment")
