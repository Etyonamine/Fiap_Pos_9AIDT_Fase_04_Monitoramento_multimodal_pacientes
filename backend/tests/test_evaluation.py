import json
import math
import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation import EvaluationInputError, evaluate
from evaluation.__main__ import main
from evaluation.metrics import load_document


def document(cases, *, kind="real_annotated", label="test-set"):
    return {"dataset_kind": kind, "dataset_label": label, "cases": cases}


def case(case_id="case-1", events=None, **extra):
    return {"case_id": case_id, "events": events or [], **extra}


def event(timestamp, kind="fall", **extra):
    return {"kind": kind, "timestamp_s": timestamp, **extra}


def test_event_matching_is_one_to_one_and_tolerance_boundary_is_inclusive():
    references = document([case(events=[event(0.4), event(1.0)])])
    predictions = document([case(events=[event(0), event(0.5), event(0.5, "other")])])

    report = evaluate(references, predictions, tolerance_seconds=0.5)

    assert report["event_detection"]["overall"] == {
        "true_positive": 2,
        "false_positive": 1,
        "false_negative": 0,
        "precision": pytest.approx(2 / 3),
        "recall": 1.0,
        "f1": pytest.approx(0.8),
    }
    assert report["event_detection"]["by_case_and_kind"] == [
        {
            "case_id": "case-1",
            "kind": "fall",
            "true_positive": 2,
            "false_positive": 0,
            "false_negative": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
        },
        {
            "case_id": "case-1",
            "kind": "other",
            "true_positive": 0,
            "false_positive": 1,
            "false_negative": 0,
            "precision": 0.0,
            "recall": None,
            "f1": None,
        },
    ]


def test_matcher_finds_maximum_cardinality_instead_of_greedy_nearest_only():
    references = document([case(events=[event(0.4), event(1.0)])])
    predictions = document([case(events=[event(0), event(0.5)])])

    report = evaluate(references, predictions, tolerance_seconds=0.5)

    assert report["event_detection"]["overall"]["true_positive"] == 2
    assert report["event_detection"]["overall"]["false_positive"] == 0
    assert report["event_detection"]["overall"]["false_negative"] == 0


def test_event_counts_are_scoped_by_case_and_kind():
    references = document([
        case("case-a", [event(1)]),
        case("case-b", [event(1)]),
    ])
    predictions = document([
        case("case-a", [event(1, "other")]),
        case("case-b", []),
    ])

    report = evaluate(references, predictions, tolerance_seconds=0)

    assert report["event_detection"]["overall"]["true_positive"] == 0
    assert report["event_detection"]["overall"]["false_positive"] == 1
    assert report["event_detection"]["overall"]["false_negative"] == 2
    assert len(report["event_detection"]["by_case_and_kind"]) == 3


@pytest.mark.parametrize(
    ("reference_events", "prediction_events", "expected"),
    [
        ([], [], (None, None, None)),
        ([], [event(1)], (0.0, None, None)),
        ([event(1)], [], (None, 0.0, None)),
    ],
)
def test_undefined_event_metrics_are_null_not_perfect(
    reference_events, prediction_events, expected,
):
    metrics = evaluate(
        document([case(events=reference_events)]),
        document([case(events=prediction_events)]),
    )["event_detection"]["overall"]

    assert (metrics["precision"], metrics["recall"], metrics["f1"]) == expected


def test_transcription_uses_unicode_case_and_punctuation_normalization():
    report = evaluate(
        document([case(transcript="Ｐreciso, de JOSÉ!")]),
        document([case(transcript="preciso de josé")]),
    )

    transcription = report["transcription"]
    assert transcription["reference_words"] == 3
    assert transcription["hypothesis_words"] == 3
    assert transcription["substitutions"] == 0
    assert transcription["deletions"] == 0
    assert transcription["insertions"] == 0
    assert transcription["word_error_rate"] == 0


def test_transcription_edit_counts_and_empty_reference_rate():
    report = evaluate(
        document([
            case("edited", transcript="one two"),
            case("empty", transcript=""),
        ]),
        document([
            case("edited", transcript="one three extra"),
            case("empty", transcript="inserted"),
        ]),
    )["transcription"]

    assert report["evaluated_cases"] == 2
    assert report["reference_words"] == 2
    assert report["hypothesis_words"] == 4
    assert report["substitutions"] == 1
    assert report["deletions"] == 0
    assert report["insertions"] == 2
    assert report["word_error_rate"] == 1.5


@pytest.mark.parametrize(
    ("reference", "prediction", "message"),
    [
        (document([case(transcript="words")]), document([case()]), "transcript"),
        (document([case(angle_degrees=[1])]), document([case()]), "angle_degrees"),
        (
            document([case(angle_degrees=[1, 2])]),
            document([case(angle_degrees=[1])]),
            "mismatched angle_degrees",
        ),
    ],
)
def test_optional_fields_must_be_present_on_both_sides(reference, prediction, message):
    with pytest.raises(EvaluationInputError, match=message):
        evaluate(reference, prediction)


