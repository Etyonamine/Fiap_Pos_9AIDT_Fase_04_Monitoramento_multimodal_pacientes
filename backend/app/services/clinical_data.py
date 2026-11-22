import csv
import io
import json
import math
import re
import unicodedata
from datetime import datetime, timezone

MAX_RECORDS = 10_000
PATIENT_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
VITAL_FIELDS = {
    "heart_rate_bpm": (20, 250, "Frequência cardíaca"),
    "systolic_mmhg": (40, 300, "Pressão sistólica"),
    "diastolic_mmhg": (20, 200, "Pressão diastólica"),
    "spo2_percent": (50, 100, "SpO₂"),
}
VITAL_LIMITS = {
    "heart_rate_bpm": {"low": 50, "high": 120, "unit": "bpm"},
    "systolic_mmhg": {"low": 90, "high": 180, "unit": "mmHg"},
    "diastolic_mmhg": {"low": 60, "high": 120, "unit": "mmHg"},
    "spo2_percent": {"low": 90, "high": 100, "unit": "%"},
}
RAPID_CHANGE_LIMITS = {
    "heart_rate_bpm": 30,
    "systolic_mmhg": 30,
    "diastolic_mmhg": 20,
    "spo2_percent": 4,
}


class ClinicalDataError(ValueError):
    pass


def parse_records(content: bytes, filename: str) -> list[dict]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ClinicalDataError("Use CSV ou JSON codificado em UTF-8.") from error
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if suffix == "csv":
            reader = csv.DictReader(io.StringIO(text))
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ClinicalDataError("O CSV deve ter cabeçalho único e legível.")
            records = list(reader)
        elif suffix == "json":
            payload = json.loads(text)
            records = payload.get("records") if isinstance(payload, dict) else payload
        else:
            raise ClinicalDataError("Envie um arquivo CSV ou JSON.")
    except (csv.Error, json.JSONDecodeError) as error:
        raise ClinicalDataError("Não foi possível interpretar o arquivo CSV/JSON.") from error
    if not isinstance(records, list) or not records:
        raise ClinicalDataError("O arquivo deve conter pelo menos um registro.")
    if len(records) > MAX_RECORDS:
        raise ClinicalDataError(f"O limite por arquivo é {MAX_RECORDS} registros.")
    if any(not isinstance(record, dict) for record in records):
        raise ClinicalDataError("Cada registro deve ser um objeto com os campos documentados.")
    return records


