from __future__ import annotations

import re
from typing import Any


_ACCURACY_PATTERNS = (
    r"(?:accuracy|acc|precision|f1|score)\s*[:=]\s*(\d+(?:[.,]\d+)?)\s*%?",
    r"(\d+(?:[.,]\d+)?)\s*%\s*(?:accuracy|acc|precision|f1|score)",
)

_MODEL_PATTERNS = (
    r"(?:model|model_name)\s*[:=]\s*([A-Za-z0-9._\-/]+)",
    r"\b(llama[0-9.\-a-zA-Z]*)\b",
    r"\b(mistral[0-9.\-a-zA-Z]*)\b",
)


def normalize_accuracy(value: float) -> float:
    """Normalize an accuracy value to the [0, 1] range.

    Accepts either percentage form (e.g. 90.0) or decimal form (e.g. 0.9)
    and always returns a decimal. Values already in [0, 1] are returned as-is.

    Args:
        value: Accuracy as a percentage or decimal.

    Returns:
        Accuracy as a decimal in [0, 1].
    """
    if value > 1:
        return value / 100.0
    return value


def extract_accuracy(text: str | None) -> float | None:
    """Parse an accuracy value from a free-form text string.

    Tries a set of regex patterns that cover common formats such as
    "accuracy: 92.1", "acc=0.91", or "91% f1". Returns the first match
    found, normalized to the [0, 1] range via `normalize_accuracy`.

    Args:
        text: Any string that may contain an accuracy metric, e.g. an
            experiment name or description. Handles both period and comma
            as the decimal separator.

    Returns:
        Accuracy as a decimal in [0, 1], or None if no match is found.
    """
    if not text:
        return None

    for pattern in _ACCURACY_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            # Normalize European-style decimal commas before converting to float
            raw = match.group(1).replace(",", ".")
            return normalize_accuracy(float(raw))

    return None


def extract_model_name(name: str | None, description: str | None) -> str | None:
    """Infer a model name from an experiment's name and description.

    Searches the combined text for known model name patterns (e.g. llama,
    mistral) or an explicit "model=..." key. Falls back to returning the raw
    `name` argument if no pattern matches.

    Args:
        name: Experiment name, may contain a model identifier.
        description: Experiment description, may contain a model identifier.

    Returns:
        The extracted model name string, the raw `name` as a fallback, or
        None if both inputs are empty.
    """
    # Combine name and description into a single searchable string, skipping None values
    text = " ".join([x for x in (name, description) if x])
    if not text:
        return None

    for pattern in _MODEL_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    # No pattern matched — fall back to the raw name rather than returning nothing
    return name


def aggregate_run_summaries(run_reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate emissions and resource usage across a list of run reports.

    Sums the emissions, energy consumption, and duration for all runs belonging
    to a single experiment. Missing or null fields are treated as zero.

    Args:
        run_reports: List of run report dicts, each expected to contain
            "emissions", "energy_consumed", and "duration" keys.

    Returns:
        A dict with the following keys:
            - run_count: Total number of runs.
            - emissions_kg_co2e: Total CO2-equivalent emissions in kilograms.
            - energy_kwh: Total energy consumed in kilowatt-hours.
            - duration_seconds: Total wall-clock duration in seconds.
    """
    emissions = sum(float(item.get("emissions") or 0.0) for item in run_reports)
    energy_consumed = sum(
        float(item.get("energy_consumed") or 0.0) for item in run_reports
    )
    duration = sum(float(item.get("duration") or 0.0) for item in run_reports)
    return {
        "run_count": len(run_reports),
        "emissions_kg_co2e": emissions,
        "energy_kwh": energy_consumed,
        "duration_seconds": duration,
    }


def select_lowest_consumption_experiment(
    experiment_reports: list[dict[str, Any]],
    min_accuracy: float | None = None,
) -> dict[str, Any]:
    """Select the most carbon-efficient experiment that meets an accuracy threshold.

    Filters experiment reports by a minimum accuracy requirement (parsed from
    each experiment's name and description), then returns the one with the
    lowest CO2 emissions. Energy consumption and duration are used as
    tiebreakers in that order.

    Args:
        experiment_reports: List of experiment summary dicts. Each dict should
            contain "experiment_id", "name", "description", "emissions",
            "energy_consumed", and "duration" keys.
        min_accuracy: Optional minimum accuracy in either percentage (90.0) or
            decimal (0.9) form. Experiments whose accuracy cannot be parsed are
            excluded when a threshold is provided.

    Returns:
        A dict with the following keys:
            - selected: The chosen experiment dict, or None if no candidates.
            - min_accuracy: The normalized threshold that was applied.
            - candidate_count: Number of experiments that passed the filter.
            - message: Human-readable explanation, present only when no
              candidates were found.
    """
    # Normalize threshold upfront so all comparisons use the same [0, 1] scale
    normalized_threshold = (
        normalize_accuracy(min_accuracy) if min_accuracy is not None else None
    )

    candidates = []
    for report in experiment_reports:
        # Accuracy is parsed from free-form text rather than a dedicated field
        accuracy = extract_accuracy(
            f"{report.get('name', '')} {report.get('description', '')}"
        )
        emissions = float(report.get("emissions") or 0.0)
        candidate = {
            "experiment_id": report.get("experiment_id"),
            "name": report.get("name"),
            "description": report.get("description"),
            "model": extract_model_name(report.get("name"), report.get("description")),
            "accuracy": accuracy,
            "emissions_kg_co2e": emissions,
            "energy_kwh": float(report.get("energy_consumed") or 0.0),
            "duration_seconds": float(report.get("duration") or 0.0),
        }
        # Skip experiments that don't meet the accuracy bar; if no threshold is
        # set, all experiments are eligible regardless of parsed accuracy
        if normalized_threshold is None or (
            accuracy is not None and accuracy >= normalized_threshold
        ):
            candidates.append(candidate)

    if not candidates:
        return {
            "selected": None,
            "min_accuracy": normalized_threshold,
            "candidate_count": 0,
            "message": "No experiment matches the requested minimum accuracy.",
        }

    selected = min(
        candidates,
        key=lambda c: (
            c["emissions_kg_co2e"],
            c["energy_kwh"],
            c["duration_seconds"],
        ),
    )
    return {
        "selected": selected,
        "min_accuracy": normalized_threshold,
        "candidate_count": len(candidates),
    }