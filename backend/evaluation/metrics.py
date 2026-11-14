"""Strict, dependency-free evaluation of annotation and prediction JSON."""

from __future__ import annotations

import json
import math
import statistics
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


class EvaluationInputError(ValueError):
    """Raised when an input document does not conform to the evaluation schema."""


_TOP_LEVEL_FIELDS = {"dataset_kind", "dataset_label", "cases"}
_CASE_FIELDS = {"case_id", "events", "transcript", "angle_degrees"}
_EVENT_FIELDS = {"kind", "timestamp_s", "latency_ms"}
_DATASET_KINDS = {"synthetic_nonclinical", "real_annotated"}


def load_document(path: str | Path) -> dict[str, Any]:
    """Load one UTF-8 JSON document, rejecting non-standard numeric constants."""
    source = Path(path)
    try:
        with source.open(encoding="utf-8") as file:
            return json.load(file, parse_constant=_reject_json_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, EvaluationInputError) as exc:
        raise EvaluationInputError(f"{source}: {exc}") from exc


def _reject_json_constant(value: str) -> None:
    raise EvaluationInputError(f"non-standard JSON number {value!r} is not allowed")


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationInputError(f"{where} must be an object")
    return value


def _fields(
    obj: dict[str, Any],
    required: set[str],
    allowed: set[str],
    where: str,
) -> None:
    missing = required - obj.keys()
    extra = obj.keys() - allowed
    if missing:
        raise EvaluationInputError(f"{where} is missing required field(s): {', '.join(sorted(missing))}")
    if extra:
        raise EvaluationInputError(f"{where} has unknown field(s): {', '.join(sorted(extra))}")


