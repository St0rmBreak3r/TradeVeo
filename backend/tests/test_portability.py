from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient

from backend.app.main import create_app

ORIGIN = "http://127.0.0.1:5173"


def payload(instrument: str = "EURUSD", notes: str | None = "journal note"):
    return {
        "instrument": instrument, "market": "forex", "direction": "long",
        "opened_at": "2026-10-21T09:30:00Z", "closed_at": "2026-10-21T10:00:00Z",
        "entry_price": "100", "exit_price": "105", "size": "2", "multiplier": "10",
        "fees": "1", "currency": "USD", "realized_pnl_override": None,
        "strategy": "Review", "tags": ["tag one", "tag two"], "notes": notes,
    }


def test_csv_export_preview_and_import_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "app-data"))
    with TestClient(create_app(f"sqlite:///{tmp_path / 'journal.sqlite3'}")) as client:
        created = client.post("/api/trades", json=payload(), headers={"Origin": ORIGIN})
        assert created.status_code == 201
        exported = client.get("/api/export.csv")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("text/csv")
        parsed = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
        assert parsed[0]["tags"] == '["tag one", "tag two"]'

        preview = client.post("/api/import/preview", files={"file": ("trades.csv", exported.content, "text/csv")}, headers={"Origin": ORIGIN})
        assert preview.status_code == 200
        details = preview.json()
        assert details["valid_count"] == 1
        assert details["errors"] == []
        assert client.get("/api/trades").json()["total"] == 1
        assert client.post("/api/import/commit", json={"preview_token": details["preview_token"], "confirm_valid_rows": False}, headers={"Origin": ORIGIN}).status_code == 400
        committed = client.post("/api/import/commit", json={"preview_token": details["preview_token"], "confirm_valid_rows": True}, headers={"Origin": ORIGIN})
        assert committed.status_code == 200
        assert committed.json() == {"created": 1, "skipped_invalid": 0}
        rows = client.get("/api/trades").json()["items"]
        assert len(rows) == 2
        assert rows[0]["tags"] == ["tag one", "tag two"]
        assert {row["net_pnl"] for row in rows} == {"99"}


def test_csv_formula_safe_export_and_invalid_row_preview(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "app-data"))
    with TestClient(create_app(f"sqlite:///{tmp_path / 'journal.sqlite3'}")) as client:
        assert client.post("/api/trades", json=payload(notes="=HYPERLINK(\"x\")"), headers={"Origin": ORIGIN}).status_code == 201
        csv_response = client.get("/api/export.csv")
        values = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
        assert values[0]["notes"].startswith("'=HYPERLINK")
        invalid_csv = csv_response.content.replace(b",100,105,2,10,1,USD", b",not-a-number,105,2,10,1,USD")
        preview = client.post("/api/import/preview", files={"file": ("invalid.csv", invalid_csv, "text/csv")}, headers={"Origin": ORIGIN})
        assert preview.status_code == 200
        assert preview.json()["valid_count"] == 0
        assert preview.json()["errors"]
        assert client.get("/api/trades").json()["total"] == 1


def test_backup_restore_requires_confirmation_and_recovers_deleted_trades(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "app-data"))
    with TestClient(create_app(f"sqlite:///{tmp_path / 'journal.sqlite3'}")) as client:
        assert client.post("/api/trades", json=payload(), headers={"Origin": ORIGIN}).status_code == 201
        assert client.post("/api/backups/restore", json={"backup_id": "00000000-0000-0000-0000-000000000000", "confirm": False}, headers={"Origin": ORIGIN}).status_code == 422
        backup = client.post("/api/backups", headers={"Origin": ORIGIN})
        assert backup.status_code == 200
        backup_info = backup.json()
        assert backup_info["trade_count"] == 1
        assert client.get("/api/backups").json()[0]["backup_id"] == backup_info["backup_id"]

        trade = client.get("/api/trades").json()["items"][0]
        assert client.delete(f"/api/trades/{trade['id']}", headers={"Origin": ORIGIN}).status_code == 204
        assert client.get("/api/trades").json()["total"] == 0
        restored = client.post("/api/backups/restore", json={"backup_id": backup_info["backup_id"], "confirm": True}, headers={"Origin": ORIGIN})
        assert restored.status_code == 200
        assert restored.json()["restored_count"] == 1
        assert restored.json()["pre_restore_backup_id"]
        recovered = client.get("/api/trades").json()["items"]
        assert len(recovered) == 1
        assert recovered[0]["instrument"] == "EURUSD"
        assert len(client.get("/api/backups").json()) == 2
