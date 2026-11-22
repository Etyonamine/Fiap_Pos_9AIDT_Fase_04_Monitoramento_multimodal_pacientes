import json
import logging

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.routers import clinical_data
from app.services import fhir_r4
from app.services.clinical_data import ClinicalDataError, analyze_vitals

PATIENT = "synthetic-fhir-1"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"


def observation(code, value, unit, recorded_at, **overrides):
    return {
        "resourceType": "Observation",
        "status": "final",
        "subject": {"reference": f"Patient/{PATIENT}"},
        "effectiveDateTime": recorded_at,
        "code": {"coding": [{"system": LOINC, "code": code}]},
        "valueQuantity": {"system": UCUM, "code": unit, "value": value},
        **overrides,
    }


def bundle(resources, links=None):
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": item} for item in resources],
        "link": links or [],
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FHIR_BASE_URL", "https://fhir.example.test/r4")
    monkeypatch.setenv("FHIR_BEARER_TOKEN", "synthetic-token")
    database.initialize()
    app = FastAPI()
    app.include_router(clinical_data.router)
    with TestClient(app) as test_client:
        yield test_client


def use_fhir_transport(monkeypatch, handler):
    monkeypatch.setattr(
        fhir_r4, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_fhir_imports_paged_vitals_without_inventing_missing_values(client, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer synthetic-token"
        assert request.headers["accept"] == "application/fhir+json"
        if len(requests) == 1:
            assert request.url.params["patient"] == PATIENT
            return httpx.Response(200, json=bundle([
                observation("8867-4", 132, "/min", "2026-11-18T10:00:00Z"),
                {
                    "resourceType": "Observation",
                    "status": "final",
                    "subject": {"reference": f"Patient/{PATIENT}"},
                    "effectiveDateTime": "2026-11-18T10:00:00Z",
                    "code": {"coding": [{"system": LOINC, "code": "85354-9"}]},
                    "component": [
                        observation("8480-6", 85, "mm[Hg]", "2026-11-18T10:00:00Z"),
                        observation("8462-4", 55, "mm[Hg]", "2026-11-18T10:00:00Z"),
                    ],
                },
            ], [{"relation": "next", "url": "?page=2"}]))
        assert request.url.params["page"] == "2"
        return httpx.Response(200, json=bundle([
            observation("59408-5", 88, "%", "2026-11-18T10:15:00Z"),
            observation("2708-6", 90, "%", "2026-11-18T10:20:00Z"),
            observation(
                "8867-4", 60, "/min", "2026-11-18T10:30:00Z",
                subject={"reference": "Patient/different-patient"},
            ),
        ]))

    use_fhir_transport(monkeypatch, handler)
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert response.status_code == 201
    result = response.json()
    assert result["source"] == "FHIR R4"
    assert result["record_count"] == 2
    assert result["points"][0]["heart_rate_bpm"] == 132
    assert result["points"][0]["systolic_mmhg"] == 85
    assert "spo2_percent" not in result["points"][0]
    assert result["points"][1]["spo2_percent"] == 88
    assert "heart_rate_bpm" not in result["points"][1]
    assert {event["field"] for event in result["events"]} == {
        "heart_rate_bpm", "systolic_mmhg", "diastolic_mmhg", "spo2_percent",
    }
    assert result["warnings"] == [
        "2 observação(ões) não foram importadas por código, estado ou sujeito incompatível."
    ]
    assert PATIENT not in json.dumps(client.get("/api/clinical-data/imports").json())


def test_partial_vitals_keep_per_signal_history_without_duplicating_thresholds():
    records = [
        {"patient_id": PATIENT, "recorded_at": "2026-11-18T10:00:00Z", "heart_rate_bpm": 130},
        {"patient_id": PATIENT, "recorded_at": "2026-11-18T10:05:00Z", "spo2_percent": 97},
        {"patient_id": PATIENT, "recorded_at": "2026-11-18T10:10:00Z", "heart_rate_bpm": 135},
        {"patient_id": PATIENT, "recorded_at": "2026-11-18T10:20:00Z", "heart_rate_bpm": 90},
        {"patient_id": PATIENT, "recorded_at": "2026-11-18T10:25:00Z", "heart_rate_bpm": 125},
    ]
    result = analyze_vitals(records, {}, allow_partial=True)
    crossings = [item for item in result["events"] if item["kind"] == "threshold_crossing"]
    changes = [item for item in result["events"] if item["kind"] == "rapid_change"]
    assert [item["recorded_at"] for item in crossings] == [
        "2026-11-18T10:00:00.000000Z", "2026-11-18T10:25:00.000000Z",
    ]
    assert len(changes) == 2
    with pytest.raises(ClinicalDataError):
        analyze_vitals(records, {})


def test_partial_vitals_require_a_measurement_and_consistent_blood_pressure():
    row = {"patient_id": PATIENT, "recorded_at": "2026-11-18T10:00:00Z"}
    with pytest.raises(ClinicalDataError, match="ao menos um sinal"):
        analyze_vitals([row], {}, allow_partial=True)
    with pytest.raises(ClinicalDataError, match="sistólica deve superar"):
        analyze_vitals([{**row, "systolic_mmhg": 80, "diastolic_mmhg": 100}], {}, allow_partial=True)


def test_fhir_prescriptions_are_orders_not_inferred_treatment_history(client, monkeypatch):
    resource = {
        "resourceType": "MedicationRequest",
        "status": "active",
        "subject": {"reference": f"Patient/{PATIENT}"},
        "authoredOn": "2026-11-18T10:00:00Z",
        "medicationCodeableConcept": {"text": "Medicamento sintético"},
        "dosageInstruction": [{
            "doseAndRate": [{"doseQuantity": {"value": 10, "code": "mg", "system": UCUM}}],
        }],
    }
    missing_dose = {
        **resource, "status": "completed", "authoredOn": "2026-11-19T10:00:00Z",
        "dosageInstruction": [],
    }
    use_fhir_transport(monkeypatch, lambda request: httpx.Response(
        200, json=bundle([resource, missing_dose]),
    ))
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "prescriptions", "authorized": True},
    )
    assert response.status_code == 201
    result = response.json()
    assert result["records"][0]["dose"] == 10
    assert result["records"][1]["dose"] is None
    assert result["records"][1]["status"] == "completed"
    assert [item["kind"] for item in result["events"]] == ["fhir_order", "fhir_order"]
    assert "não foram interpretadas" in result["warnings"][0]
    assert "não histórico de versões" in result["notice"]
    assert PATIENT not in json.dumps(result)


