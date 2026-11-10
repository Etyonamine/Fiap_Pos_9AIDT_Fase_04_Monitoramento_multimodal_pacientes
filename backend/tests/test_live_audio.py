import io
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import Future
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import azure_service, live_audio


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        if time.monotonic() >= deadline:
            pytest.fail("Streaming worker did not reach expected state.")
        time.sleep(.005)


@pytest.fixture
def streaming(tmp_path, monkeypatch):
    streams = []
    language_jobs = []

    class Decoder:
        def __init__(self):
            self.stdout = io.BytesIO(b"\x01\x00" * 160000)
            self.terminated = False

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            return 0

    class Speech:
        def __init__(self, config, recognized, partial, failed):
            self.recognized = recognized
            self.partial = partial
            self.failed = failed
            self.data = b""
            self.finished = False
            self.stopped = False
            streams.append(self)

        def start(self):
            pass

        def write(self, data):
            self.data += data

        def finish(self):
            self.finished = True

        def stop(self):
            self.stopped = True

    def submit(*args):
        future = Future()
        language_jobs.append(future)
        return future

    monkeypatch.setattr(live_audio, "configuration", lambda **kwargs: {})
    monkeypatch.setattr(live_audio, "SpeechStream", Speech)
    monkeypatch.setattr(live_audio.StreamingAudio, "open_decoder", lambda self: Decoder())
    monkeypatch.setattr(live_audio.language_executor, "submit", submit)
    sessions = []

    def create(start=0):
        session = live_audio.StreamingAudio(tmp_path / "source.mp4", start, 10)
        sessions.append(session)
        return session

    yield create, streams, language_jobs
    for session in sessions:
        session.close()
        if session.thread:
            assert not session.thread.is_alive()


def test_continuous_connection_sends_only_played_pcm_without_three_second_wait(streaming):
    create, streams, _ = streaming
    session = create()
    assert session.thread is None
    session.advance(0, False)
    assert session.thread is None
    session.advance(.2, False)
    wait_for(lambda: len(streams) == 1 and len(streams[0].data) == 6400)
    assert session.snapshot()["audio_until"] == .2
    session.advance(.5, False)
    wait_for(lambda: len(streams[0].data) == 16000)
    assert len(streams) == 1
    assert session.snapshot()["audio_until"] == .5
    time.sleep(.03)
    assert len(streams[0].data) == 16000
    assert session.snapshot()["events"] == []


def test_final_speech_alert_is_available_while_language_is_still_blocked(streaming):
    create, streams, jobs = streaming
    session = create()
    session.advance(.8, False)
    wait_for(lambda: len(streams) == 1 and len(streams[0].data) == 25600)
    streams[0].partial("Socorro")
    provisional = session.snapshot()
    assert provisional["partial_text"] == "Socorro"
    assert provisional["events"] == [{
        "timestamp": 0, "kind": "Fala: socorro", "severity": "critical",
        "source": "audio", "provisional": True,
    }]
    assert not jobs
    streams[0].recognized("Socorro. Não preciso de ajuda.", .1, .6)
    state = session.snapshot()
    assert state["partial_text"] == ""
    assert state["events"] == [{
        "timestamp": .1, "kind": "Fala: socorro", "severity": "critical", "source": "audio",
        "provisional": False,
    }]
    assert state["language_pending"]
    assert state["transcripts"][0]["language"] is None
    assert not jobs[0].done()
    jobs[0].set_result({"key_phrases": ["Socorro"], "sentiment": {"label": "negative"}})
    state = session.snapshot()
    assert not state["language_pending"]
    assert state["transcripts"][0]["language"]["sentiment"]["label"] == "negative"


@pytest.mark.parametrize("final_text", ["Não preciso de ajuda.", "Estou tranquilo.", ""])
def test_provisional_alert_is_retracted_when_partial_or_final_text_is_corrected(streaming, final_text):
    create, streams, jobs = streaming
    session = create()
    session.advance(.8, False)
    wait_for(lambda: streams and len(streams[0].data) == 25600)
    streams[0].partial("Preciso de ajuda", .1, .4)
    assert session.snapshot()["events"][0]["provisional"]
    streams[0].partial("Não preciso de ajuda", .1, .5)
    assert session.snapshot()["events"] == []
    streams[0].partial("Preciso de ajuda", .1, .4)
    assert len(session.snapshot()["events"]) == 1
    streams[0].recognized(final_text, .1, .6)
    state = session.snapshot()
    assert state["events"] == []
    assert state["partial_text"] == ""
    if final_text:
        assert state["transcripts"][0]["text"] == final_text
    else:
        assert state["transcripts"] == []
        assert not jobs


def test_language_failure_does_not_stop_speech_or_clear_an_alert(streaming):
    create, streams, jobs = streaming
    session = create()
    session.advance(.4, False)
    wait_for(lambda: streams and len(streams[0].data) == 12800)
    streams[0].recognized("Socorro.", 0, .3)
    session.snapshot()
    jobs[0].set_exception(azure_service.AzureAudioError("Language indisponível."))
    state = session.snapshot()
    assert state["audio_error"] is None
    assert state["transcripts"][0]["language_error"] == "Language indisponível."
    assert state["events"][0]["kind"] == "Fala: socorro"
    session.advance(.8, False)
    wait_for(lambda: len(streams[0].data) == 25600)
    streams[0].recognized("Me ajuda.", .4, .3)
    assert len(session.snapshot()["transcripts"]) == 2
    assert len(streams) == 1


