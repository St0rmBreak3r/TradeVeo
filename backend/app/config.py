from __future__ import annotations

import os
from pathlib import Path

from tzlocal import get_localzone_name


def _data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data)
    return Path.home() / ".local" / "share"


def database_path() -> Path:
    root = _data_root()
    current = root / "Tradeveo" / "journal.sqlite3"
    legacy = root / "TRYEDVEO" / "journal.sqlite3"
    if not current.exists() and legacy.exists():
        return legacy
    return current


def _setting(name: str, default: str) -> str:
    value = os.environ.get(f"TRADEVEO_{name}", "").strip()
    if value:
        return value
    return os.environ.get(f"TRYEDVEO_{name}", "").strip() or default


def database_url() -> str:
    return _setting("DATABASE_URL", f"sqlite:///{database_path()}")


def backup_directory() -> Path:
    return database_path().parent / "backups"


def ui_origin() -> str:
    return _setting("UI_ORIGIN", "http://127.0.0.1:5173")


def timezone_name() -> str:
    return _setting("TIMEZONE", get_localzone_name())