def test_fhir_requires_authorization_configuration_and_safe_patient_id(client, monkeypatch):
    denied = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": False},
    )
    assert denied.status_code == 400
    invalid = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": "../patient", "kind": "vitals", "authorized": True},
    )
    assert invalid.status_code == 422
    monkeypatch.delenv("FHIR_BEARER_TOKEN")
    missing = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert missing.status_code == 503
    assert client.get("/api/clinical-data/imports").json() == []


def test_fhir_refuses_cross_origin_pagination_without_sending_the_token(client, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=bundle([], [{
            "relation": "next", "url": "https://other.example.test/steal-token",
        }]))

    use_fhir_transport(monkeypatch, handler)
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert response.status_code == 502
    assert "paginação" in response.json()["detail"].lower()
    assert len(requests) == 1
    assert client.get("/api/clinical-data/imports").json() == []


def test_fhir_keeps_distinct_subsecond_readings_in_temporal_order(client, monkeypatch):
    resources = [
        observation("8867-4", 100, "/min", "2026-11-18T10:00:00.500Z"),
        observation("8867-4", 80, "/min", "2026-11-18T10:00:00Z"),
        observation("8867-4", 110, "/min", "2026-11-18T10:00:00.900Z"),
    ]
    use_fhir_transport(monkeypatch, lambda request: httpx.Response(200, json=bundle(resources)))
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert response.status_code == 201
    points = response.json()["points"]
    assert [point["heart_rate_bpm"] for point in points] == [80, 100, 110]
    assert [point["recorded_at"] for point in points] == [
        "2026-11-18T10:00:00.000000Z",
        "2026-11-18T10:00:00.500000Z",
        "2026-11-18T10:00:00.900000Z",
    ]


def test_fhir_ignores_malformed_coding_without_uncaught_type_error(client, monkeypatch):
    malformed = observation("8867-4", 130, "/min", "2026-11-18T10:00:00Z")
    malformed["code"] = {"coding": [{"system": LOINC, "code": ["8867-4"]}]}
    use_fhir_transport(monkeypatch, lambda request: httpx.Response(
        200, json=bundle([malformed]),
    ))
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert response.status_code == 502
    assert client.get("/api/clinical-data/imports").json() == []


