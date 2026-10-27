from __future__ import annotations

import os
from pathlib import Path

from tzlocal import get_localzone_name


def database_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "TRYEDVEO" / "journal.sqlite3"
    return Path.home() / ".local" / "share" / "TRYEDVEO" / "journal.sqlite3"


def database_url() -> str:
    return os.environ.get("TRYEDVEO_DATABASE_URL", f"sqlite:///{database_path()}")


def backup_directory() -> Path:
    return database_path().parent / "backups"


def ui_origin() -> str:
    return os.environ.get("TRYEDVEO_UI_ORIGIN", "http://127.0.0.1:5173")


def timezone_name() -> str:
    return os.environ.get("TRYEDVEO_TIMEZONE", get_localzone_name())
