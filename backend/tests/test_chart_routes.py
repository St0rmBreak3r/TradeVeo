from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.main import create_app
from backend.app.api import chart_analysis as chart_routes
from backend.app.schemas.chart_analysis import ChartAnalysisResult
from backend.app.services import credentials

ORIGIN = "http://127.0.0.1:5173"


def png() -> bytes:
    image = Image.new("RGB", (200, 120), "white")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


class FakeProvider:
    def __init__(self, result=None, error=None):
        self.called = 0
        self.image = None
        self.result = result or ChartAnalysisResult.model_validate({
            "decision": "NO_TRADE", "symbol": None, "timeframe": None, "setup_type": None,
            "entry": None, "stop_loss": None, "targets": [], "confidence": "low",
            "confidence_note": "Unclear.", "observations": [], "rationale": "Cannot ground levels.",
            "invalidation": None, "warnings": ["No trade."],
        })
        self.error = error

    async def analyze(self, image_data_url):
        self.called += 1
        self.image = image_data_url
        if self.error:
            raise self.error
        return self.result


def client(tmp_path, monkeypatch, provider, key="test-key"):
    monkeypatch.setattr(chart_routes, "load_provider_config", lambda: chart_routes.AiProviderConfig())
    monkeypatch.setattr(chart_routes, "config_warning", lambda: None)
    monkeypatch.setattr(chart_routes, "resolve_api_key", lambda provider="openai": (key, "environment") if key else (None, "none"))
    app = create_app(database_url=f"sqlite:///{tmp_path / 'chart-test.sqlite3'}")
    app.state.chart_provider_factory = lambda api_key: provider
    return TestClient(app), provider


def test_consent_required_and_provider_not_called(tmp_path, monkeypatch):
    api, provider = client(tmp_path, monkeypatch, FakeProvider())
    with api:
        response = api.post("/api/chart-analysis", files={"image": ("chart.png", png(), "image/png")}, headers={"Origin": ORIGIN})
        assert response.status_code == 400
        assert provider.called == 0


def test_valid_consented_image_returns_structured_no_trade_without_persistence(tmp_path, monkeypatch):
    api, provider = client(tmp_path, monkeypatch, FakeProvider())
    with api:
        response = api.post("/api/chart-analysis", data={"consent": "true"}, files={"image": ("chart.png", png(), "image/png")}, headers={"Origin": ORIGIN})
        assert response.status_code == 200
        assert response.json()["decision"] == "NO_TRADE"
        assert provider.called == 1
        assert provider.image.startswith("data:image/png;base64,")
        assert api.get("/api/trades").json()["total"] == 0


def test_missing_key_prevents_provider_call(tmp_path, monkeypatch):
    api, provider = client(tmp_path, monkeypatch, FakeProvider(), key=None)
    with api:
        response = api.post("/api/chart-analysis", data={"consent": "true"}, files={"image": ("chart.png", png(), "image/png")}, headers={"Origin": ORIGIN})
        assert response.status_code == 503
        assert provider.called == 0


@pytest.mark.parametrize(("filename", "mime", "payload", "expected"), [
    ("chart.gif", "image/gif", b"GIF89a", 415),
    ("forged.png", "image/jpeg", png(), 415),
    ("bad.png", "image/png", b"broken", 422),
])
def test_invalid_image_rejected_before_provider(tmp_path, monkeypatch, filename, mime, payload, expected):
    api, provider = client(tmp_path, monkeypatch, FakeProvider())
    with api:
        response = api.post("/api/chart-analysis", data={"consent": "true"}, files={"image": (filename, payload, mime)}, headers={"Origin": ORIGIN})
        assert response.status_code == expected
        assert provider.called == 0


def test_provider_exception_is_redacted(tmp_path, monkeypatch):
    api, provider = client(tmp_path, monkeypatch, FakeProvider(error=RuntimeError("secret-key and raw image bytes")))
    with api:
        response = api.post("/api/chart-analysis", data={"consent": "true"}, files={"image": ("chart.png", png(), "image/png")}, headers={"Origin": ORIGIN})
        assert response.status_code == 502
        assert "secret-key" not in response.text
        assert "raw image" not in response.text


def test_ai_status_never_returns_secret(tmp_path, monkeypatch):
    api, _ = client(tmp_path, monkeypatch, FakeProvider(), key="very-secret-key")
    with api:
        response = api.get("/api/ai/status")
        assert response.status_code == 200
        assert response.json() == {"provider": "openai", "configured": True, "model": "gpt-5.4-mini", "credential_source": "environment"}
        assert "very-secret-key" not in response.text


def test_credential_save_and_delete_do_not_echo_or_store_in_database(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_routes, "load_provider_config", lambda: chart_routes.AiProviderConfig())
    monkeypatch.setattr(chart_routes, "config_warning", lambda: None)
    monkeypatch.setattr(chart_routes, "save_api_key", lambda secret, provider="openai": None)
    monkeypatch.setattr(chart_routes, "delete_saved_api_key", lambda provider="openai": None)
    monkeypatch.setattr(chart_routes, "resolve_api_key", lambda provider="openai": (None, "none"))
    api = TestClient(create_app(database_url=f"sqlite:///{tmp_path / 'chart-test.sqlite3'}"))
    with api:
        saved = api.put("/api/ai/credential", json={"api_key": "user-secret"}, headers={"Origin": ORIGIN})
        assert saved.status_code == 200
        assert "user-secret" not in saved.text
        deleted = api.delete("/api/ai/credential", headers={"Origin": ORIGIN})
        assert deleted.status_code == 200
        assert deleted.json() == {"configured": False}


def test_cross_origin_chart_upload_rejected(tmp_path, monkeypatch):
    api, provider = client(tmp_path, monkeypatch, FakeProvider())
    with api:
        response = api.post("/api/chart-analysis", data={"consent": "true"}, files={"image": ("chart.png", png(), "image/png")}, headers={"Origin": "https://attacker.example"})
        assert response.status_code == 403
        assert provider.called == 0