@pytest.mark.parametrize(
    "next_url",
    [
        "https://fhir.example.test/outside",
        "https://fhir.example.test/r4/%252e%252e/escape",
        "https://fhir.example.test/r4/%5c..%5cescape",
        "https://other.example.test/r4/Observation",
        "http://fhir.example.test/r4/Observation",
    ],
)
def test_fhir_rejects_unsafe_pagination_paths(client, monkeypatch, next_url):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=bundle([], [{"relation": "next", "url": next_url}]))

    use_fhir_transport(monkeypatch, handler)
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert response.status_code == 502
    assert len(seen) == 1


def test_fhir_caps_response_while_streaming(client, monkeypatch):
    chunks = []

    class LargeStream(httpx.SyncByteStream):
        def __iter__(self):
            for index in range(10):
                chunks.append(index)
                yield b" " * 65536

    monkeypatch.setattr(fhir_r4, "MAX_PAGE_BYTES", 100_000)
    use_fhir_transport(monkeypatch, lambda _request: httpx.Response(200, stream=LargeStream()))
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert response.status_code == 502
    assert "limite" in response.json()["detail"]
    assert len(chunks) == 2


def test_fhir_does_not_log_patient_query_or_bearer_token(client, monkeypatch, caplog):
    use_fhir_transport(monkeypatch, lambda _request: httpx.Response(200, json=bundle([
        observation("8867-4", 100, "/min", "2026-11-18T10:00:00Z"),
    ])))
    with caplog.at_level(logging.INFO, logger="httpx"):
        response = client.post(
            "/api/clinical-data/fhir",
            json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
        )
    assert response.status_code == 201
    assert PATIENT not in caplog.text
    assert "synthetic-token" not in caplog.text


def test_fhir_rejects_more_precision_than_it_can_preserve(client, monkeypatch):
    resources = [observation("8867-4", 100, "/min", "2026-11-18T10:00:00.1234567Z")]
    use_fhir_transport(monkeypatch, lambda _request: httpx.Response(200, json=bundle(resources)))
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert response.status_code == 502
    assert client.get("/api/clinical-data/imports").json() == []


@pytest.mark.parametrize(
    "url,token,valid",
    [
        ("http://localhost:8000/r4", "token", True),
        ("http://127.0.0.1:8000/r4", "token", True),
        ("http://fhir.example.test/r4", "token", False),
        ("https://user:pass@fhir.example.test/r4", "token", False),
        ("https://fhir.example.test/r4?secret=x", "token", False),
        ("https://fhir.example.test:99999/r4", "token", False),
        ("https://fhir.example.test:0/r4", "token", False),
        ("https://fhir.example.test/r4", "bad\ntoken", False),
    ],
)
def test_fhir_configuration_accepts_only_safe_urls_and_tokens(client, monkeypatch, url, token, valid):
    monkeypatch.setenv("FHIR_BASE_URL", url)
    monkeypatch.setenv("FHIR_BEARER_TOKEN", token)
    if valid:
        assert fhir_r4.configuration() == (url, token)
    else:
        with pytest.raises(fhir_r4.FhirConfigurationError):
            fhir_r4.configuration()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"{"),
        httpx.Response(200, json={"resourceType": "Patient"}),
        httpx.Response(200, json={"resourceType": "Bundle", "entry": {}}),
        httpx.Response(200, json={"resourceType": "Bundle", "entry": [None]}),
        httpx.Response(200, json=bundle([], [{"relation": "next", "url": 5}])),
        httpx.Response(200, stream=httpx.ByteStream(b"{}"), headers={"content-encoding": "gzip"}),
        httpx.Response(401),
        httpx.Response(302, headers={"location": "https://other.example.test/"}),
    ],
)
def test_fhir_reports_protocol_errors_without_saving_imports(client, monkeypatch, response):
    calls = []

    def handler(request):
        calls.append(request)
        return response

    use_fhir_transport(monkeypatch, handler)
    result = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert result.status_code == 502
    assert len(calls) == 1
    assert client.get("/api/clinical-data/imports").json() == []


