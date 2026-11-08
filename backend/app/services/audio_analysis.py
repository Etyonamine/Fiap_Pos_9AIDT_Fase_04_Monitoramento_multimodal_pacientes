import array
import math
import re
import sys
import unicodedata
import wave
from pathlib import Path


def acoustic_analysis(path: Path) -> dict:
    energies = []
    square_sum = 0
    sample_count = 0
    clipped = 0
    with wave.open(str(path), "rb") as audio:
        rate = audio.getframerate()
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or rate != 16000:
            raise ValueError("O áudio convertido deve ser WAV PCM mono de 16 bits a 16 kHz.")
        while data := audio.readframes(rate // 10):
            samples = array.array("h", data)
            if sys.byteorder != "little":
                samples.byteswap()
            squares = sum(sample * sample for sample in samples)
            square_sum += squares
            sample_count += len(samples)
            clipped += sum(abs(sample) >= 32760 for sample in samples)
            energies.append(math.sqrt(squares / len(samples)) / 32768)
    if not sample_count:
        raise ValueError("Arquivo sem amostras de áudio decodificáveis.")

    # Fixed energy thresholds describe the recording, not respiratory physiology.
    low_ratio = sum(energy < 0.02 for energy in energies) / len(energies)
    longest = current = 0
    for energy in energies:
        current = current + 1 if energy < 0.02 else 0
        longest = max(longest, current)
    indicators = []
    if low_ratio >= 0.4:
        indicators.append("Muitas janelas de baixa energia: revisar pausas, volume e ruído.")
    if longest >= 20:
        indicators.append("Trecho de baixa energia de pelo menos 2 s: revisar pausa na gravação.")
    if clipped / sample_count >= 0.01:
        indicators.append("Possível saturação do microfone; pode prejudicar a transcrição.")
    energy_change_db = None
    if len(energies) >= 300:
        third = len(energies) // 3
        first_active = [energy for energy in energies[:third] if energy >= 0.02]
        last_active = [energy for energy in energies[-third:] if energy >= 0.02]
        if len(first_active) >= 10 and len(last_active) >= 10:
            first_rms = math.sqrt(sum(energy ** 2 for energy in first_active) / len(first_active))
            last_rms = math.sqrt(sum(energy ** 2 for energy in last_active) / len(last_active))
            energy_change_db = 20 * math.log10(last_rms / first_rms)
            if energy_change_db <= -6:
                indicators.append("Redução de intensidade de pelo menos 6 dB entre o início e o fim: "
                                  "revisar possível mudança vocal ou condições de captação.")
    bars = []
    for index in range(min(80, len(energies))):
        start = index * len(energies) // min(80, len(energies))
        end = (index + 1) * len(energies) // min(80, len(energies))
        bars.append(round(max(energies[start:end]), 5))
    return {
        "duration": round(sample_count / rate, 3),
        "rms_energy": round(math.sqrt(square_sum / sample_count) / 32768, 5),
        "low_energy_ratio": round(low_ratio, 4),
        "longest_low_energy_seconds": round(longest * 0.1, 1),
        "clipping_ratio": round(clipped / sample_count, 4),
        "energy_change_db": round(energy_change_db, 2) if energy_change_db is not None else None,
        "waveform": bars,
        "indicators": indicators,
        "limitation": "Heurísticas acústicas não validadas clinicamente. Pausas e baixa energia "
                      "podem decorrer de silêncio, ruído ou microfone; não detectam nem "
                      "diagnosticam fadiga ou dificuldade respiratória.",
    }


def critical_terms(text: str) -> list[dict]:
    normalized = "".join(
        char for char in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(char) != "Mn"
    )
    rules = {
        "critical": ("dor no peito", "falta de ar", "dispneia", "não consigo respirar",
                     "dificuldade para respirar", "dificuldade respiratória", "sufocamento",
                     "desmaio", "perda de consciência", "convulsão"),
        "warning": ("cansaço", "fadiga", "fraqueza", "tontura", "palpitação", "palpitações"),
    }
    mentions = []
    for severity, terms in rules.items():
        for term in terms:
            literal = "".join(
                char for char in unicodedata.normalize("NFD", term)
                if unicodedata.category(char) != "Mn"
            )
            for match in re.finditer(r"\b" + re.escape(literal) + r"\b", normalized):
                # Limit negation to the current clause; "não consigo respirar" is itself an alert.
                prefix = re.split(r"[.!?;,\n]|\b(?:mas|porem|contudo)\b",
                                  normalized[:match.start()])[-1]
                prefix = prefix.replace("nao consigo respirar", "dificuldade respiratoria")
                negated = bool(re.search(
                    r"\b(?:nao|sem|nego|nega|negou|ausencia de)\b(?:\s+\w+){0,5}\s*$",
                    prefix,
                ))
                suffix = normalized[match.end():match.end() + 45]
                negated = negated or bool(re.match(
                    r"\s+(?:ausente|ausentes|negada|negado)\b", suffix
                ))
                mentions.append({
                    "term": term, "severity": severity,
                    "negated": negated, "offset": match.start(),
                    "context": text[max(0, match.start() - 60):match.end() + 60],
                })
    return sorted(mentions, key=lambda mention: mention["offset"])
