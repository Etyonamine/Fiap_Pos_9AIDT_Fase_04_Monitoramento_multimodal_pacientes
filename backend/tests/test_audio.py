import array
import builtins
import json
import math
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database
from app.routers import audio
from app.services import azure_service
from app.services.audio_analysis import acoustic_analysis, critical_terms


def make_wav(path, seconds=3, amplitude=6000):
    samples = array.array("h", (
        int(amplitude * math.sin(2 * math.pi * 220 * index / 16000))
        for index in range(int(seconds * 16000))
    ))
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(samples.tobytes())
    return path


@pytest.fixture
def config(monkeypatch):
    for name in ("AZURE_TEXT_ANALYTICS_KEY", "AZURE_TEXT_ANALYTICS_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    values = {
        "AZURE_SPEECH_KEY": "test-speech-key", "AZURE_SPEECH_REGION": "eastus",
        "AZURE_LANGUAGE_KEY": "test-language-key",
        "AZURE_LANGUAGE_ENDPOINT": "https://test.cognitiveservices.azure.com",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setattr(audio, "DATA_DIR", tmp_path)
    database.initialize()
    monkeypatch.setattr(audio.executor, "submit", lambda fn, *args: fn(*args))
    app = FastAPI()
    app.include_router(audio.router)
    with TestClient(app) as client:
        yield client


def upload(client, path):
    with path.open("rb") as file:
        response = client.post("/api/audios", files={"file": (path.name, file, "audio/wav")})
    assert response.status_code == 202
    return response.json()


def speech_result():
    return {
        "provider": "Azure Speech to Text", "language": "pt-BR",
        "text": "Tenho cansaço e falta de ar. Não tenho dor no peito.",
        "segments": [{"text": "Tenho cansaço e falta de ar.", "offset": 0.5,
                      "duration": 2, "confidence": 0.91}],
    }


def test_import_replay_range_and_retention(client, tmp_path):
    original = make_wav(tmp_path / "consulta.wav")
    record = upload(client, original)
    assert record["status"] == "uploaded"
    assert record["duration"] == 3
    assert record["result"] is None
    assert record["acoustic"]["waveform"]
    assert not list(tmp_path.glob("audio-upload-*"))
    response = client.get(record["url"], headers={"Range": "bytes=0-43"})
    assert response.status_code == 206
    assert response.content.startswith(b"RIFF")
    assert response.headers["content-type"] == "audio/wav"
    database.initialize()
    assert client.get("/api/audios").json()[0]["id"] == record["id"]
    assert client.delete(f"/api/audios/{record['id']}").status_code == 204
    assert not audio.normalized_path(record["id"]).exists()
    assert client.get(record["url"]).status_code == 404


def test_mp3_conversion(client, tmp_path):
    import subprocess
    source = make_wav(tmp_path / "source.wav")
    mp3 = tmp_path / "consulta.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), str(mp3)], check=True)
    record = upload(client, mp3)
    assert record["status"] == "uploaded"
    with wave.open(str(audio.normalized_path(record["id"])), "rb") as converted:
        assert (converted.getnchannels(), converted.getsampwidth(), converted.getframerate()) == (1, 2, 16000)


def test_full_analysis_and_partial_language_failure(client, tmp_path, config, monkeypatch):
    monkeypatch.setattr(audio, "transcribe", lambda *args: speech_result())
    language = {
        "provider": "Azure Text Analytics", "key_phrases": ["cansaço", "falta de ar"],
        "sentiment": {"label": "negative", "scores": {"positive": .01, "neutral": .09, "negative": .9}},
    }
    monkeypatch.setattr(audio, "analyze_language", lambda *args: language)
    record = upload(client, make_wav(tmp_path / "consulta.wav"))
    response = client.post(f"/api/audios/{record['id']}/analyze")
    assert response.status_code == 202
    assert response.json()["status"] == "ready"
    result = response.json()["result"]
    assert result["language"] == language
    assert [(m["term"], m["negated"]) for m in result["critical_terms"]] == [
        ("cansaço", False), ("falta de ar", False), ("dor no peito", True),
    ]

    def unavailable(*args):
        raise azure_service.AzureAudioError("Azure Language indisponível.")
    monkeypatch.setattr(audio, "analyze_language", unavailable)
    failed = client.post(f"/api/audios/{record['id']}/analyze").json()
    assert failed["status"] == "failed"
    assert failed["error"] == "Azure Language indisponível."
    assert failed["result"]["transcription"] == speech_result()
    assert "language" not in failed["result"]
    assert client.get(failed["url"]).status_code == 200


def test_no_fake_transcription_on_speech_failure(client, tmp_path, config, monkeypatch):
    def unavailable(*args):
        raise azure_service.AzureAudioError("Sem fala reconhecida.")
    monkeypatch.setattr(audio, "transcribe", unavailable)
    record = upload(client, make_wav(tmp_path / "consulta.wav"))
    failed = client.post(f"/api/audios/{record['id']}/analyze").json()
    assert failed["status"] == "failed"
    assert failed["result"] is None
    assert failed["url"] == record["url"]


def test_missing_speech_sdk_reports_install_instructions(tmp_path, config, monkeypatch):
    original_import = builtins.__import__

    def import_without_speech_sdk(name, *args, **kwargs):
        if name == "azure.cognitiveservices.speech":
            raise ModuleNotFoundError("No module named 'azure'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_speech_sdk)
    with pytest.raises(azure_service.AzureAudioError, match="SDK Azure Speech não instalado"):
        azure_service.transcribe(tmp_path / "audio.wav", 1, {})


@pytest.mark.parametrize("name,value", [
    ("AZURE_SPEECH_KEY", None), ("AZURE_SPEECH_REGION", None),
    ("AZURE_LANGUAGE_KEY", None), ("AZURE_LANGUAGE_ENDPOINT", None),
    ("AZURE_SPEECH_KEY", "sua_chave_speech"),
    ("AZURE_LANGUAGE_KEY", "sua_chave_language"),
    ("AZURE_SPEECH_REGION", "https://eastus.api.cognitive.microsoft.com"),
    ("AZURE_LANGUAGE_ENDPOINT", "http://test.cognitiveservices.azure.com"),
])
def test_invalid_configuration_keeps_replay_available(
    client, tmp_path, config, monkeypatch, caplog, name, value,
):
    if value is None:
        monkeypatch.delenv(name)
    else:
        monkeypatch.setenv(name, value)
    submitted = []
    record = upload(client, make_wav(tmp_path / "consulta.wav"))
    monkeypatch.setattr(audio.executor, "submit", lambda *args: submitted.append(args))
    response = client.post(f"/api/audios/{record['id']}/analyze")
    assert response.status_code == 503
    assert name in response.json()["detail"]
    assert f"Análise do áudio {record['id']} não iniciada" in caplog.text
    assert name in caplog.text
    assert not submitted
    assert client.get(f"/api/audios/{record['id']}").json() == record
    settings = client.get("/api/audios/configuration").json()
    assert not settings["configured"]
    for key in ("AZURE_SPEECH_KEY", "AZURE_LANGUAGE_KEY"):
        assert config[key] not in caplog.text + json.dumps(settings) + response.text
    assert client.get(record["url"]).status_code == 200


def test_configuration_legacy_names(config, monkeypatch):
    monkeypatch.delenv("AZURE_LANGUAGE_KEY")
    monkeypatch.delenv("AZURE_LANGUAGE_ENDPOINT")
    monkeypatch.setenv("AZURE_TEXT_ANALYTICS_KEY", "legacy-key")
    monkeypatch.setenv("AZURE_TEXT_ANALYTICS_ENDPOINT", "https://legacy.cognitiveservices.azure.com/")
    assert azure_service.configuration()["AZURE_LANGUAGE_KEY"] == "legacy-key"
    assert azure_service.configuration()["AZURE_LANGUAGE_ENDPOINT"].endswith(".com")


@pytest.mark.parametrize("name,content,status", [
    ("consulta.exe", b"audio", 415), ("empty.wav", b"", 422),
])
def test_reject_upload(client, tmp_path, name, content, status):
    response = client.post("/api/audios", files={"file": (name, content)})
    assert response.status_code == status
    assert not list(tmp_path.glob("audio-upload-*"))


def test_upload_size_and_duration_limits(client, tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "MAX_BYTES", 20)
    assert client.post("/api/audios", files={"file": ("large.wav", b"x" * 21)}).status_code == 413
    monkeypatch.setattr(audio, "MAX_BYTES", 100 * 1024 * 1024)
    monkeypatch.setattr(audio, "MAX_SECONDS", 2)
    record = upload(client, make_wav(tmp_path / "too-long.wav", seconds=3))
    assert record["status"] == "failed"
    assert record["url"] is None
    assert not audio.normalized_path(record["id"]).exists()


def test_bad_audio_is_explicit_failure(client):
    response = client.post("/api/audios", files={"file": ("broken.wav", b"invalid audio")})
    assert response.status_code == 202
    assert response.json()["status"] == "failed"
    assert response.json()["error"]
    assert response.json()["url"] is None


def test_failed_file_deletion_preserves_record_for_retry(client, tmp_path, monkeypatch):
    record = upload(client, make_wav(tmp_path / "consulta.wav"))
    def denied(*args, **kwargs):
        raise PermissionError("Test deletion failure")
    monkeypatch.setattr(Path, "unlink", denied)
    response = client.delete(f"/api/audios/{record['id']}")
    assert response.status_code == 500
    assert "excluir" in response.json()["detail"]
    assert client.get(f"/api/audios/{record['id']}").status_code == 200


def test_language_empty_input_is_explicit_error(config):
    with pytest.raises(azure_service.AzureAudioError, match="vazia"):
        azure_service.analyze_language("   ", config)


def test_duplicates_busy_delete_and_restart(client, tmp_path, config, monkeypatch):
    record = upload(client, make_wav(tmp_path / "consulta.wav"))
    monkeypatch.setattr(audio.executor, "submit", lambda *args: None)
    assert client.post(f"/api/audios/{record['id']}/analyze").json()["status"] == "queued"
    assert client.post(f"/api/audios/{record['id']}/analyze").status_code == 409
    assert client.delete(f"/api/audios/{record['id']}").status_code == 409
    database.initialize()
    failed = client.get(f"/api/audios/{record['id']}").json()
    assert failed["status"] == "failed"
    assert "interrompido" in failed["error"]
    assert client.get(failed["url"]).status_code == 200


def test_acoustic_thresholds_and_silence(tmp_path):
    silence = acoustic_analysis(make_wav(tmp_path / "silence.wav", amplitude=0))
    assert silence["rms_energy"] == 0
    assert silence["low_energy_ratio"] == 1
    assert silence["longest_low_energy_seconds"] == 3
    assert len(silence["indicators"]) == 2
    assert acoustic_analysis(make_wav(tmp_path / "voice.wav"))["low_energy_ratio"] == 0
    assert silence["energy_change_db"] is None


def test_acoustic_intensity_reduction_is_measured_not_diagnosed(tmp_path):
    path = tmp_path / "variation.wav"
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        for amplitude in (12000, 6000, 3000):
            samples = array.array("h", (
                int(amplitude * math.sin(2 * math.pi * 220 * index / 16000))
                for index in range(16000 * 10)
            ))
            output.writeframes(samples.tobytes())
    result = acoustic_analysis(path)
    assert result["energy_change_db"] == pytest.approx(-12.04, abs=.02)
    assert any("6 dB" in indicator for indicator in result["indicators"])
    assert "não detectam nem diagnosticam" in result["limitation"]


@pytest.mark.parametrize("text,expected", [
    ("Não tenho falta de ar, mas tenho fadiga.", [("falta de ar", True), ("fadiga", False)]),
    ("Não consigo respirar.", [("não consigo respirar", False)]),
    ("Não consigo respirar e tenho cansaço.", [("não consigo respirar", False), ("cansaço", False)]),
    ("Sem cansaço ou falta de ar.", [("cansaço", True), ("falta de ar", True)]),
    ("Dor no peito ausente. Tenho dispneia.", [("dor no peito", True), ("dispneia", False)]),
    ("Dor no peitoral e descansaço.", []),
])
def test_terms_context_and_negation(text, expected):
    assert [(m["term"], m["negated"]) for m in critical_terms(text)] == expected


def language_transport(request):
    documents = json.loads(request.content)["documents"]
    if request.url.path.endswith("sentiment"):
        results = [{"id": document["id"], "sentiment": "negative",
                    "confidenceScores": {"positive": .01, "neutral": .09, "negative": .9}}
                   for document in documents]
    else:
        results = [{"id": document["id"], "keyPhrases": ["falta de ar"]} for document in documents]
    return httpx.Response(200, json={"documents": results, "errors": []})


def mock_language_client(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(azure_service.httpx, "Client",
                        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_long_text_azure_batching(config, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return language_transport(request)
    mock_language_client(monkeypatch, handler)
    text = "Sinto falta de ar. " * 3000
    result = azure_service.analyze_language(text, config)
    chunks = result["sentiment"]["chunks"]
    assert len(chunks) > 10
    assert all(len(chunk["text"]) <= 4500 for chunk in chunks)
    assert result["sentiment"]["label"] == "negative"
    assert result["sentiment"]["scores"]["negative"] == .9
    assert result["key_phrases"] == ["falta de ar"]
    assert len(calls) == 4
    assert all(len(json.loads(call.content)["documents"]) <= 10 for call in calls)


@pytest.mark.parametrize("response", [
    httpx.Response(401), httpx.Response(429), httpx.Response(500),
    httpx.Response(200, json={"documents": [], "errors": [{"id": "0"}]}),
    httpx.Response(200, json={"documents": [{"id": "0", "sentiment": "negative",
                                           "confidenceScores": {"positive": 2}}]}),
])
def test_language_errors_are_not_success(config, monkeypatch, response):
    mock_language_client(monkeypatch, lambda request: response)
    with pytest.raises(azure_service.AzureAudioError):
        azure_service.analyze_language("Falta de ar.", config)


@pytest.mark.parametrize("outcome", ["success", "empty", "canceled", "malformed"])
def test_sdk_continuous_transcription_over_sixty_seconds(config, tmp_path, monkeypatch, outcome):
    import azure.cognitiveservices.speech as speechsdk

    class Signal:
        def connect(self, callback):
            self.callback = callback
        def emit(self, event):
            self.callback(event)

    class Recognizer:
        def __init__(self, **kwargs):
            self.recognized = Signal()
            self.canceled = Signal()
            self.session_stopped = Signal()
        def start_continuous_recognition_async(self):
            results = ((0, "Tenho cansaço."), (610_000_000, "Sinto falta de ar.")) if outcome != "empty" else ()
            for offset, text in results:
                self.recognized.emit(SimpleNamespace(result=SimpleNamespace(
                    reason=speechsdk.ResultReason.RecognizedSpeech,
                    json=json.dumps({"NBest": [{"Confidence": .92 if outcome != "malformed" else 2}]}),
                    text=text, offset=offset, duration=20_000_000,
                )))
            if outcome == "canceled":
                self.canceled.emit(SimpleNamespace(result=SimpleNamespace(
                    cancellation_details=SimpleNamespace(reason=speechsdk.CancellationReason.Error)
                )))
            self.session_stopped.emit(None)
            return SimpleNamespace(get=lambda: None)
        def stop_continuous_recognition_async(self):
            return SimpleNamespace(get=lambda: None)

    monkeypatch.setattr(speechsdk, "SpeechRecognizer", Recognizer)
    if outcome != "success":
        with pytest.raises(azure_service.AzureAudioError):
            azure_service.transcribe(make_wav(tmp_path / "consulta.wav"), 70, config)
        return
    result = azure_service.transcribe(make_wav(tmp_path / "consulta.wav"), 70, config)
    assert result["text"] == "Tenho cansaço. Sinto falta de ar."
    assert result["segments"][1]["offset"] == 61
    assert result["segments"][1]["confidence"] == .92
