from __future__ import annotations

import io

import pytest
from PIL import Image
from pydantic import ValidationError

from backend.app.schemas.chart_analysis import ChartAnalysisResult
from backend.app.services.chart_images import MAX_CHART_BYTES, validate_chart_image


def result(**overrides):
    base = {
        "decision": "NO_TRADE", "symbol": None, "timeframe": None, "setup_type": None,
        "entry": None, "stop_loss": None, "targets": [], "confidence": "low",
        "confidence_note": "Price labels are unreadable.", "observations": [],
        "rationale": "Insufficient chart detail.", "invalidation": None,
        "warnings": ["No action."],
    }
    base.update(overrides)
    return base


def image_bytes(image_format: str = "PNG", size=(320, 200)) -> bytes:
    image = Image.new("RGB", size, "white")
    out = io.BytesIO()
    image.save(out, format=image_format)
    return out.getvalue()


def test_no_trade_schema_accepts_empty_actionable_levels():
    parsed = ChartAnalysisResult.model_validate(result())
    assert parsed.decision == "NO_TRADE"
    assert parsed.targets == []


def test_no_trade_cannot_contain_actionable_levels():
    with pytest.raises(ValidationError, match="NO_TRADE"):
        ChartAnalysisResult.model_validate(result(entry={"low": 1.1, "high": 1.2, "basis": "Visible"}))


def test_signal_rejects_non_finite_and_bad_entry_zone():
    with pytest.raises(ValidationError):
        ChartAnalysisResult.model_validate(result(decision="LONG", entry={"low": 2.0, "high": 1.0, "basis": "levels"}, confidence="medium"))
    with pytest.raises(ValidationError):
        ChartAnalysisResult.model_validate(result(decision="LONG", entry={"low": float("nan"), "high": 2.0, "basis": "levels"}, confidence="medium"))


def test_image_validation_returns_matching_mime_base64_data_url():
    mime, data_url = validate_chart_image(image_bytes(), "image/png")
    assert mime == "image/png"
    assert data_url.startswith("data:image/png;base64,")


def test_image_validation_accepts_jpeg_and_rejects_mismatched_claim():
    data = image_bytes("JPEG")
    assert validate_chart_image(data, "image/jpeg")[0] == "image/jpeg"
    with pytest.raises(TypeError, match="does not match"):
        validate_chart_image(data, "image/png")


def test_image_validation_rejects_empty_bad_format_and_corrupt_data():
    with pytest.raises(ValueError, match="non-empty"):
        validate_chart_image(b"", "image/png")
    with pytest.raises(TypeError, match="PNG or JPEG"):
        validate_chart_image(image_bytes(), "image/gif")
    with pytest.raises(ValueError, match="valid PNG or JPEG"):
        validate_chart_image(b"not an image", "image/png")


def test_image_validation_rejects_oversize_and_large_dimensions():
    with pytest.raises(OverflowError, match="10 MiB"):
        validate_chart_image(b"a" * (MAX_CHART_BYTES + 1), "image/png")
    with pytest.raises(OverflowError, match="dimensions"):
        validate_chart_image(image_bytes(size=(10001, 1)), "image/png")
