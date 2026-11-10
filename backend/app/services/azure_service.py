import json
import math
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

import httpx


class AzureAudioError(RuntimeError):
    pass


def configuration(*, require_language: bool = True) -> dict:
    values = {
        "AZURE_SPEECH_KEY": os.getenv("AZURE_SPEECH_KEY", "").strip(),
        "AZURE_SPEECH_REGION": os.getenv("AZURE_SPEECH_REGION", "").strip(),
        "AZURE_LANGUAGE_KEY": (
            os.getenv("AZURE_LANGUAGE_KEY") or os.getenv("AZURE_TEXT_ANALYTICS_KEY", "")
        ).strip(),
        "AZURE_LANGUAGE_ENDPOINT": (
            os.getenv("AZURE_LANGUAGE_ENDPOINT") or os.getenv("AZURE_TEXT_ANALYTICS_ENDPOINT", "")
        ).strip().rstrip("/"),
    }
    required = values if require_language else {
        name: value for name, value in values.items() if name.startswith("AZURE_SPEECH_")
    }
    missing = [name for name, value in required.items() if not value or any(
        marker in value.lower() for marker in ("sua_chave", "seu-recurso", "seu-servico", "<", ">")
    )]
    if missing:
        raise AzureAudioError("Configure no backend: " + ", ".join(missing) + ".")
    if not re.fullmatch(r"[a-z0-9-]+", values["AZURE_SPEECH_REGION"]):
        raise AzureAudioError("AZURE_SPEECH_REGION deve ser a região do recurso, como eastus.")
    endpoint = urlparse(values["AZURE_LANGUAGE_ENDPOINT"])
    if require_language and (
        endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.query
    ):
        raise AzureAudioError("AZURE_LANGUAGE_ENDPOINT deve ser o endpoint HTTPS do recurso Language.")
    return values


def transcribe(path: Path, duration: float, config: dict, *, allow_empty: bool = False) -> dict:
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as error:
        raise AzureAudioError(
            "SDK Azure Speech não instalado no ambiente Python do backend. "
            "Execute `python -m pip install -r requirements.txt` na pasta backend "
            "e reinicie o servidor."
        ) from error

    speech_config = speechsdk.SpeechConfig(
        subscription=config["AZURE_SPEECH_KEY"], region=config["AZURE_SPEECH_REGION"]
    )
    speech_config.speech_recognition_language = "pt-BR"
    speech_config.output_format = speechsdk.OutputFormat.Detailed
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=speechsdk.audio.AudioConfig(filename=str(path)),
    )
    segments = []
    failures = []
    done = threading.Event()

    def recognized(event):
        if event.result.reason != speechsdk.ResultReason.RecognizedSpeech:
            return
        try:
            payload = json.loads(event.result.json)
            alternatives = payload.get("NBest", [])
            confidence = alternatives[0].get("Confidence") if alternatives else None
            if confidence is not None and (
                not isinstance(confidence, (int, float)) or not math.isfinite(confidence)
                or not 0 <= confidence <= 1
            ):
                raise ValueError("Invalid confidence")
            segments.append({
                "text": event.result.text,
                "offset": event.result.offset / 10_000_000,
                "duration": event.result.duration / 10_000_000,
                "confidence": confidence,
            })
        except (ValueError, TypeError, KeyError, AttributeError):
            failures.append("Azure Speech retornou metadados inválidos.")
            done.set()

    def canceled(event):
        if event.result.cancellation_details.reason == speechsdk.CancellationReason.Error:
            failures.append("Azure Speech interrompeu a transcrição. Confira chave, região, "
                            "quota e conectividade do recurso Speech.")
        done.set()

    recognizer.recognized.connect(recognized)
    recognizer.canceled.connect(canceled)
    recognizer.session_stopped.connect(lambda event: done.set())
    try:
        recognizer.start_continuous_recognition_async().get()
        if not done.wait(timeout=duration + 120):
            raise AzureAudioError("Tempo limite da transcrição Azure Speech excedido.")
    except AzureAudioError:
        raise
    except RuntimeError as error:
        raise AzureAudioError("Não foi possível iniciar Azure Speech. Confira o recurso "
                              "e a instalação do SDK no servidor.") from error
    finally:
        recognizer.stop_continuous_recognition_async().get()
    if failures:
        raise AzureAudioError(failures[0])
    segments.sort(key=lambda segment: segment["offset"])
    if not segments and not allow_empty:
        raise AzureAudioError("Azure Speech não reconheceu fala. Verifique volume, idioma e gravação.")
    return {
        "provider": "Azure Speech to Text", "language": "pt-BR",
        "text": " ".join(segment["text"] for segment in segments), "segments": segments,
    }


