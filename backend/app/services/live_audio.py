import copy
import logging
import math
import subprocess
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from app.services.audio_analysis import critical_terms
from app.services.azure_service import AzureAudioError, analyze_language, configuration

logger = logging.getLogger(__name__)
language_executor = ThreadPoolExecutor(max_workers=2)
SAMPLE_RATE = 16000


def inspect_language(text: str):
    return analyze_language(text, configuration())


def speech_events(text: str, timestamp: float, provisional: bool):
    events = {}
    for mention in critical_terms(text):
        if mention["negated"] or (provisional and mention["severity"] != "critical"):
            continue
        events[mention["term"]] = {
            "timestamp": timestamp, "kind": f"Fala: {mention['term']}",
            "severity": mention["severity"], "source": "audio", "provisional": provisional,
        }
    return list(events.values())


class SpeechStream:
    def __init__(self, config: dict, recognized: Callable, partial: Callable, failed: Callable):
        try:
            import azure.cognitiveservices.speech as speechsdk
        except ImportError as error:
            raise AzureAudioError("SDK Azure Speech não instalado no Python do backend.") from error
        speech_config = speechsdk.SpeechConfig(
            subscription=config["AZURE_SPEECH_KEY"], region=config["AZURE_SPEECH_REGION"],
        )
        speech_config.speech_recognition_language = "pt-BR"
        speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "300")
        self.input = speechsdk.audio.PushAudioInputStream(
            stream_format=speechsdk.audio.AudioStreamFormat(
                samples_per_second=SAMPLE_RATE, bits_per_sample=16, channels=1,
            ),
        )
        self.recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config, audio_config=speechsdk.audio.AudioConfig(stream=self.input),
        )
        self.stopped = threading.Event()

        def on_recognized(event):
            if event.result.reason in (
                speechsdk.ResultReason.RecognizedSpeech, speechsdk.ResultReason.NoMatch,
            ):
                recognized(
                    event.result.text or "", event.result.offset / 10_000_000,
                    event.result.duration / 10_000_000,
                )

        def on_canceled(event):
            if event.result.cancellation_details.reason == speechsdk.CancellationReason.Error:
                failed("Azure Speech interrompeu o streaming. Verifique região, chave, quota e rede.")
            self.stopped.set()

        self.recognizer.recognized.connect(on_recognized)
        self.recognizer.recognizing.connect(lambda event: partial(
            event.result.text, event.result.offset / 10_000_000, event.result.duration / 10_000_000,
        ))
        self.recognizer.canceled.connect(on_canceled)
        self.recognizer.session_stopped.connect(lambda event: self.stopped.set())

    def start(self):
        self.recognizer.start_continuous_recognition_async().get()

    def write(self, data: bytes):
        self.input.write(data)

    def finish(self):
        self.input.close()
        try:
            if not self.stopped.wait(10):
                raise AzureAudioError("Tempo limite ao finalizar o trecho de Speech reproduzido.")
        finally:
            self.recognizer.stop_continuous_recognition_async().get()

    def stop(self):
        self.input.close()
        self.recognizer.stop_continuous_recognition_async().get()


