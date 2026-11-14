"""Command-line entry point for offline evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .metrics import EvaluationInputError, evaluate, load_document

_EXAMPLES = Path(__file__).parent / "examples"


def _write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare reference annotations with externally generated predictions. "
            "Reads local JSON only; does not load media or run model inference."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("evaluate", help="evaluate two annotation JSON files")
    run.add_argument("--references", type=Path, required=True, help="reference annotations JSON")
    run.add_argument("--predictions", type=Path, required=True, help="predictions JSON")
    run.add_argument(
        "--tolerance-seconds",
        type=float,
        default=0.5,
        help="inclusive timestamp tolerance for event matches (default: 0.5)",
    )
    run.add_argument("--output", type=Path, required=True, help="path for the JSON report")

    demo = commands.add_parser(
        "demo",
        help="evaluate the included synthetic, nonclinical example data",
    )
    demo.add_argument("--output", type=Path, required=True, help="path for the JSON report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "demo":
            references = load_document(_EXAMPLES / "references.json")
            predictions = load_document(_EXAMPLES / "predictions.json")
            tolerance = 0.5
        else:
            references = load_document(args.references)
            predictions = load_document(args.predictions)
            tolerance = args.tolerance_seconds

        report = evaluate(references, predictions, tolerance_seconds=tolerance)
        _write_report(report, args.output)
    except (EvaluationInputError, OSError, json.JSONDecodeError) as exc:
        print(f"evaluation: {exc}", file=sys.stderr)
        return 2

    print(f"Evaluation report written to {args.output}")
    if report["dataset"]["synthetic_nonclinical"]:
        print("NOTICE: synthetic nonclinical example only; this is not model validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
