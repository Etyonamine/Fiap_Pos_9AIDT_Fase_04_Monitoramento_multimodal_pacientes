import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import database
from app.routers import clinical_data
from app.services.clinical_data import (
    ClinicalDataError, analyze_prescriptions, finite_number, parse_records, patient_ref, timestamp,
)
from app.services.azure_service import AzureAudioError


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize()
    app = FastAPI()
    app.include_router(clinical_data.router)
    with TestClient(app) as test_client:
        yield test_client


def test_vitals_csv_import_detects_threshold_crossings_and_rapid_changes(client):
    csv = (
        "recorded_at,patient_id,heart_rate_bpm,systolic_mmhg,diastolic_mmhg,spo2_percent\n"
        "2026-11-18T10:00:00-03:00,synthetic-01,78,120,80,97\n"
        "2026-11-18T10:15:00-03:00,synthetic-01,80,121,81,97\n"
        "2026-11-18T10:30:00-03:00,synthetic-01,132,120,80,88\n"
        "2026-11-18T10:45:00-03:00,synthetic-01,134,120,80,87\n"
        "2026-11-18T11:00:00-03:00,synthetic-01,84,120,80,97\n"
        "2026-11-18T11:15:00-03:00,synthetic-01,132,120,80,88\n"
    )
    response = client.post(
        "/api/clinical-data/vitals",
        files={"file": ("sample.csv", csv, "text/csv")},
    )
    assert response.status_code == 201
    result = response.json()
    assert result["record_count"] == 6
    assert result["patient_count"] == 1
    assert result["points"][0]["recorded_at"] == "2026-11-18T13:00:00Z"
    assert result["points"][0]["patient_ref"] == f"imp-{result['id'][:8]}-001"
    threshold_events = [event for event in result["events"] if event["kind"] == "threshold_crossing"]
    assert [(event["field"], event["recorded_at"]) for event in threshold_events] == [
        ("heart_rate_bpm", "2026-11-18T13:30:00Z"),
        ("spo2_percent", "2026-11-18T13:30:00Z"),
        ("heart_rate_bpm", "2026-11-18T14:15:00Z"),
        ("spo2_percent", "2026-11-18T14:15:00Z"),
    ]
    assert all(event["priority"] == "review" for event in result["events"])
    assert "not" not in result["rules"]["notice"].lower()
    assert client.get("/api/clinical-data/imports").json()[0]["id"] == result["id"]
    assert client.get("/api/clinical-data/examples/vitals").status_code == 200


@pytest.mark.parametrize(
    ("csv", "expected"),
    [
        (
            "recorded_at,patient_id,heart_rate_bpm,systolic_mmhg,diastolic_mmhg,spo2_percent\n"
            "2026-11-18T10:00:00,synthetic-01,78,120,80,97\n",
            "fuso horário",
        ),
        (
            "recorded_at,patient_id,heart_rate_bpm,systolic_mmhg,diastolic_mmhg,spo2_percent\n"
            "2026-11-18T10:00:00Z,synthetic-01,NaN,120,80,97\n",
            "entre 20 e 250",
        ),
    ],
)
def test_vitals_import_rejects_missing_timezone_and_nonfinite_values(client, csv, expected):
    response = client.post(
        "/api/clinical-data/vitals",
        files={"file": ("sample.csv", csv, "text/csv")},
    )
    assert response.status_code == 422
    assert expected in response.json()["detail"]


def test_vitals_import_rejects_duplicate_patient_timestamps(client):
    record = {
        "patient_id": "synthetic-01", "recorded_at": "2026-11-18T10:00:00Z",
        "heart_rate_bpm": 78, "systolic_mmhg": 120,
        "diastolic_mmhg": 80, "spo2_percent": 97,
    }
    response = client.post(
        "/api/clinical-data/vitals",
        files={"file": ("sample.json", json.dumps([record, record]), "application/json")},
    )
    assert response.status_code == 422
    assert "únicos" in response.json()["detail"]


