from decimal import Decimal

from fastapi.testclient import TestClient

from backend.app.main import create_app

ORIGIN = "http://127.0.0.1:5173"

LONG = {
    "instrument": "EURUSD",
    "market": "forex",
    "direction": "long",
    "opened_at": "2026-10-21T09:30:00Z",
    "closed_at": "2026-10-21T10:00:00Z",
    "entry_price": "100",
    "exit_price": "105",
    "size": "2",
    "multiplier": "10",
    "fees": "1",
    "currency": "USD",
    "realized_pnl_override": None,
    "strategy": "Breakout",
    "tags": ["london"],
    "notes": "",
}


def client_for(tmp_path):
    return TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'journal.sqlite3'}"))


def create(client, payload=LONG):
    return client.post("/api/trades", json=payload, headers={"Origin": ORIGIN})


def test_create_trade_calculates_decimal_pnl_and_persists(tmp_path):
    with client_for(tmp_path) as client:
        response = create(client)
        assert response.status_code == 201
        trade = response.json()
        assert trade["gross_pnl"] == "100"
        assert trade["net_pnl"] == "99"
        assert client.get("/api/trades").json()["items"] == [trade]
        assert client.get(f"/api/trades/{trade['id']}").json()["id"] == trade["id"]

    with client_for(tmp_path) as client:
        assert client.get("/api/trades").json()["items"][0]["net_pnl"] == "99"


def test_short_override_open_and_close_validation(tmp_path):
    short = {**LONG, "direction": "short", "entry_price": "105", "exit_price": "100"}
    override = {**LONG, "realized_pnl_override": "-8"}
    with client_for(tmp_path) as client:
        results = [create(client, payload).json() for payload in (short, override)]
        assert {Decimal(row["net_pnl"]) for row in results} == {Decimal("99"), Decimal("-9")}
        open_position = create(client, {**LONG, "closed_at": None, "exit_price": None}).json()
        assert open_position["gross_pnl"] is None
        assert open_position["net_pnl"] is None
        assert create(client, {**LONG, "closed_at": None}).status_code == 422
        assert create(client, {**LONG, "entry_price": 100}).status_code == 422
        assert create(client, {**LONG, "closed_at": "2026-10-21T09:00:00Z"}).status_code == 422
        assert create(client, {**LONG, "unknown": "rejected"}).status_code == 422


def test_update_delete_filters_sort_pagination_and_origin_guard(tmp_path):
    with client_for(tmp_path) as client:
        first = create(client).json()
        second = create(client, {**LONG, "instrument": "GBPUSD", "currency": "GBP", "entry_price": "10", "exit_price": "11"}).json()
        updated = client.put(f"/api/trades/{first['id']}", json={**LONG, "notes": "reviewed"}, headers={"Origin": ORIGIN})
        assert updated.status_code == 200
        assert updated.json()["notes"] == "reviewed"
        assert client.get("/api/trades?instrument=EURUSD&currency=USD").json()["total"] == 1
        sorted_list = client.get("/api/trades?sort=instrument&order=asc&limit=1").json()
        assert sorted_list["items"][0]["instrument"] == "EURUSD"
        assert sorted_list["total"] == 2
        assert client.get("/api/trades?sort=instrument%3BDROP%20TABLE%20trades").status_code == 422
        assert client.get("/api/trades?limit=500").status_code == 422
        assert client.delete(f"/api/trades/{second['id']}", headers={"Origin": ORIGIN}).status_code == 204
        assert client.delete(f"/api/trades/{first['id']}", headers={"Origin": ORIGIN}).status_code == 204
        assert client.get("/api/trades").json()["total"] == 0
        assert client.post("/api/trades", json=LONG, headers={"Origin": "https://attacker.example"}).status_code == 403


def test_list_reports_total_beyond_page_size(tmp_path):
    with client_for(tmp_path) as client:
        for i in range(3):
            assert create(client, {**LONG, "instrument": f"FX{i}"}).status_code == 201
        page = client.get("/api/trades?limit=2&offset=1").json()
        assert len(page["items"]) == 2
        assert page["total"] == 3
