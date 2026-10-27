from fastapi.testclient import TestClient

from backend.app.main import create_app

ORIGIN = "http://127.0.0.1:5173"


def payload(instrument, currency, direction, entry, exit_price, opened, closed, size="1", fees="0"):
    return {
        "instrument": instrument,
        "market": "forex",
        "direction": direction,
        "opened_at": opened,
        "closed_at": closed,
        "entry_price": entry,
        "exit_price": exit_price,
        "size": size,
        "multiplier": "1",
        "fees": fees,
        "currency": currency,
        "realized_pnl_override": None,
        "strategy": "Review",
        "tags": [],
        "notes": None,
    }


def test_summary_uses_exact_decimal_and_separate_currencies(tmp_path):
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'journal.sqlite3'}"))
    with client:
        for item in [
            payload("EURUSD", "USD", "long", "0.1", "0.3", "2026-01-02T09:00:00Z", "2026-01-02T10:00:00Z", fees="0.1"),
            payload("GBPUSD", "GBP", "short", "5", "8", "2026-01-03T09:00:00Z", "2026-01-03T10:00:00Z"),
            payload("USDJPY", "USD", "long", "2", "2", "2026-01-04T09:00:00Z", "2026-01-04T10:00:00Z"),
        ]:
            assert client.post("/api/trades", json=item, headers={"Origin": ORIGIN}).status_code == 201
        open_item = payload("AUDUSD", "USD", "long", "1", None, "2026-01-05T09:00:00Z", None)
        assert client.post("/api/trades", json=open_item, headers={"Origin": ORIGIN}).status_code == 201

        response = client.get("/api/analytics/summary")
        assert response.status_code == 200
        summary = response.json()
        assert summary["open_count"] == 1
        currencies = {row["currency"]: row for row in summary["currencies"]}
        assert currencies["USD"]["closed_count"] == 2
        assert currencies["USD"]["net_pnl"] == "0.1"
        assert currencies["USD"]["wins"] == 1
        assert currencies["USD"]["breakeven"] == 1
        assert currencies["GBP"]["net_pnl"] == "-3"
        assert currencies["GBP"]["profit_factor"] == "0"
        assert len([point for point in summary["equity"] if point["currency"] == "USD"]) == 2


def test_calendar_groups_by_local_date_and_currency(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEVEO_TIMEZONE", "America/New_York")
    client = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'journal.sqlite3'}"))
    with client:
        for item in [
            payload("EURUSD", "USD", "long", "1", "2", "2026-07-01T01:00:00Z", "2026-07-01T01:00:00Z"),
            payload("GBPUSD", "GBP", "long", "1", "2", "2026-07-01T02:00:00Z", "2026-07-01T02:00:00Z"),
        ]:
            assert client.post("/api/trades", json=item, headers={"Origin": ORIGIN}).status_code == 201
        result = client.get("/api/calendar?year=2026&month=6")
        assert result.status_code == 200
        days = result.json()["days"]
        assert {(day["date"], day["currency"], day["net_pnl"]) for day in days} == {
            ("2026-06-30", "USD", "1"),
            ("2026-06-30", "GBP", "1"),
        }