def test_prescription_import_compares_history_without_claiming_medical_safety(client):
    records = [
        {"patient_id": "synthetic-01", "recorded_at": "2026-11-18T08:00:00Z",
         "medication": "Medicamento A", "dose": 10, "unit": "mg", "status": "active"},
        {"patient_id": "synthetic-01", "recorded_at": "2026-11-19T08:00:00Z",
         "medication": "medicamento a", "dose": 10, "unit": "mg", "status": "active"},
        {"patient_id": "synthetic-01", "recorded_at": "2026-11-20T08:00:00Z",
         "medication": "Medicamento A", "dose": 30, "unit": "mg", "status": "active"},
        {"patient_id": "synthetic-01", "recorded_at": "2026-11-21T08:00:00Z",
         "medication": "Medicamento A", "dose": 30, "unit": "mg", "status": "discontinued"},
    ]
    response = client.post(
        "/api/clinical-data/prescriptions",
        files={"file": ("history.json", json.dumps(records), "application/json")},
    )
    assert response.status_code == 201
    result = response.json()
    assert [event["kind"] for event in result["events"]] == [
        "started", "regimen_changed", "discontinued",
    ]
    assert result["events"][1]["previous"]["dose"] == 10
    assert result["events"][1]["current"]["dose"] == 30
    assert "não valida prescrição" in result["notice"]
    assert client.get("/api/clinical-data/examples/prescriptions").status_code == 200


def test_prescription_acceptance_distinguishes_expected_unexpected_and_missing_plan(client):
    baseline = {
        "patient_id": "synthetic-01", "medication": "Medicamento A",
        "unit": "mg", "status": "active", "route": "oral",
    }
    def plan(dose):
        return {"dose": dose, "unit": "mg", "status": "active", "route": "oral"}

    records = [
        {**baseline, "recorded_at": f"2026-11-{day:02d}T08:00:00Z",
         "dose": dose, **({"expected_regimen": plan(expected)} if expected else {})}
        for day, dose, expected in [
            (18, 10, 10), (19, 20, 20), (20, 30, 20),
            (21, 30, 20), (22, 30, None), (23, 40, None), (24, 40, 50),
        ]
    ]
    response = client.post(
        "/api/clinical-data/prescriptions",
        files={"file": ("acceptance.json", json.dumps(records), "application/json")},
    )
    assert response.status_code == 201
    result = response.json()
    assert [row["plan_comparison"]["status"] for row in result["records"]] == [
        "matches", "matches", "differs", "differs", "not_provided", "not_provided", "differs",
    ]
    assert result["records"][2]["plan_comparison"]["different_fields"] == ["dose"]
    assert result["records"][2]["plan_comparison"]["compared_fields"] == [
        "dose", "unit", "status", "route",
    ]
    assert [event["kind"] for event in result["events"]] == [
        "started", "expected_regimen_change", "unexpected_regimen",
        "regimen_changed", "unexpected_regimen",
    ]
    assert result["events"][1]["priority"] == "information"
    assert result["events"][2]["priority"] == "review"
    assert "autoria da referência" in result["notice"]


@pytest.mark.parametrize("reference", [
    {}, {"dose": 10, "unit": "mg"}, {"dose": True, "unit": "mg", "status": "active"},
    {"dose": 10, "unit": "mg/", "status": "active"},
    {"dose": 10, "unit": "mg", "status": "unknown"},
    {"dose": 10, "unit": "mg", "status": "active", "route": 3},
    {"dose": 10, "unit": "mg", "status": "active", "route": "  "},
    {"dose": 10, "unit": "mg", "status": "active", "frequency": None},
    {"dose": 10, "unit": "mg", "status": "active", "frequency": "x" * 81},
    {"dose": 10, "unit": "mg", "status": "active", "dosage": 20},
    "not-a-plan",
])
def test_prescription_rejects_incomplete_or_invalid_expected_plan(reference):
    record = {
        "patient_id": "synthetic-01", "recorded_at": "2026-11-18T08:00:00Z",
        "medication": "Medicamento A", "dose": 10, "unit": "mg", "status": "active",
        "expected_regimen": reference,
    }
    with pytest.raises(ClinicalDataError):
        analyze_prescriptions([record], {})