def timestamp(value, row_number: int, *, preserve_fraction: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClinicalDataError(f"Registro {row_number}: recorded_at é obrigatório.")
    fraction = re.search(r"[Tt]\d{2}:\d{2}:\d{2}[.,](\d+)", value)
    if preserve_fraction and fraction and len(fraction.group(1)) > 6:
        raise ClinicalDataError(f"Registro {row_number}: use no máximo seis casas decimais de segundo.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ClinicalDataError(
            f"Registro {row_number}: recorded_at deve ser uma data ISO 8601."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ClinicalDataError(
            f"Registro {row_number}: recorded_at precisa incluir fuso horário."
        )
    precision = "microseconds" if preserve_fraction else "seconds"
    return parsed.astimezone(timezone.utc).isoformat(timespec=precision).replace("+00:00", "Z")


def patient_ref(value, row_number: int) -> str:
    if not isinstance(value, str) or not PATIENT_ID.fullmatch(value.strip()):
        raise ClinicalDataError(
            f"Registro {row_number}: patient_id deve ser um pseudônimo de até 80 caracteres "
            "alfanuméricos, ponto, hífen ou sublinhado."
        )
    normalized = unicodedata.normalize("NFKC", value.strip()).casefold()
    return normalized


def finite_number(value, row_number: int, field: str, bounds: tuple[float, float]) -> float:
    if isinstance(value, bool):
        raise ClinicalDataError(f"Registro {row_number}: {field} deve ser numérico.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ClinicalDataError(f"Registro {row_number}: {field} deve ser numérico.") from error
    if not math.isfinite(number) or not bounds[0] <= number <= bounds[1]:
        raise ClinicalDataError(
            f"Registro {row_number}: {field} deve estar entre {bounds[0]} e {bounds[1]}."
        )
    return number


def analyze_vitals(
    records: list[dict], pseudonyms: dict[str, str], *, allow_partial: bool = False,
) -> dict:
    normalized = []
    seen = set()
    for row_number, record in enumerate(records, 1):
        patient = patient_ref(record.get("patient_id"), row_number)
        recorded_at = timestamp(record.get("recorded_at"), row_number, preserve_fraction=allow_partial)
        key = (patient, recorded_at)
        if key in seen:
            raise ClinicalDataError(
                f"Registro {row_number}: patient_id e recorded_at precisam ser únicos."
            )
        seen.add(key)
        row = {
            "patient_ref": pseudonyms.setdefault(patient, f"caso-{len(pseudonyms) + 1:03d}"),
            "recorded_at": recorded_at,
        }
        for field, (low, high, label) in VITAL_FIELDS.items():
            if allow_partial and record.get(field) in (None, ""):
                continue
            row[field] = finite_number(record.get(field), row_number, label, (low, high))
        if not any(field in row for field in VITAL_FIELDS):
            raise ClinicalDataError(f"Registro {row_number}: informe ao menos um sinal vital.")
        if (
            "systolic_mmhg" in row and "diastolic_mmhg" in row
            and row["systolic_mmhg"] <= row["diastolic_mmhg"]
        ):
            raise ClinicalDataError(
                f"Registro {row_number}: pressão sistólica deve superar a diastólica."
            )
        normalized.append((patient, row))
    normalized.sort(key=lambda item: (item[0], item[1]["recorded_at"]))

    events = []
    previous_flags: dict[str, set[str]] = {}
    previous_values: dict[str, dict[str, tuple[float, str]]] = {}
    for patient, row in normalized:
        prior_flags = previous_flags.get(patient, set())
        current_flags = prior_flags.copy()
        for field, limits in VITAL_LIMITS.items():
            if field not in row:
                continue
            current_flags.discard(f"{field}:low")
            current_flags.discard(f"{field}:high")
            value = row[field]
            if value < limits["low"]:
                flag = f"{field}:low"
                current_flags.add(flag)
                label = VITAL_FIELDS[field][2]
                message = (
                    f"{label} abaixo do limite demonstrativo de {limits['low']} {limits['unit']} "
                    f"(medição: {value:g} {limits['unit']})."
                )
            elif value > limits["high"]:
                flag = f"{field}:high"
                current_flags.add(flag)
                label = VITAL_FIELDS[field][2]
                message = (
                    f"{label} acima do limite demonstrativo de {limits['high']} {limits['unit']} "
                    f"(medição: {value:g} {limits['unit']})."
                )
            else:
                message = None
                flag = None
            if message and flag not in prior_flags:
                events.append({
                    "recorded_at": row["recorded_at"], "patient_ref": row["patient_ref"],
                    "kind": "threshold_crossing", "field": field,
                    "message": message, "priority": "review",
                })

        prior_values = previous_values.setdefault(patient, {})
        for field, limit in RAPID_CHANGE_LIMITS.items():
            if field not in row:
                continue
            prior = prior_values.get(field)
            if prior:
                previous_value, previous_time = prior
                gap = (
                    datetime.fromisoformat(row["recorded_at"].replace("Z", "+00:00"))
                    - datetime.fromisoformat(previous_time.replace("Z", "+00:00"))
                ).total_seconds() / 60
                difference = row[field] - previous_value
                if (
                    0 < gap <= 30 and abs(difference) >= limit
                    and (field != "spo2_percent" or difference <= -limit)
                ):
                    events.append({
                        "recorded_at": row["recorded_at"], "patient_ref": row["patient_ref"],
                        "kind": "rapid_change", "field": field,
                        "message": (
                            f"Variação de {difference:+g} em {field} em {gap:g} min; "
                            "revisar a série e a qualidade da medição."
                        ),
                        "priority": "review",
                    })
            prior_values[field] = (row[field], row["recorded_at"])
        previous_flags[patient] = current_flags

    points = [row for _, row in normalized]
    return {
        "kind": "vitals", "record_count": len(points),
        "patient_count": len(pseudonyms), "points": points,
        "events": sorted(events, key=lambda event: (event["recorded_at"], event["patient_ref"])),
        "rules": {
            "vital_limits": VITAL_LIMITS,
            "rapid_change_within_minutes": 30,
            "rapid_change_absolute_limits": RAPID_CHANGE_LIMITS,
            "notice": (
                "Limites iniciais demonstrativos, sem ajuste por idade, condição ou linha de base. "
                "Não representam diagnóstico nem substituem avaliação profissional."
            ),
        },
    }


PRESCRIPTION_FIELDS = ("dose", "unit", "status", "route", "frequency")


def expected_regimen(value, row_number: int) -> dict | None:
    if value is None:
        return None
    required = {"dose", "unit", "status"}
    if not isinstance(value, dict) or not required.issubset(value) or (
        set(value) - set(PRESCRIPTION_FIELDS)
    ):
        raise ClinicalDataError(
            f"Registro {row_number}: expected_regimen deve conter dose, unit e status; "
            "route e frequency são opcionais."
        )
    unit = value["unit"]
    if not isinstance(unit, str) or not re.fullmatch(r"[A-Za-z%µμ.]{1,16}", unit.strip()):
        raise ClinicalDataError(f"Registro {row_number}: unidade da referência inválida.")
    if value["status"] not in ("active", "discontinued"):
        raise ClinicalDataError(f"Registro {row_number}: status da referência inválido.")
    result = {
        "dose": finite_number(value["dose"], row_number, "expected_regimen.dose", (0.001, 100_000)),
        "unit": unit.strip(),
        "status": value["status"],
    }
    for field, limit in (("route", 40), ("frequency", 80)):
        if field in value:
            if (
                not isinstance(value[field], str)
                or not value[field].strip() or len(value[field]) > limit
            ):
                raise ClinicalDataError(f"Registro {row_number}: {field} da referência inválido.")
            result[field] = value[field].strip()
    return result


def compare_expected_regimen(current: dict, expected: dict | None) -> dict:
    if expected is None:
        return {
            "status": "not_provided", "compared_fields": [],
            "different_fields": [], "missing_fields": [],
        }
    fields = [field for field in PRESCRIPTION_FIELDS if field in expected]
    different = []
    missing = []
    for field in fields:
        actual = current.get(field, "")
        if field in ("unit", "route", "frequency"):
            actual = actual.strip()
        if field in ("route", "frequency") and not actual:
            missing.append(field)
        elif actual != expected[field]:
            different.append(field)
    return {
        "status": "differs" if different else "incomplete" if missing else "matches",
        "compared_fields": fields,
        "different_fields": different,
        "missing_fields": missing,
    }


def analyze_prescriptions(
    records: list[dict], pseudonyms: dict[str, str], *, preserve_fraction: bool = False,
) -> dict:
    normalized = []
    seen = set()
    for row_number, record in enumerate(records, 1):
        patient = patient_ref(record.get("patient_id"), row_number)
        recorded_at = timestamp(
            record.get("recorded_at"), row_number, preserve_fraction=preserve_fraction,
        )
        medication = record.get("medication")
        unit = record.get("unit")
        status = record.get("status", "active")
        if not isinstance(medication, str) or not medication.strip() or len(medication) > 120:
            raise ClinicalDataError(f"Registro {row_number}: medication é obrigatório (até 120 caracteres).")
        if not isinstance(unit, str) or not re.fullmatch(r"[A-Za-z%µμ.]{1,16}", unit.strip()):
            raise ClinicalDataError(f"Registro {row_number}: informe uma unidade de dose válida.")
        if status not in ("active", "discontinued"):
            raise ClinicalDataError(
                f"Registro {row_number}: status deve ser active ou discontinued."
            )
        dose = finite_number(record.get("dose"), row_number, "dose", (0.001, 100_000))
        key = (patient, unicodedata.normalize("NFKC", medication).casefold(), recorded_at)
        if key in seen:
            raise ClinicalDataError(
                f"Registro {row_number}: medication e recorded_at precisam ser únicos por pseudônimo."
            )
        seen.add(key)
        reference = expected_regimen(record.get("expected_regimen"), row_number)
        route = record.get("route")
        frequency = record.get("frequency")
        row = {
            "patient_ref": pseudonyms.setdefault(patient, f"caso-{len(pseudonyms) + 1:03d}"),
            "recorded_at": recorded_at, "medication": medication.strip(),
            "dose": dose, "unit": unit.strip(), "status": status,
            "route": "" if route is None else str(route).strip()[:40],
            "frequency": "" if frequency is None else str(frequency).strip()[:80],
            "expected_regimen": reference,
        }
        row["plan_comparison"] = compare_expected_regimen(row, reference)
        normalized.append((patient, key[1], row))
    normalized.sort(key=lambda item: (item[0], item[1], item[2]["recorded_at"]))

    events = []
    previous: dict[tuple[str, str], dict] = {}
    for patient, medication_key, row in normalized:
        key = (patient, medication_key)
        prior = previous.get(key)
        kind = None
        if prior is None and row["status"] == "active":
            kind = "started"
        elif prior:
            if prior["status"] == "active" and row["status"] == "discontinued":
                kind = "discontinued"
            elif prior["status"] == "discontinued" and row["status"] == "active":
                kind = "restarted"
            elif row["status"] == "active" and (
                row["dose"] != prior["dose"] or row["unit"] != prior["unit"]
                or row["route"] != prior["route"] or row["frequency"] != prior["frequency"]
            ):
                kind = "regimen_changed"
        comparison = row["plan_comparison"]
        if comparison["status"] == "differs":
            unchanged_difference = (
                prior is not None
                and prior["plan_comparison"]["status"] == "differs"
                and prior["expected_regimen"] == row["expected_regimen"]
                and all(prior[field] == row[field] for field in PRESCRIPTION_FIELDS)
            )
            kind = None if unchanged_difference else "unexpected_regimen"
        elif comparison["status"] == "matches" and kind in (
            "regimen_changed", "discontinued", "restarted",
        ):
            kind = "expected_regimen_change"
        if kind:
            if kind == "unexpected_regimen":
                message = (
                    f"{row['medication']}: divergência da referência fornecida nos campos "
                    f"{', '.join(comparison['different_fields'])}; revisar."
                )
            elif kind == "expected_regimen_change":
                message = (
                    f"{row['medication']}: alteração compatível com os campos da referência "
                    "fornecida; manter revisão humana."
                )
            else:
                message = (
                    f"{row['medication']}: {kind.replace('_', ' ')}; "
                    "comparar com a ordem autorizada."
                )
            events.append({
                "recorded_at": row["recorded_at"], "patient_ref": row["patient_ref"],
                "kind": kind, "medication": row["medication"],
                "message": message,
                "previous": (
                    {field: prior[field] for field in ("dose", "unit", "route", "frequency", "status")}
                    if prior else None
                ),
                "current": {
                    field: row[field] for field in ("dose", "unit", "route", "frequency", "status")
                },
                "plan_comparison": comparison,
                "priority": "information" if kind == "expected_regimen_change" else "review",
            })
        previous[key] = row

    return {
        "kind": "prescriptions", "record_count": len(normalized),
        "patient_count": len(pseudonyms),
        "records": [row for _, _, row in normalized],
        "events": events,
        "notice": (
            "A referência é fornecida pela origem e comparada somente nos campos informados; "
            "campos observados ausentes não são considerados compatíveis. Sem referência não "
            "há avaliação do esperado. A aplicação não valida prescrição, "
            "autoria da referência, interações, dose segura, indicação ou decisão médica."
        ),
    }


def note_events(text: str, patient: str, recorded_at: str, mentions: list[dict]) -> list[dict]:
    return [
        {
            "recorded_at": recorded_at, "patient_ref": patient,
            "kind": "text_mention", "field": mention["term"],
            "message": f"Menção textual para revisão: {mention['term']}.",
            "priority": "review",
        }
        for mention in mentions
        if not mention["negated"]
    ]