def _finite_number(value: Any, where: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationInputError(f"{where} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise EvaluationInputError(f"{where} must be a finite number") from None
    if not math.isfinite(number):
        raise EvaluationInputError(f"{where} must be a finite number")
    if minimum is not None and number < minimum:
        raise EvaluationInputError(f"{where} must be at least {minimum:g}")
    return number


def _nonempty_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationInputError(f"{where} must be a non-empty string")
    return value


def _validate_document(document: Any, role: str) -> dict[str, Any]:
    obj = _object(document, role)
    _fields(obj, _TOP_LEVEL_FIELDS, _TOP_LEVEL_FIELDS, role)
    kind = _nonempty_string(obj["dataset_kind"], f"{role}.dataset_kind")
    if kind not in _DATASET_KINDS:
        raise EvaluationInputError(
            f"{role}.dataset_kind must be one of {', '.join(sorted(_DATASET_KINDS))}"
        )
    label = _nonempty_string(obj["dataset_label"], f"{role}.dataset_label")
    raw_cases = obj["cases"]
    if not isinstance(raw_cases, list):
        raise EvaluationInputError(f"{role}.cases must be an array")

    cases: dict[str, dict[str, Any]] = {}
    for case_index, raw_case in enumerate(raw_cases):
        where = f"{role}.cases[{case_index}]"
        case = _object(raw_case, where)
        _fields(case, {"case_id", "events"}, _CASE_FIELDS, where)
        case_id = _nonempty_string(case["case_id"], f"{where}.case_id")
        if case_id in cases:
            raise EvaluationInputError(f"{role} has duplicate case_id {case_id!r}")

        raw_events = case["events"]
        if not isinstance(raw_events, list):
            raise EvaluationInputError(f"{where}.events must be an array")
        events: list[dict[str, Any]] = []
        for event_index, raw_event in enumerate(raw_events):
            event_where = f"{where}.events[{event_index}]"
            event = _object(raw_event, event_where)
            _fields(event, {"kind", "timestamp_s"}, _EVENT_FIELDS, event_where)
            normalized_event: dict[str, Any] = {
                "kind": _nonempty_string(event["kind"], f"{event_where}.kind"),
                "timestamp_s": _finite_number(
                    event["timestamp_s"], f"{event_where}.timestamp_s", minimum=0,
                ),
            }
            if "latency_ms" in event:
                normalized_event["latency_ms"] = _finite_number(
                    event["latency_ms"], f"{event_where}.latency_ms", minimum=0,
                )
            events.append(normalized_event)

        normalized_case: dict[str, Any] = {"events": events}
        if "transcript" in case:
            if not isinstance(case["transcript"], str):
                raise EvaluationInputError(f"{where}.transcript must be a string when present")
            normalized_case["transcript"] = case["transcript"]
        if "angle_degrees" in case:
            angles = case["angle_degrees"]
            if not isinstance(angles, list):
                raise EvaluationInputError(f"{where}.angle_degrees must be an array")
            normalized_case["angle_degrees"] = [
                _finite_number(angle, f"{where}.angle_degrees[{index}]", minimum=0)
                for index, angle in enumerate(angles)
            ]
            if any(angle > 180 for angle in normalized_case["angle_degrees"]):
                raise EvaluationInputError(f"{where}.angle_degrees values must not exceed 180")
        cases[case_id] = normalized_case

    return {"dataset_kind": kind, "dataset_label": label, "cases": cases}


def _maximum_matches(
    reference_times: list[float],
    predicted_times: list[float],
    tolerance_seconds: float,
) -> int:
    """Maximum-cardinality one-to-one match, preferring nearby predictions."""
    adjacency = [
        sorted(
            (
                index for index, predicted in enumerate(predicted_times)
                if abs(reference - predicted) <= tolerance_seconds
            ),
            key=lambda index: (abs(reference - predicted_times[index]), index),
        )
        for reference in reference_times
    ]
    order = sorted(range(len(reference_times)), key=lambda index: (len(adjacency[index]), index))
    assigned_reference: dict[int, int] = {}

    def assign(reference_index: int, seen: set[int]) -> bool:
        for prediction_index in adjacency[reference_index]:
            if prediction_index in seen:
                continue
            seen.add(prediction_index)
            previous = assigned_reference.get(prediction_index)
            if previous is None or assign(previous, seen):
                assigned_reference[prediction_index] = reference_index
                return True
        return False

    return sum(assign(index, set()) for index in order)


def _detection_metrics(true_positive: int, false_positive: int, false_negative: int) -> dict[str, Any]:
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive else None
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative else None
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else (0.0 if precision == 0 and recall == 0 else None)
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _event_groups(
    reference_cases: dict[str, dict[str, Any]],
    prediction_cases: dict[str, dict[str, Any]],
    tolerance_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    counts_by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    by_case_and_kind: list[dict[str, Any]] = []
    total = [0, 0, 0]

    for case_id in sorted(reference_cases):
        reference_events = reference_cases[case_id]["events"]
        predicted_events = prediction_cases[case_id]["events"]
        kinds = sorted({event["kind"] for event in reference_events + predicted_events})
        for kind in kinds:
            reference_times = [
                event["timestamp_s"] for event in reference_events if event["kind"] == kind
            ]
            predicted_times = [
                event["timestamp_s"] for event in predicted_events if event["kind"] == kind
            ]
            tp = _maximum_matches(reference_times, predicted_times, tolerance_seconds)
            fp = len(predicted_times) - tp
            fn = len(reference_times) - tp
            for index, count in enumerate((tp, fp, fn)):
                total[index] += count
                counts_by_kind[kind][index] += count
            by_case_and_kind.append({
                "case_id": case_id,
                "kind": kind,
                **_detection_metrics(tp, fp, fn),
            })

    by_kind = [
        {"kind": kind, **_detection_metrics(*counts)}
        for kind, counts in sorted(counts_by_kind.items())
    ]
    return _detection_metrics(*total), by_kind, by_case_and_kind


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return without_punctuation.split()


def _word_errors(reference: list[str], hypothesis: list[str]) -> tuple[int, int, int]:
    """Return substitutions, deletions, insertions from a deterministic edit path."""
    rows, columns = len(reference) + 1, len(hypothesis) + 1
    distance = [[0] * columns for _ in range(rows)]
    operation = [[""] * columns for _ in range(rows)]
    for row in range(1, rows):
        distance[row][0] = row
        operation[row][0] = "delete"
    for column in range(1, columns):
        distance[0][column] = column
        operation[0][column] = "insert"

    for row in range(1, rows):
        for column in range(1, columns):
            same = reference[row - 1] == hypothesis[column - 1]
            options = [
                (distance[row - 1][column - 1] + (not same), "match" if same else "substitute"),
                (distance[row - 1][column] + 1, "delete"),
                (distance[row][column - 1] + 1, "insert"),
            ]
            distance[row][column], operation[row][column] = min(
                options, key=lambda item: item[0],
            )

    substitutions = deletions = insertions = 0
    row, column = len(reference), len(hypothesis)
    while row or column:
        current = operation[row][column]
        if current == "match":
            row -= 1
            column -= 1
        elif current == "substitute":
            substitutions += 1
            row -= 1
            column -= 1
        elif current == "delete":
            deletions += 1
            row -= 1
        else:
            insertions += 1
            column -= 1
    return substitutions, deletions, insertions


def _transcription_metrics(
    reference_cases: dict[str, dict[str, Any]],
    prediction_cases: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    reference_words = hypothesis_words = substitutions = deletions = insertions = 0
    evaluated_cases = 0
    for case_id in sorted(reference_cases):
        reference = reference_cases[case_id].get("transcript")
        hypothesis = prediction_cases[case_id].get("transcript")
        if (reference is None) != (hypothesis is None):
            raise EvaluationInputError(
                f"case {case_id!r} must provide transcript in both documents or neither"
            )
        if reference is None:
            continue
        evaluated_cases += 1
        reference_tokens, hypothesis_tokens = _tokens(reference), _tokens(hypothesis)
        reference_words += len(reference_tokens)
        hypothesis_words += len(hypothesis_tokens)
        errors = _word_errors(reference_tokens, hypothesis_tokens)
        substitutions += errors[0]
        deletions += errors[1]
        insertions += errors[2]
    return {
        "evaluated_cases": evaluated_cases,
        "reference_words": reference_words,
        "hypothesis_words": hypothesis_words,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "word_error_rate": (
            (substitutions + deletions + insertions) / reference_words
            if reference_words else None
        ),
        "normalization": "Unicode NFKC, case-folding, punctuation removal, whitespace tokens",
    }


def _angle_metrics(
    reference_cases: dict[str, dict[str, Any]],
    prediction_cases: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    absolute_errors: list[float] = []
    evaluated_cases = 0
    for case_id in sorted(reference_cases):
        reference = reference_cases[case_id].get("angle_degrees")
        prediction = prediction_cases[case_id].get("angle_degrees")
        if (reference is None) != (prediction is None):
            raise EvaluationInputError(
                f"case {case_id!r} must provide angle_degrees in both documents or neither"
            )
        if reference is None:
            continue
        if len(reference) != len(prediction):
            raise EvaluationInputError(
                f"case {case_id!r} has mismatched angle_degrees array lengths"
            )
        evaluated_cases += 1
        absolute_errors.extend(abs(left - right) for left, right in zip(reference, prediction))
    return {
        "evaluated_cases": evaluated_cases,
        "sample_count": len(absolute_errors),
        "mae_degrees": statistics.mean(absolute_errors) if absolute_errors else None,
    }


def _latency_metrics(prediction_cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    latencies = [
        event["latency_ms"]
        for case in prediction_cases.values()
        for event in case["events"]
        if "latency_ms" in event
    ]
    ordered = sorted(latencies)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else None
    return {
        "sample_count": len(latencies),
        "units": "milliseconds",
        "mean_ms": statistics.mean(latencies) if latencies else None,
        "median_ms": statistics.median(latencies) if latencies else None,
        "p95_ms_nearest_rank": p95,
        "measurement_note": (
            "Only supplied prediction-event latency_ms values are summarized; "
            "the evaluator does not time inference."
        ),
    }


def evaluate(
    references: Any,
    predictions: Any,
    *,
    tolerance_seconds: float = 0.5,
) -> dict[str, Any]:
    """Validate documents, compare annotations, and return a JSON-serializable report."""
    tolerance = _finite_number(tolerance_seconds, "tolerance_seconds", minimum=0)
    reference = _validate_document(references, "references")
    prediction = _validate_document(predictions, "predictions")
    if reference["dataset_kind"] != prediction["dataset_kind"]:
        raise EvaluationInputError("references and predictions dataset_kind must match")
    if reference["dataset_label"] != prediction["dataset_label"]:
        raise EvaluationInputError("references and predictions dataset_label must match")

    reference_ids = set(reference["cases"])
    prediction_ids = set(prediction["cases"])
    if reference_ids != prediction_ids:
        missing_predictions = sorted(reference_ids - prediction_ids)
        missing_references = sorted(prediction_ids - reference_ids)
        details = []
        if missing_predictions:
            details.append(f"missing predictions for case_id(s): {', '.join(missing_predictions)}")
        if missing_references:
            details.append(f"missing references for case_id(s): {', '.join(missing_references)}")
        raise EvaluationInputError("; ".join(details))

    overall, by_kind, by_case_and_kind = _event_groups(
        reference["cases"], prediction["cases"], tolerance,
    )
    synthetic = reference["dataset_kind"] == "synthetic_nonclinical"
    return {
        "schema_version": 1,
        "dataset": {
            "kind": reference["dataset_kind"],
            "label": reference["dataset_label"],
            "synthetic_nonclinical": synthetic,
        },
        "notice": (
            "Offline annotation metrics only. No media was read and no inference was run. "
            "Metrics do not establish clinical validity."
            + (
                " Synthetic nonclinical example; this is not model validation."
                if synthetic else ""
            )
        ),
        "event_tolerance_seconds_inclusive": tolerance,
        "event_detection": {
            "matching": "one-to-one within the same case_id and event kind",
            "overall": overall,
            "by_kind": by_kind,
            "by_case_and_kind": by_case_and_kind,
        },
        "transcription": _transcription_metrics(reference["cases"], prediction["cases"]),
        "angle_error": _angle_metrics(reference["cases"], prediction["cases"]),
        "prediction_latency": _latency_metrics(prediction["cases"]),
    }