def test_missing_observed_plan_fields_are_not_treated_as_a_match_or_divergence():
    record = {
        "patient_id": "synthetic-01", "recorded_at": "2026-11-18T08:00:00Z",
        "medication": "Medicamento A", "dose": 10, "unit": "mg", "status": "active",
        "route": None,
        "expected_regimen": {"dose": 10, "unit": "mg", "status": "active", "route": "oral"},
    }
    comparison = analyze_prescriptions([record], {})["records"][0]["plan_comparison"]
    assert comparison["status"] == "incomplete"
    assert comparison["missing_fields"] == ["route"]
    assert comparison["different_fields"] == []

    record["dose"] = 20
    comparison = analyze_prescriptions([record], {})["records"][0]["plan_comparison"]
    assert comparison["status"] == "differs"
    assert comparison["missing_fields"] == ["route"]
    assert comparison["different_fields"] == ["dose"]


def test_note_requires_cloud_consent_and_does_not_store_original_text(client, monkeypatch, tmp_path):
    calls = []

    def analyze(text, config):
        calls.append(text)
        return {
            "provider": "Azure AI Language",
            "key_phrases": ["falta de ar"],
            "key_phrase_mentions": [{
                "term": "falta de ar", "severity": "critical", "negated": False,
                "key_phrases": ["falta de ar"],
            }],
            "sentiment": {
                "label": "negative",
                "scores": {"positive": 0.01, "neutral": 0.09, "negative": 0.9},
                "aggregation": "length_weighted",
            },
        }

    monkeypatch.setattr(clinical_data, "configuration", lambda **kwargs: {"language": True})
    monkeypatch.setattr(clinical_data, "analyze_language", analyze)
    content = json.dumps({
        "patient_id": "synthetic-01",
        "recorded_at": "2026-11-18T10:00:00-03:00",
        "text": "Relata falta de ar após caminhada. Nota sintética reservada.",
    })
    denied = client.post(
        "/api/clinical-data/notes",
        files={"file": ("note.json", content, "application/json")},
        data={"consent_to_cloud": "false"},
    )
    assert denied.status_code == 400
    assert calls == []

    response = client.post(
        "/api/clinical-data/notes",
        files={"file": ("note.json", content, "application/json")},
        data={"consent_to_cloud": "true"},
    )
    assert response.status_code == 201
    result = response.json()
    assert result["language"]["sentiment"]["label"] == "negative"
    assert result["language"]["key_phrase_mentions"][0]["negated"] is False
    assert result["events"][0]["field"] == "falta de ar"
    assert result["patient_ref"] == f"imp-{result['id'][:8]}-001"
    serialized = json.dumps(client.get("/api/clinical-data/imports").json(), ensure_ascii=False)
    assert "Nota sintética reservada" not in serialized
    assert "Relata falta de ar" not in serialized
    assert "sentiment" in serialized
    assert calls == ["Relata falta de ar após caminhada. Nota sintética reservada."]

    vitals = (
        "recorded_at,patient_id,heart_rate_bpm,systolic_mmhg,diastolic_mmhg,spo2_percent\n"
        "2026-11-18T10:00:00Z,synthetic-01,78,120,80,97\n"
    )
    other = client.post(
        "/api/clinical-data/vitals",
        files={"file": ("other.csv", vitals, "text/csv")},
    )
    assert other.status_code == 201
    assert other.json()["points"][0]["patient_ref"] != result["patient_ref"]


def test_note_requires_language_configuration_without_speech_configuration(client, monkeypatch):
    monkeypatch.setattr(
        clinical_data, "configuration",
        lambda **kwargs: (_ for _ in ()).throw(AzureAudioError("Configure Azure Language.")),
    )
    content = json.dumps({
        "patient_id": "synthetic-01", "recorded_at": "2026-11-18T10:00:00Z",
        "text": "Nota clínica sintética.",
    })
    response = client.post(
        "/api/clinical-data/notes",
        files={"file": ("note.json", content, "application/json")},
        data={"consent_to_cloud": "true"},
    )
    assert response.status_code == 503
    assert "Configure Azure Language" in response.json()["detail"]
    assert client.get("/api/clinical-data/imports").json() == []


def test_examples_return_not_found_for_unknown_or_missing_assets(client, monkeypatch, tmp_path):
    assert client.get("/api/clinical-data/examples/unknown").status_code == 404
    monkeypatch.setattr(clinical_data, "EXAMPLES", tmp_path)
    assert client.get("/api/clinical-data/examples/vitals").status_code == 404


