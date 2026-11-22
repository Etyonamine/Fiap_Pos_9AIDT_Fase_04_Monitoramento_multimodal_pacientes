import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import main


def test_lifespan_stops_webhook_even_if_application_raises(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(main, "initialize", lambda: calls.append("initialize"))
    monkeypatch.setattr(main, "start_worker", lambda: calls.append("start"))
    monkeypatch.setattr(main, "stop_worker", lambda: calls.append("stop"))
    monkeypatch.setattr(main, "shutdown_camera", lambda: calls.append("camera"))
    monkeypatch.setattr(main, "shutdown_monitor", lambda: calls.append("monitor"))
    monkeypatch.setattr(main, "executor", SimpleNamespace(shutdown=lambda **_kwargs: calls.append("video")))
    monkeypatch.setattr(main, "audio_executor", SimpleNamespace(shutdown=lambda **_kwargs: calls.append("audio")))

    def unavailable_samples():
        raise HTTPException(503, "Exemplo sintético indisponível.")

    monkeypatch.setattr(main, "load_samples", unavailable_samples)

    async def run():
        async with main.lifespan(main.app):
            raise RuntimeError("synthetic application failure")

    with pytest.raises(RuntimeError, match="synthetic application failure"):
        asyncio.run(run())
    assert calls == ["initialize", "start", "camera", "video", "monitor", "audio", "stop"]
    assert "Exemplos indisponíveis" in caplog.text