def test_pause_flushes_only_played_audio_and_resume_offsets_remain_correct(streaming):
    create, streams, _ = streaming
    session = create(4)
    session.advance(4.4, True)
    wait_for(lambda: streams and streams[0].finished)
    assert len(streams[0].data) == 12800
    streams[0].recognized("Socorro.", .1, .2)
    assert session.snapshot()["events"][0]["timestamp"] == 4.1
    assert not session.snapshot()["audio_pending"]
    session.advance(4.4, True)
    time.sleep(.03)
    assert len(streams) == 1
    session.advance(4.8, False)
    wait_for(lambda: len(streams) == 2 and len(streams[1].data) == 12800)
    streams[1].recognized("Me ajuda.", .1, .2)
    state = session.snapshot()
    assert state["transcripts"][1]["start"] == 4.5
    assert state["transcripts"][1]["end"] <= 4.8
    assert sum(len(stream.data) for stream in streams) == 25600


def test_close_discards_late_callbacks_and_pending_language(streaming):
    create, streams, jobs = streaming
    session = create()
    session.advance(.3, False)
    wait_for(lambda: streams and len(streams[0].data) == 9600)
    streams[0].recognized("Socorro.", 0, .2)
    session.snapshot()
    session.close()
    assert jobs[0].cancelled()
    streams[0].recognized("Me ajuda.", .2, .1)
    streams[0].partial("late")
    state = session.snapshot()
    assert len(state["transcripts"]) == 1
    assert not state["audio_pending"]
    assert not state["language_pending"]
    assert not state["partial_text"]
    with pytest.raises(azure_service.AzureAudioError, match="encerrada"):
        session.advance(.4, False)


def test_speech_error_remains_explicit(streaming):
    create, streams, _ = streaming
    session = create()
    session.advance(.2, False)
    wait_for(lambda: streams and len(streams[0].data) == 6400)
    streams[0].failed("Speech indisponível.")
    wait_for(lambda: not session.thread.is_alive())
    state = session.advance(.4, False)
    assert state["audio_error"] == "Speech indisponível."
    assert state["audio_until"] == .2
    assert not state["audio_pending"]
    assert len(streams) == 1


def test_repeated_mentions_in_one_segment_do_not_duplicate_attendance(streaming):
    create, streams, _ = streaming
    session = create()
    session.advance(.8, False)
    wait_for(lambda: streams and len(streams[0].data) == 25600)
    streams[0].partial("Socorro, socorro. Me ajuda, me ajuda.", .1, .6)
    assert len(session.snapshot()["events"]) == 2
    streams[0].recognized("Socorro, socorro. Me ajuda, me ajuda.", .1, .6)
    events = session.snapshot()["events"]
    assert len(events) == 2
    assert all(not event["provisional"] for event in events)


def test_speech_configuration_does_not_require_language(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "test-key")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus")
    for name in (
        "AZURE_LANGUAGE_KEY", "AZURE_LANGUAGE_ENDPOINT",
        "AZURE_TEXT_ANALYTICS_KEY", "AZURE_TEXT_ANALYTICS_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    assert azure_service.configuration(require_language=False)["AZURE_SPEECH_REGION"] == "eastus"
    with pytest.raises(azure_service.AzureAudioError, match="AZURE_LANGUAGE"):
        azure_service.configuration()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
@pytest.mark.parametrize("with_audio", [True, False])
def test_real_ffmpeg_stream_is_bounded_to_playback_and_reports_missing_audio(
    tmp_path, monkeypatch, with_audio,
):
    source = tmp_path / "source.mp4"
    command = [
        "ffmpeg", "-nostdin", "-y", "-f", "lavfi", "-i", "color=size=64x64:rate=25:duration=2",
    ]
    if with_audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    subprocess.run(
        command + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)],
        check=True, capture_output=True, timeout=30,
    )
    chunks = []
    finished = threading.Event()

    class Speech:
        def __init__(self, *args):
            pass

        def start(self):
            pass

        def write(self, data):
            chunks.append(data)

        def finish(self):
            finished.set()

        def stop(self):
            pass

    monkeypatch.setattr(live_audio, "configuration", lambda **kwargs: {})
    monkeypatch.setattr(live_audio, "SpeechStream", Speech)
    session = live_audio.StreamingAudio(source, .4, 2)
    try:
        session.advance(.8, True)
        if with_audio:
            assert finished.wait(5)
            assert sum(map(len, chunks)) == 12800
            assert session.snapshot()["audio_until"] == .8
            assert session.snapshot()["audio_error"] is None
        else:
            wait_for(lambda: session.snapshot()["audio_error"] is not None)
            assert "decodificar" in session.snapshot()["audio_error"]
            assert chunks == []
    finally:
        session.close()
    assert not session.thread.is_alive()
