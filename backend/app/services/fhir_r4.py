import ipaddress
import json
import math
import os
import posixpath
import re
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from app.services.clinical_data import ClinicalDataError, analyze_vitals, timestamp
from app.services.private_http import private_http

FHIR_ID = re.compile(r"^[A-Za-z0-9.-]{1,64}$")
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
VITAL_CODES = {
    "8867-4": ("heart_rate_bpm", "/min"),
    "8480-6": ("systolic_mmhg", "mm[Hg]"),
    "8462-4": ("diastolic_mmhg", "mm[Hg]"),
    "59408-5": ("spo2_percent", "%"),
}
MAX_PAGES = 30
MAX_RESOURCES = 10_000
MAX_PAGE_BYTES = 5 * 1024 * 1024


class FhirConfigurationError(RuntimeError):
    pass


class FhirResponseError(RuntimeError):
    pass


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def configuration() -> tuple[str, str]:
    base = os.getenv("FHIR_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("FHIR_BEARER_TOKEN", "").strip()
    if not base or not token:
        raise FhirConfigurationError("Configure FHIR_BASE_URL e FHIR_BEARER_TOKEN no backend.")
    try:
        url = urlsplit(base)
        port = url.port
    except ValueError as error:
        raise FhirConfigurationError("FHIR_BASE_URL é inválida.") from error
    if (
        not url.hostname or url.username is not None or url.password is not None
        or url.query or url.fragment or any(character.isspace() for character in base)
        or (url.scheme != "https" and not (url.scheme == "http" and _is_loopback(url.hostname)))
    ):
        raise FhirConfigurationError(
            "FHIR_BASE_URL deve usar HTTPS, ou HTTP apenas para testes no próprio computador."
        )
    if port is not None and not 1 <= port <= 65535:
        raise FhirConfigurationError("FHIR_BASE_URL contém porta inválida.")
    if any(ord(character) < 33 or ord(character) > 126 for character in token):
        raise FhirConfigurationError("FHIR_BEARER_TOKEN é inválido.")
    return base, token


def _same_fhir_server(base: str, candidate: str) -> bool:
    expected = urlsplit(base)
    target = urlsplit(candidate)
    try:
        same_origin = (
            target.scheme == expected.scheme
            and target.hostname == expected.hostname
            and (target.port or (443 if target.scheme == "https" else 80))
            == (expected.port or (443 if expected.scheme == "https" else 80))
        )
    except ValueError:
        return False
    base_path = posixpath.normpath(unquote(expected.path or "/"))
    decoded_path = unquote(target.path or "/")
    target_path = posixpath.normpath(decoded_path)
    return (
        same_origin and target.username is None and target.password is None and not target.fragment
        and "\\" not in decoded_path and "%" not in decoded_path
        and (base_path == "/" or target_path == base_path or target_path.startswith(base_path + "/"))
    )


@private_http
def _resources(base: str, token: str, resource_type: str, patient_id: str) -> list[dict]:
    url = f"{base}/{resource_type}"
    params: dict[str, str] | None = {"patient": patient_id, "_count": "100"}
    visited = set()
    resources = []
    try:
        with _client() as client:
            for _ in range(MAX_PAGES):
                if url in visited or not _same_fhir_server(base, url):
                    raise FhirResponseError("Paginação FHIR inválida ou fora do servidor configurado.")
                visited.add(url)
                with client.stream(
                    "GET",
                    url,
                    params=params,
                    headers={
                        "Accept": "application/fhir+json",
                        "Accept-Encoding": "identity",
                        "Authorization": f"Bearer {token}",
                    },
                ) as response:
                    params = None
                    response.raise_for_status()
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise FhirResponseError("O servidor FHIR enviou uma resposta compactada não suportada.")
                    content = bytearray()
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        content.extend(chunk)
                        if len(content) > MAX_PAGE_BYTES:
                            raise FhirResponseError("Uma página FHIR ultrapassou o limite de 5 MB.")
                    bundle = json.loads(content)
                    response_url = str(response.url)
                if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
                    raise FhirResponseError("O servidor FHIR não retornou um Bundle válido.")
                entries = bundle.get("entry", [])
                links = bundle.get("link", [])
                if not isinstance(entries, list) or not isinstance(links, list):
                    raise FhirResponseError("O Bundle FHIR contém entradas ou links inválidos.")
                for entry in entries:
                    if not isinstance(entry, dict) or not isinstance(entry.get("resource"), dict):
                        raise FhirResponseError("O Bundle FHIR contém uma entrada inválida.")
                    resources.append(entry["resource"])
                if len(resources) > MAX_RESOURCES:
                    raise FhirResponseError("A consulta FHIR excedeu o limite de 10.000 recursos.")
                next_links = [
                    item.get("url") for item in links
                    if isinstance(item, dict) and item.get("relation") == "next"
                ]
                if not next_links:
                    return resources
                if len(next_links) != 1 or not isinstance(next_links[0], str):
                    raise FhirResponseError("O Bundle FHIR contém links de paginação inválidos.")
                url = urljoin(response_url, next_links[0])
            raise FhirResponseError("A consulta FHIR excedeu o limite de páginas.")
    except httpx.HTTPStatusError as error:
        raise FhirResponseError(f"O servidor FHIR retornou HTTP {error.response.status_code}.") from error
    except httpx.RequestError as error:
        raise FhirResponseError("Falha de conexão ou tempo limite ao consultar FHIR.") from error
    except ValueError as error:
        raise FhirResponseError("O servidor FHIR retornou JSON inválido.") from error


def _client() -> httpx.Client:
    return httpx.Client(timeout=15, follow_redirects=False, trust_env=False)


def _subject_matches(resource: dict, base: str, patient_id: str) -> bool:
    subject = resource.get("subject")
    reference = subject.get("reference") if isinstance(subject, dict) else None
    return reference in (f"Patient/{patient_id}", f"{base}/Patient/{patient_id}")


def _vital_field(concept) -> tuple[str, str] | None:
    if not isinstance(concept, dict) or not isinstance(concept.get("coding"), list):
        return None
    fields = {
        VITAL_CODES[item["code"]]
        for item in concept["coding"]
        if (
            isinstance(item, dict) and item.get("system") == LOINC
            and isinstance(item.get("code"), str) and item.get("code") in VITAL_CODES
        )
    }
    if len(fields) > 1:
        raise FhirResponseError("Uma observação FHIR contém códigos vitais incompatíveis.")
    return next(iter(fields), None)


def _vital_observations(resources: list[dict], base: str, patient_id: str) -> dict:
    grouped: dict[str, dict] = {}
    skipped = 0
    for resource in resources:
        if (
            resource.get("resourceType") != "Observation"
            or resource.get("status") not in ("final", "amended", "corrected")
            or not _subject_matches(resource, base, patient_id)
        ):
            skipped += 1
            continue
        components = resource.get("component", [])
        if not isinstance(components, list) or any(not isinstance(item, dict) for item in components):
            raise FhirResponseError("Componentes de uma observação FHIR são inválidos.")
        values = [(resource.get("code"), resource.get("valueQuantity"))]
        values.extend(
            (component.get("code"), component.get("valueQuantity"))
            for component in components
        )
        recognized = [(_vital_field(code), quantity) for code, quantity in values]
        recognized = [(field, quantity) for field, quantity in recognized if field is not None]
        if not recognized:
            skipped += 1
            continue
        try:
            observed_at = timestamp(resource.get("effectiveDateTime"), 1, preserve_fraction=True)
        except ClinicalDataError as error:
            raise FhirResponseError(
                "Uma observação FHIR reconhecida precisa de effectiveDateTime com fuso."
            ) from error
        row = grouped.setdefault(observed_at, {"patient_id": patient_id, "recorded_at": observed_at})
        for (field, expected_unit), quantity in recognized:
            if (
                not isinstance(quantity, dict) or quantity.get("system") != UCUM
                or quantity.get("code") != expected_unit or "value" not in quantity
            ):
                raise FhirResponseError(
                    f"Observação FHIR de {field} sem valor ou unidade UCUM esperada ({expected_unit})."
                )
            if field in row:
                raise FhirResponseError("Observações FHIR duplicadas para o mesmo sinal e instante.")
            row[field] = quantity["value"]
    if not grouped:
        raise FhirResponseError("O FHIR não retornou sinais vitais compatíveis para o paciente informado.")
    try:
        result = analyze_vitals(list(grouped.values()), {}, allow_partial=True)
    except ClinicalDataError as error:
        raise FhirResponseError(f"Observação FHIR inválida: {error}") from error
    result["source"] = "FHIR R4"
    result["warnings"] = (
        [f"{skipped} observação(ões) não foram importadas por código, estado ou sujeito incompatível."]
        if skipped else []
    )
    result["notice"] = (
        "Importação FHIR manual; medições ausentes não são estimadas. "
        "Limites são demonstrativos e exigem revisão humana."
    )
    return result


def _medication_label(resource: dict) -> str | None:
    concept = resource.get("medicationCodeableConcept")
    if not isinstance(concept, dict):
        return None
    text = concept.get("text")
    if isinstance(text, str) and text.strip() and len(text.strip()) <= 120:
        return text.strip()
    coding = concept.get("coding", [])
    if not isinstance(coding, list):
        return None
    for item in coding:
        display = item.get("display") if isinstance(item, dict) else None
        if isinstance(display, str) and display.strip() and len(display.strip()) <= 120:
            return display.strip()
    return None


def _simple_dose(resource: dict) -> tuple[float | None, str | None]:
    instructions = resource.get("dosageInstruction", [])
    if not isinstance(instructions, list) or len(instructions) != 1 or not isinstance(instructions[0], dict):
        return None, None
    doses = instructions[0].get("doseAndRate", [])
    if not isinstance(doses, list) or len(doses) != 1 or not isinstance(doses[0], dict):
        return None, None
    quantity = doses[0].get("doseQuantity")
    if not isinstance(quantity, dict) or isinstance(quantity.get("value"), bool):
        return None, None
    value = quantity.get("value")
    unit = quantity.get("code") or quantity.get("unit")
    if (
        not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
        or not isinstance(unit, str) or not unit.strip() or len(unit) > 16
    ):
        return None, None
    return float(value), unit.strip()


def _medication_requests(resources: list[dict], base: str, patient_id: str) -> dict:
    records = []
    skipped = 0
    without_simple_dose = 0
    for resource in resources:
        status = resource.get("status")
        name = _medication_label(resource)
        if (
            resource.get("resourceType") != "MedicationRequest"
            or not _subject_matches(resource, base, patient_id)
            or status not in ("active", "on-hold", "cancelled", "completed", "stopped", "draft", "unknown")
            or not name
        ):
            skipped += 1
            continue
        try:
            authored_at = timestamp(resource.get("authoredOn"), 1, preserve_fraction=True)
        except ClinicalDataError:
            skipped += 1
            continue
        dose, unit = _simple_dose(resource)
        if dose is None:
            without_simple_dose += 1
        records.append({
            "patient_ref": "caso-001", "recorded_at": authored_at, "medication": name,
            "dose": dose, "unit": unit, "status": status, "route": "", "frequency": "",
        })
    if not records:
        raise FhirResponseError("O FHIR não retornou prescrições compatíveis para o paciente informado.")
    records.sort(key=lambda row: row["recorded_at"])
    events = [{
        "patient_ref": row["patient_ref"], "recorded_at": row["recorded_at"],
        "kind": "fhir_order", "medication": row["medication"],
        "message": f"Ordem FHIR: {row['medication']} (estado {row['status']}); revisar.",
        "priority": "review",
    } for row in records]
    warnings = []
    if skipped:
        warnings.append(f"{skipped} prescrição(ões) não foram importadas por dados incompatíveis.")
    if without_simple_dose:
        warnings.append(f"{without_simple_dose} dose(s) ausentes ou complexas não foram interpretadas.")
    return {
        "kind": "prescriptions", "source": "FHIR R4", "record_count": len(records),
        "patient_count": 1, "records": records, "events": events, "warnings": warnings,
        "notice": (
            "São ordens FHIR, não histórico de versões ou administração. "
            "A aplicação não verifica prescrição, dose segura, indicação ou interações."
        ),
    }


def import_patient_data(patient_id: str, kind: str) -> dict:
    if not isinstance(patient_id, str) or not FHIR_ID.fullmatch(patient_id):
        raise ClinicalDataError("Informe um identificador FHIR válido (até 64 caracteres).")
    if kind not in ("vitals", "prescriptions"):
        raise ClinicalDataError("Escolha sinais vitais ou prescrições.")
    base, token = configuration()
    resource_type = "Observation" if kind == "vitals" else "MedicationRequest"
    resources = _resources(base, token, resource_type, patient_id)
    if kind == "vitals":
        return _vital_observations(resources, base, patient_id)
    return _medication_requests(resources, base, patient_id)