def text_chunks(text: str) -> list[str]:
    chunks = []
    while text:
        end = min(4500, len(text))
        if end < len(text):
            boundary = text.rfind(" ", 0, end)
            if boundary > 0:
                end = boundary
        chunks.append(text[:end])
        text = text[end:].lstrip()
    return chunks


def analyze_language(text: str, config: dict) -> dict:
    if not text.strip():
        raise AzureAudioError("A transcrição está vazia; não é possível analisar linguagem.")
    chunks = text_chunks(text)
    sentiments = []
    phrases = []
    base = config["AZURE_LANGUAGE_ENDPOINT"] + "/text/analytics/v3.1"
    try:
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            for start in range(0, len(chunks), 10):
                batch = chunks[start:start + 10]
                documents = [{"id": str(start + index), "language": "pt", "text": chunk}
                             for index, chunk in enumerate(batch)]
                for task in ("sentiment", "keyPhrases"):
                    response = client.post(
                        f"{base}/{task}",
                        headers={"Ocp-Apim-Subscription-Key": config["AZURE_LANGUAGE_KEY"]},
                        json={"documents": documents},
                    )
                    if response.status_code in (401, 403):
                        raise AzureAudioError("Azure Text Analytics recusou a autenticação. "
                                              "Use chave e endpoint do mesmo recurso Language.")
                    if response.status_code == 429:
                        raise AzureAudioError("Quota do Azure Text Analytics excedida. Tente mais tarde.")
                    response.raise_for_status()
                    payload = response.json()
                    results = payload.get("documents", [])
                    if payload.get("errors") or len(results) != len(batch):
                        raise AzureAudioError("Azure Text Analytics não analisou todos os trechos.")
                    by_id = {document["id"]: document for document in results}
                    for document in documents:
                        result = by_id[document["id"]]
                        if task == "sentiment":
                            scores = result["confidenceScores"]
                            if result["sentiment"] not in ("positive", "neutral", "negative", "mixed"):
                                raise ValueError("Invalid sentiment")
                            if any(not isinstance(scores[label], (int, float))
                                   or not math.isfinite(scores[label]) or not 0 <= scores[label] <= 1
                                   for label in ("positive", "neutral", "negative")):
                                raise ValueError("Invalid scores")
                            sentiments.append({
                                "text": document["text"], "label": result["sentiment"],
                                "scores": scores,
                            })
                        else:
                            extracted = result["keyPhrases"]
                            if not isinstance(extracted, list) or any(
                                not isinstance(phrase, str) for phrase in extracted
                            ):
                                raise ValueError("Invalid key phrases")
                            phrases.extend(extracted)
    except httpx.HTTPStatusError as error:
        raise AzureAudioError(f"Azure Text Analytics falhou (HTTP {error.response.status_code}).") from error
    except httpx.RequestError as error:
        raise AzureAudioError("Falha de conexão ou tempo limite do Azure Text Analytics.") from error
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise AzureAudioError("Resposta inválida do Azure Text Analytics.") from error
    total = sum(len(item["text"]) for item in sentiments)
    scores = {
        label: round(sum(item["scores"][label] * len(item["text"]) for item in sentiments) / total, 4)
        for label in ("positive", "neutral", "negative")
    }
    labels = {item["label"] for item in sentiments}
    label = next(iter(labels)) if len(labels) == 1 else "mixed"
    return {
        "provider": "Azure Text Analytics", "key_phrases": list(dict.fromkeys(phrases)),
        "sentiment": {"label": label, "scores": scores, "chunks": sentiments,
                      "aggregation": "Média dos scores ponderada pelo tamanho dos trechos; "
                                     "rótulos diferentes são apresentados como misto."},
    }