class StreamingAudio:
    """Keep one Speech connection per uninterrupted playback, independent of YOLO."""

    def __init__(self, source: Path, start: float, duration: float):
        self.source = source
        self.start = start
        self.duration = duration
        self.condition = threading.Condition()
        self.closed = False
        self.target = start
        self.sent_samples = 0
        self.flush = False
        self.active = False
        self.error: str | None = None
        self.partial = ""
        self.provisional_events: list[dict] = []
        self.transcripts: list[dict] = []
        self.events: list[dict] = []
        self.thread: threading.Thread | None = None
        self.decoder: subprocess.Popen | None = None
        self.language_future: Future | None = None
        self.language_index = 0
        self.config: dict | None = None

    @property
    def sent_until(self):
        return min(self.duration, self.start + self.sent_samples / SAMPLE_RATE)

    @property
    def pending_samples(self):
        return max(0, math.floor((self.target - self.start) * SAMPLE_RATE + 1e-6) - self.sent_samples)

    def fail(self, message: str):
        logger.warning("Falha no streaming de áudio: %s", message)
        with self.condition:
            if not self.closed:
                self.error = message
                self.partial = ""
                self.provisional_events = []
                self.condition.notify_all()

    def recognized(self, base: float, text: str, offset: float, duration: float):
        with self.condition:
            if self.closed or self.error:
                return
            self.partial = ""
            self.provisional_events = []
            if not text.strip():
                return
            if not all(math.isfinite(value) and value >= 0 for value in (offset, duration)):
                self.fail("Azure Speech retornou tempos inválidos.")
                return
            start = min(self.sent_until, base + offset)
            end = min(self.sent_until, start + duration)
            self.transcripts.append({
                "start": start, "end": end, "text": text,
                "language": None, "language_pending": True, "language_error": None,
            })
            known = {(event["timestamp"], event["kind"]) for event in self.events}
            self.events.extend(
                event for event in speech_events(text, start, False)
                if (event["timestamp"], event["kind"]) not in known
            )

    def recognizing(self, base: float, text: str, offset: float, duration: float):
        with self.condition:
            if not self.closed and not self.error:
                if not all(math.isfinite(value) and value >= 0 for value in (offset, duration)):
                    self.fail("Azure Speech retornou tempos provisórios inválidos.")
                    return
                self.partial = text
                self.provisional_events = speech_events(text, min(self.sent_until, base + offset), True)

    def collect_language(self):
        if self.language_future is not None and self.language_future.done():
            segment = self.transcripts[self.language_index]
            try:
                segment["language"] = self.language_future.result()
            except Exception as error:
                logger.exception("Falha na análise Language do streaming")
                segment["language_error"] = (
                    str(error) if isinstance(error, AzureAudioError)
                    else "Falha na análise de linguagem. Consulte o log do servidor."
                )
            segment["language_pending"] = False
            self.language_future = None
            self.language_index += 1
        if not self.closed and self.language_future is None and self.language_index < len(self.transcripts):
            self.language_future = language_executor.submit(
                inspect_language, self.transcripts[self.language_index]["text"],
            )

    def snapshot(self):
        with self.condition:
            self.collect_language()
            return {
                "audio_until": self.sent_until,
                "audio_pending": not self.closed and not self.error and (
                    self.active or self.pending_samples > 0
                ),
                "audio_error": self.error, "partial_text": self.partial,
                "language_pending": any(segment["language_pending"] for segment in self.transcripts),
                "transcripts": copy.deepcopy(self.transcripts),
                "events": copy.deepcopy(self.events + self.provisional_events),
            }

    def advance(self, timestamp: float, flush: bool):
        with self.condition:
            if self.closed:
                raise AzureAudioError("Sessão de áudio encerrada.")
            if timestamp + 1e-6 < self.target or timestamp > self.duration:
                raise AzureAudioError("Posição inválida para streaming de áudio.")
            self.target = timestamp
            self.flush = flush
            if self.thread is None and timestamp > self.start and not self.error:
                self.thread = threading.Thread(target=self.run, name="bed-speech", daemon=True)
                self.thread.start()
            self.condition.notify_all()
        return self.snapshot()

    def open_decoder(self):
        return subprocess.Popen(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(self.source),
             "-ss", str(self.start), "-t", str(self.duration - self.start),
             "-map", "0:a:0", "-vn", "-af", "aresample=async=1:first_pts=0,apad",
             "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )

    def run(self):
        stream = None
        decoder = None
        try:
            self.config = configuration(require_language=False)
            with self.condition:
                if self.closed:
                    return
                decoder = self.open_decoder()
                self.decoder = decoder
            if decoder.stdout is None:
                raise AzureAudioError("FFmpeg não disponibilizou a faixa sonora.")
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.closed or self.error or (
                        self.pending_samples > 0
                    ) or (self.flush and self.active))
                    if self.closed or self.error:
                        break
                    samples = min(1600, self.pending_samples)
                    if stream is None and samples:
                        base = self.sent_until
                        self.active = True
                    else:
                        base = None
                if base is not None:
                    stream = SpeechStream(
                        self.config,
                        lambda text, offset, duration, origin=base: self.recognized(
                            origin, text, offset, duration,
                        ),
                        lambda text, offset=0, duration=0, origin=base: self.recognizing(
                            origin, text, offset, duration,
                        ),
                        self.fail,
                    )
                    stream.start()
                if samples:
                    data = decoder.stdout.read(samples * 2)
                    if len(data) != samples * 2:
                        raise AzureAudioError("Não foi possível decodificar a faixa sonora reproduzida.")
                    with self.condition:
                        if self.closed or self.error:
                            break
                        self.sent_samples += samples
                    if stream is None:
                        raise AzureAudioError("Speech não iniciou o fluxo de reconhecimento.")
                    stream.write(data)
                with self.condition:
                    finish = self.flush and self.pending_samples == 0
                if finish and stream is not None:
                    stream.finish()
                    stream = None
                    with self.condition:
                        self.active = False
                        self.partial = ""
                        self.provisional_events = []
        except Exception as error:
            logger.exception("Falha no worker de Speech contínuo")
            self.fail(
                str(error) if isinstance(error, AzureAudioError)
                else "Falha no streaming de áudio. Consulte o log do servidor.",
            )
        finally:
            if stream is not None:
                try:
                    stream.stop()
                except RuntimeError:
                    logger.exception("Falha ao encerrar Azure Speech")
            with self.condition:
                self.active = False
            if decoder is not None:
                if decoder.poll() is None:
                    decoder.terminate()
                decoder.wait(timeout=10)
                if decoder.stdout is not None:
                    decoder.stdout.close()

    def close(self):
        with self.condition:
            self.closed = True
            self.collect_language()
            self.partial = ""
            self.provisional_events = []
            if self.language_future is not None:
                self.language_future.cancel()
                self.language_future = None
            for segment in self.transcripts:
                if segment["language_pending"]:
                    segment["language_pending"] = False
                    segment["language_error"] = "Sessão encerrada; análise de linguagem descartada."
            if self.active or self.pending_samples > 0:
                self.error = self.error or "Sessão encerrada; reconhecimento pendente descartado."
            self.condition.notify_all()
            if self.decoder is not None and self.decoder.poll() is None:
                self.decoder.terminate()
        if self.thread is not None:
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                logger.error("Worker de Speech ainda encerrando após o limite de espera.")
