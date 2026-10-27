from __future__ import annotations

import os
from typing import Literal

from pydantic import SecretStr

SERVICE_NAME = "Tradeveo"
LEGACY_SERVICE_NAME = "TRYEDVEO"
CredentialSource = Literal["environment", "credential_manager", "none"]
PROVIDER_CREDENTIALS: dict[str, tuple[str, str]] = {
    "openai": ("OPENAI_API_KEY", "openai-api-key"),
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic-api-key"),
    "custom_openai_compatible": ("TRADEVEO_CUSTOM_API_KEY", "custom-openai-compatible-api-key"),
}
# Preserve the old constant for integrations/tests that import it.
CREDENTIAL_USERNAME = "openai-api-key"
ENVIRONMENT_VARIABLE = "OPENAI_API_KEY"


def _provider_credential(provider: str) -> tuple[str, str]:
    try:
        return PROVIDER_CREDENTIALS[provider]
    except KeyError as exc:
        raise ValueError("Unsupported AI provider.") from exc


def _verified_keyring():
    try:
        import keyring
        from keyring.backends.Windows import WinVaultKeyring
    except (ImportError, RuntimeError):
        return None
    try:
        backend = keyring.get_keyring()
        if not isinstance(backend, WinVaultKeyring):
            return None
        return keyring
    except Exception:
        return None


def credential_store_available() -> bool:
    return _verified_keyring() is not None


def save_api_key(api_key: SecretStr, provider: str = "openai") -> None:
    _environment_name, username = _provider_credential(provider)
    value = api_key.get_secret_value().strip()
    if not value or len(value) > 512 or any(char.isspace() for char in value):
        raise ValueError("Enter a valid API key value.")
    backend = _verified_keyring()
    if backend is None:
        raise RuntimeError("Windows Credential Manager is unavailable or unverified; the key was not saved.")
    try:
        backend.set_password(SERVICE_NAME, username, value)
    except Exception as exc:
        raise RuntimeError("The API key could not be saved in Windows Credential Manager.") from exc


def read_saved_api_key(provider: str = "openai") -> str | None:
    _environment_name, username = _provider_credential(provider)
    backend = _verified_keyring()
    if backend is None:
        return None
    try:
        saved = backend.get_password(SERVICE_NAME, username)
        if saved:
            return saved
        legacy = backend.get_password(LEGACY_SERVICE_NAME, username)
        if legacy:
            try:
                backend.set_password(SERVICE_NAME, username, legacy)
            except Exception:
                pass
        return legacy
    except Exception:
        return None


def delete_saved_api_key(provider: str = "openai") -> None:
    _environment_name, username = _provider_credential(provider)
    backend = _verified_keyring()
    if backend is None:
        raise RuntimeError("Windows Credential Manager is unavailable or unverified; no key was deleted.")
    try:
        backend.delete_password(SERVICE_NAME, username)
    except backend.errors.PasswordDeleteError:
        return
    except Exception as exc:
        raise RuntimeError("The saved API key could not be removed from Windows Credential Manager.") from exc


def _environment_value(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value or not name.startswith("TRADEVEO_"):
        return value
    return os.environ.get(f"TRYEDVEO_{name.removeprefix('TRADEVEO_')}", "").strip()


def resolve_api_key(provider: str = "openai") -> tuple[str | None, CredentialSource]:
    environment_name, _username = _provider_credential(provider)
    environment_key = _environment_value(environment_name)
    if environment_key:
        return environment_key, "environment"
    saved = read_saved_api_key(provider)
    if saved:
        return saved, "credential_manager"
    return None, "none"