def test_fhir_connection_timeout_and_limits_fail_explicitly(client, monkeypatch):
    def timeout(request):
        raise httpx.ConnectTimeout("Synthetic timeout", request=request)

    use_fhir_transport(monkeypatch, timeout)
    payload = {"patient_id": PATIENT, "kind": "vitals", "authorized": True}
    assert "tempo limite" in client.post("/api/clinical-data/fhir", json=payload).json()["detail"]

    monkeypatch.setattr(fhir_r4, "MAX_RESOURCES", 1)
    use_fhir_transport(monkeypatch, lambda _request: httpx.Response(
        200, json=bundle([{}, {}]),
    ))
    assert "10.000 recursos" in client.post("/api/clinical-data/fhir", json=payload).json()["detail"]

    monkeypatch.setattr(fhir_r4, "MAX_PAGES", 2)
    counter = []

    def next_page(request):
        counter.append(request)
        return httpx.Response(200, json=bundle([], [{
            "relation": "next", "url": f"?page={len(counter)}",
        }]))

    use_fhir_transport(monkeypatch, next_page)
    assert "limite de páginas" in client.post("/api/clinical-data/fhir", json=payload).json()["detail"]
    assert len(counter) == 2


@pytest.mark.parametrize(
    "resource",
    [
        {**observation("8867-4", 100, "/min", "2026-11-18T10:00:00Z"), "component": [None]},
        {**observation("8867-4", 100, "/min", "2026-11-18T10:00:00Z"),
         "code": {"coding": [
             {"system": LOINC, "code": "8867-4"}, {"system": LOINC, "code": "59408-5"},
         ]}},
        observation("8867-4", True, "/min", "2026-11-18T10:00:00Z"),
        observation("8867-4", 100, "/min", "2026-11-18T10:00:00"),
    ],
)
def test_fhir_rejects_ambiguous_malformed_or_invalid_observations(client, monkeypatch, resource):
    use_fhir_transport(monkeypatch, lambda _request: httpx.Response(200, json=bundle([resource])))
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert response.status_code == 502
    assert client.get("/api/clinical-data/imports").json() == []


@pytest.mark.parametrize(
    "quantity",
    [None, {"value": True, "code": "mg"}, {"value": -1, "code": "mg"},
     {"value": 10, "code": ""}, {"value": 10, "code": "x" * 17}],
)
def test_fhir_complex_or_invalid_doses_remain_unavailable(quantity):
    resource = {"dosageInstruction": [{"doseAndRate": [{"doseQuantity": quantity}]}]}
    assert fhir_r4._simple_dose(resource) == (None, None)


def test_fhir_prescription_skips_incompatible_or_undated_orders_with_warning(client, monkeypatch):
    valid = {
        "resourceType": "MedicationRequest", "status": "active",
        "subject": {"reference": f"Patient/{PATIENT}"},
        "authoredOn": "2026-11-18T10:00:00Z",
        "medicationCodeableConcept": {"coding": [{"display": "Exemplo sintético"}]},
    }
    incompatible = {**valid, "status": "entered-in-error"}
    undated = {**valid, "authoredOn": "2026-11-18"}
    no_name = {**valid, "medicationCodeableConcept": {"coding": []}}
    use_fhir_transport(monkeypatch, lambda _request: httpx.Response(
        200, json=bundle([valid, incompatible, undated, no_name]),
    ))
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "prescriptions", "authorized": True},
    )
    assert response.status_code == 201
    result = response.json()
    assert result["record_count"] == 1
    assert result["records"][0]["medication"] == "Exemplo sintético"
    assert result["records"][0]["dose"] is None
    assert result["warnings"][0].startswith("3 prescrição")
    assert "não foram interpretadas" in result["warnings"][1]


def test_fhir_rejects_no_compatible_prescriptions_and_unsupported_kind(monkeypatch):
    with pytest.raises(fhir_r4.FhirResponseError, match="não retornou prescrições"):
        fhir_r4._medication_requests([{}], "https://example.test", PATIENT)
    with pytest.raises(ClinicalDataError, match="Escolha sinais"):
        fhir_r4.import_patient_data(PATIENT, "notes")


@pytest.mark.parametrize(
    "resources",
    [
        [observation("8867-4", 130, "beats/min", "2026-11-18T10:00:00Z")],
        [
            observation("8867-4", 130, "/min", "2026-11-18T10:00:00Z"),
            observation("8867-4", 80, "/min", "2026-11-18T10:00:00Z"),
        ],
        [observation("2708-6", 90, "%", "2026-11-18T10:00:00Z")],
    ],
)
def test_fhir_rejects_unsupported_or_ambiguous_measurements(client, monkeypatch, resources):
    use_fhir_transport(monkeypatch, lambda request: httpx.Response(200, json=bundle(resources)))
    response = client.post(
        "/api/clinical-data/fhir",
        json={"patient_id": PATIENT, "kind": "vitals", "authorized": True},
    )
    assert response.status_code == 502
    assert client.get("/api/clinical-data/imports").json() == []
