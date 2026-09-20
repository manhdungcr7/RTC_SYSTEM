"""Router regression tests without remote encoders or retrieval services."""
from types import SimpleNamespace

import numpy as np
import pytest

from api.routers import temporal as temporal_router
from api.schemas.temporal import TemporalRequest


@pytest.mark.parametrize("manual, expected", [
    (None, ["Bếp. Đảo thức ăn", "Bếp. Thêm nước"]),
    ([], ["Bếp. Đảo thức ăn", "Bếp. Thêm nước"]),
    (["", ""], ["", ""]),
    ([" \t", "\n"], ["", ""]),
    (["", " 1,5 lít "], ["", "1,5 lít"]),
    ([""], ["", "Bếp. Thêm nước"]),
    (["  muối "], ["muối", "Bếp. Thêm nước"]),
])
def test_explicit_empty_overrides_disable_text_but_missing_entries_keep_legacy_fallback(
    monkeypatch, manual, expected,
):
    captured = {}

    def capture_search(*args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(temporal_router, "search_temporal", capture_search)
    req = TemporalRequest(
        events=["Đảo thức ăn", "Thêm nước"], context="Bếp.", split_clauses=False,
        ocr_queries=manual, asr_queries=manual,
    )
    encoders = SimpleNamespace(metaclip2=SimpleNamespace(
        encode=lambda texts: np.eye(len(texts), dtype=np.float32)))
    temporal_router.temporal(req, faiss=None, meili=None, encoders=encoders, media_index=None)

    assert captured["ocr_texts"] == expected
    assert captured["asr_texts"] == expected


def test_text_channels_keep_independent_event_slots_and_disabled_signal_wins(monkeypatch):
    captured = {}

    def capture_search(*args, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(temporal_router, "search_temporal", capture_search)
    req = TemporalRequest(
        events=["Đảo thức ăn", "Thêm nước"], split_clauses=False,
        ocr_queries=["", "1,5 lít"], asr_queries=["muối", ""],
        signals={"ocr": {"enabled": True}, "asr": {"enabled": True}},
    )
    encoders = SimpleNamespace(metaclip2=SimpleNamespace(
        encode=lambda texts: np.eye(len(texts), dtype=np.float32)))
    temporal_router.temporal(req, faiss=None, meili=None, encoders=encoders, media_index=None)
    assert captured["ocr_texts"] == ["", "1,5 lít"]
    assert captured["asr_texts"] == ["muối", ""]

    req.signals["ocr"].enabled = False
    req.signals["asr"].enabled = False
    temporal_router.temporal(req, faiss=None, meili=None, encoders=encoders, media_index=None)
    assert captured["ocr_texts"] == ["", ""]
    assert captured["asr_texts"] == ["", ""]
