from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import backup_directory

FORMAT_VERSION = 1
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_DATABASE_BYTES = 1024 * 1024 * 1024


def _db_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///" ):
        raise ValueError("Backups require the local SQLite database.")
    return Path(database_url.removeprefix("sqlite:///"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _manifest(db_path: Path) -> dict[str, Any]:
    with closing(sqlite3.connect(db_path)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise ValueError("Local journal database failed its integrity check.")
    return {"format_version": FORMAT_VERSION, "schema_version": "0001", "created_at": _utc_now(), "trade_count": count}


def create_backup(database_url: str, engine: Engine | None = None) -> dict[str, Any]:
    db_path = _db_path(database_url)
    if not db_path.exists():
        raise ValueError("Journal database does not exist yet.")
    directory = backup_directory()
    directory.mkdir(parents=True, exist_ok=True)
    backup_id = str(uuid.uuid4())
    target = directory / f"tryedveo-{backup_id}.zip"
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        snapshot = Path(temporary) / "journal.sqlite3"
        if engine is not None:
            with engine.connect() as source, closing(sqlite3.connect(snapshot)) as destination:
                raw = source.connection.driver_connection
                raw.backup(destination)
                destination.commit()
        else:
            with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(snapshot)) as destination:
                source.backup(destination)
        metadata = _manifest(snapshot)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "journal.sqlite3")
            archive.writestr("manifest.json", json.dumps(metadata, indent=2))
    stat = target.stat()
    return {"backup_id": backup_id, "created_at": metadata["created_at"], "trade_count": metadata["trade_count"], "size_bytes": stat.st_size}


def list_backups() -> list[dict[str, Any]]:
    directory = backup_directory()
    if not directory.exists():
        return []
    results = []
    for archive_path in directory.glob("tryedveo-*.zip"):
        try:
            backup_id = archive_path.stem.removeprefix("tryedveo-")
            uuid.UUID(backup_id)
            with zipfile.ZipFile(archive_path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format_version") != FORMAT_VERSION:
                continue
            results.append({"backup_id": backup_id, "created_at": manifest["created_at"], "trade_count": manifest["trade_count"], "size_bytes": archive_path.stat().st_size})
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
            continue
    return sorted(results, key=lambda item: item["created_at"], reverse=True)


def restore_backup(backup_id: str, confirm: bool, database_url: str, engine: Engine, session_factory: sessionmaker) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Restore requires explicit confirmation.")
    try:
        safe_id = str(uuid.UUID(backup_id))
    except ValueError as exc:
        raise ValueError("Invalid backup identifier.") from exc
    archive_path = backup_directory() / f"tryedveo-{safe_id}.zip"
    if not archive_path.is_file() or archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Backup is missing or exceeds the allowed size.")
    with tempfile.TemporaryDirectory(dir=backup_directory()) as temporary:
        temporary_path = Path(temporary)
        staged = temporary_path / "journal.sqlite3"
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != 2 or set(names) != {"manifest.json", "journal.sqlite3"}:
                raise ValueError("Backup contains unexpected files.")
            info = archive.getinfo("journal.sqlite3")
            if info.file_size > MAX_DATABASE_BYTES or info.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError("Backup database exceeds the allowed size.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format_version") != FORMAT_VERSION or manifest.get("schema_version") != "0001":
                raise ValueError("Backup format or schema version is unsupported.")
            with archive.open("journal.sqlite3") as source, staged.open("wb") as destination:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)
        with closing(sqlite3.connect(staged)) as check:
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {row[0] for row in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            count = check.execute("SELECT COUNT(*) FROM trades").fetchone()[0] if "trades" in tables else -1
        if integrity != "ok" or count != manifest.get("trade_count") or "trades" not in tables:
            raise ValueError("Backup database failed validation.")

        before = create_backup(database_url, engine)
        destination = _db_path(database_url)
        staged_replacement = temporary_path / "replacement.sqlite3"
        staged_replacement.write_bytes(staged.read_bytes())
        engine.dispose()
        try:
            os.replace(staged_replacement, destination)
            with engine.connect() as connection:
                restored_count = connection.execute(text("SELECT COUNT(*) FROM trades")).scalar_one()
            if restored_count != count:
                raise ValueError("Restored journal count did not match the backup.")
        except Exception:
            if before:
                restore_path = backup_directory() / f"tryedveo-{before['backup_id']}.zip"
                rollback_db = temporary_path / "rollback.sqlite3"
                with zipfile.ZipFile(restore_path) as rollback_archive, rollback_archive.open("journal.sqlite3") as source, rollback_db.open("wb") as destination_file:
                    while chunk := source.read(1024 * 1024):
                        destination_file.write(chunk)
                os.replace(rollback_db, destination)
            raise
    return {"restored_count": count, "pre_restore_backup_id": before["backup_id"]}