@pytest.mark.parametrize(
    ("filename", "content", "status"),
    [
        ("empty.csv", b"", 422),
        ("unsupported.txt", b"data", 422),
        ("oversized.csv", b"x" * (clinical_data.MAX_UPLOAD_BYTES + 1), 413),
    ],
)
def test_vitals_upload_rejects_empty_unsupported_and_oversized_files(
    client, filename, content, status,
):
    response = client.post(
        "/api/clinical-data/vitals",
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == status


@pytest.mark.parametrize(
    ("filename", "content", "expected_status"),
    [
        ("note.txt", b"{}", 415),
        ("note.json", b"{", 422),
    ],
)
def test_note_requires_json_file_and_valid_payload(client, filename, content, expected_status):
    response = client.post(
        "/api/clinical-data/notes",
        files={"file": (filename, content, "application/json")},
        data={"consent_to_cloud": "true"},
    )
    assert response.status_code == expected_status


def test_note_analysis_failure_is_reported_without_persisting_text(client, monkeypatch):
    monkeypatch.setattr(clinical_data, "configuration", lambda **kwargs: {"language": True})

    def fail(*args):
        raise AzureAudioError("Azure temporarily unavailable.")

    monkeypatch.setattr(clinical_data, "analyze_language", fail)
    content = json.dumps({
        "patient_id": "synthetic-01",
        "recorded_at": "2026-11-18T10:00:00Z",
        "text": "Nota clínica sintética.",
    })
    response = client.post(
        "/api/clinical-data/notes",
        files={"file": ("note.json", content, "application/json")},
        data={"consent_to_cloud": "true"},
    )
    assert response.status_code == 502
    assert "não foi persistido" in response.json()["detail"]
    assert client.get("/api/clinical-data/imports").json() == []


@pytest.mark.parametrize(
    ("content", "filename", "expected"),
    [
        (b"\xff", "sample.csv", "UTF-8"),
        (b"{", "sample.json", "interpretar"),
        (b"[]", "sample.json", "pelo menos"),
        (b"{}", "sample.json", "pelo menos"),
        (b"{}", "sample.txt", "CSV ou JSON"),
        (b"id,id\n1,2\n", "sample.csv", "cabeçalho"),
        (b"[3]", "sample.json", "objeto"),
    ],
)
def test_record_parser_rejects_malformed_or_unsupported_inputs(content, filename, expected):
    with pytest.raises(ClinicalDataError, match=expected):
        parse_records(content, filename)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "obrigatório"),
        ("not-a-date", "ISO 8601"),
        ("2026-11-18T10:00:00", "fuso horário"),
    ],
)
def test_timestamp_rejects_missing_invalid_or_timezone_free_values(value, expected):
    with pytest.raises(ClinicalDataError, match=expected):
        timestamp(value, 1)


@pytest.mark.parametrize("value", [None, 42, "unsafe patient id", ""])
def test_patient_pseudonym_validation_rejects_invalid_identifiers(value):
    with pytest.raises(ClinicalDataError, match="pseudônimo"):
        patient_ref(value, 1)


@pytest.mark.parametrize("value", [True, "not-a-number", float("inf"), 0])
def test_finite_number_rejects_non_numeric_boolean_nonfinite_and_out_of_range(value):
    with pytest.raises(ClinicalDataError, match="numérico|entre"):
        finite_number(value, 1, "dose", (0.001, 100_000))


def test_prescription_history_detects_restart_and_regimen_changes():
    records = [
        {"patient_id": "synthetic-01", "recorded_at": "2026-11-18T08:00:00Z",
         "medication": "Medicamento B", "dose": 10, "unit": "mg", "status": "discontinued"},
        {"patient_id": "synthetic-01", "recorded_at": "2026-11-19T08:00:00Z",
         "medication": "Medicamento B", "dose": 10, "unit": "mg", "status": "active"},
        {"patient_id": "synthetic-01", "recorded_at": "2026-11-20T08:00:00Z",
         "medication": "Medicamento B", "dose": 10, "unit": "mg",
         "status": "active", "frequency": "duas vezes ao dia"},
    ]
    result = analyze_prescriptions(records, {})
    assert [event["kind"] for event in result["events"]] == ["restarted", "regimen_changed"]

    with pytest.raises(ClinicalDataError, match="status"):
        analyze_prescriptions([{**records[1], "status": "unknown"}], {})