def test_angle_mae_and_only_supplied_prediction_latency_are_summarized():
    report = evaluate(
        document([case(events=[event(1)], angle_degrees=[20, 40])]),
        document([case(
            events=[
                event(1, latency_ms=20),
                event(2, latency_ms=40),
                event(3),
            ],
            angle_degrees=[23, 35],
        )]),
    )

    assert report["angle_error"] == {
        "evaluated_cases": 1,
        "sample_count": 2,
        "mae_degrees": 4.0,
    }
    assert report["prediction_latency"]["sample_count"] == 2
    assert report["prediction_latency"]["mean_ms"] == 30
    assert report["prediction_latency"]["median_ms"] == 30
    assert report["prediction_latency"]["p95_ms_nearest_rank"] == 40


def test_case_id_mismatch_and_duplicate_ids_are_rejected():
    with pytest.raises(EvaluationInputError, match="missing predictions"):
        evaluate(document([case("missing")]), document([]))
    with pytest.raises(EvaluationInputError, match="duplicate case_id"):
        evaluate(document([case("dup"), case("dup")]), document([case("dup")]))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda doc: doc["cases"][0].pop("case_id"), "missing required field"),
        (lambda doc: doc["cases"][0].update(transcript=None), "must be a string"),
        (lambda doc: doc["cases"][0]["events"].append(event(None)), "finite number"),
        (lambda doc: doc["cases"][0]["events"].append(event(float("nan"))), "finite number"),
        (lambda doc: doc["cases"][0]["events"].append(event(True)), "finite number"),
        (lambda doc: doc["cases"][0]["events"].append(event(-1)), "at least 0"),
        (
            lambda doc: doc["cases"][0]["events"].append(event(1, latency_ms=float("inf"))),
            "finite number",
        ),
        (
            lambda doc: doc["cases"][0].update(angle_degrees=[181]),
            "must not exceed 180",
        ),
        (
            lambda doc: doc["cases"][0]["events"][0].update(extra="typo"),
            "unknown field",
        ),
    ],
)
def test_invalid_or_null_values_are_rejected_without_dropping(mutate, message):
    references = document([case(events=[event(1)])])
    predictions = document([case(events=[event(1)])])
    mutate(references)

    with pytest.raises(EvaluationInputError, match=message):
        evaluate(references, predictions)


def test_dataset_identity_and_tolerance_are_validated():
    with pytest.raises(EvaluationInputError, match="dataset_label must match"):
        evaluate(document([]), document([], label="other"))
    with pytest.raises(EvaluationInputError, match="finite number"):
        evaluate(document([]), document([]), tolerance_seconds=math.inf)
    with pytest.raises(EvaluationInputError, match="at least 0"):
        evaluate(document([]), document([]), tolerance_seconds=-0.1)


def test_json_loader_rejects_nonstandard_nan():
    source = Path(__file__).with_name(f".{uuid4().hex}.json")
    try:
        source.write_text('{"value": NaN}', encoding="utf-8")
        with pytest.raises(EvaluationInputError, match="non-standard JSON number"):
            load_document(source)
    finally:
        source.unlink(missing_ok=True)


def test_synthetic_demo_writes_explicit_transparent_report():
    output = Path(__file__).with_name(f".{uuid4().hex}.json")
    try:
        assert main(["demo", "--output", str(output)]) == 0

        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["dataset"]["kind"] == "synthetic_nonclinical"
        assert report["dataset"]["synthetic_nonclinical"] is True
        assert "not model validation" in report["notice"]
        assert report["event_detection"]["overall"]["true_positive"] == 2
    finally:
        output.unlink(missing_ok=True)


def test_evaluate_cli_reads_json_and_writes_report():
    examples = Path(__file__).parents[1] / "evaluation" / "examples"
    output = Path(__file__).with_name(f".{uuid4().hex}.json")
    try:
        assert main([
            "evaluate",
            "--references", str(examples / "references.json"),
            "--predictions", str(examples / "predictions.json"),
            "--tolerance-seconds", "0.5",
            "--output", str(output),
        ]) == 0
        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["event_tolerance_seconds_inclusive"] == 0.5
        assert report["event_detection"]["overall"]["true_positive"] == 2
    finally:
        output.unlink(missing_ok=True)


def test_cli_reports_missing_input_without_writing_a_report():
    output = Path(__file__).with_name(f".{uuid4().hex}.json")
    try:
        assert main([
            "evaluate",
            "--references", str(output.with_name(f"{output.stem}-missing.json")),
            "--predictions", str(output.with_name(f"{output.stem}-also-missing.json")),
            "--output", str(output),
        ]) == 2
        assert not output.exists()
    finally:
        output.unlink(missing_ok=True)
