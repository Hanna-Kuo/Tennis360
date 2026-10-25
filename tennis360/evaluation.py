"""Evidence-aware metrics for explicitly licensed offline teaching inputs.

Missing coach labels and measured angles remain missing. This module is not
called by the Streamlit upload path and does not calibrate a photo estimator.
"""

from __future__ import annotations

from math import isfinite
from statistics import mean, median
from typing import Sequence


def summarize_photo_results(rows: Sequence[dict]) -> dict:
    """Separate accepted coverage, phase errors, coach agreement and angle error.

    ``coach_verdict`` must be independently supplied, never inferred from player
    tier or the application's output. Green is evaluated as a proxy against
    that label; an elbow-range decision is not a full-form classifier.
    """
    accepted = preparation = preparation_accepted = unsuitable = false_accept = 0
    coach_total = coach_analyzed = coach_accepted = tp = fp = fn = tn = 0
    measured_total = wrong_arm = unknown_arm = 0
    errors: list[float] = []
    for row in rows:
        label, report = row["label"], row["report"]
        phase = label.get("preparation")
        if phase is not None and type(phase) is not bool:
            raise ValueError("preparation must be a bool or null")
        verdict = label.get("coach_verdict")
        if verdict not in (None, "correct", "incorrect"):
            raise ValueError("coach_verdict must be independently labelled correct/incorrect or null")
        analyzed = report["status"] == "analyzed"
        accepted += analyzed
        if phase is True:
            preparation += 1
            preparation_accepted += analyzed
        elif phase is False:
            unsuitable += 1
            false_accept += analyzed
        expected_arm = label.get("arm")
        if expected_arm not in (None, "left", "right"):
            raise ValueError("arm must be left/right or null")
        arm_matches = expected_arm is not None and expected_arm == report.get("arm")
        wrong_arm += bool(analyzed and expected_arm is not None and not arm_matches)
        unknown_arm += bool(analyzed and expected_arm is None)
        if verdict is not None:
            coach_total += 1
            if analyzed:
                coach_analyzed += 1
                if type(report.get("in_demo_range")) is not bool:
                    raise ValueError("analyzed reports must contain a boolean verdict")
            if analyzed and arm_matches:
                coach_accepted += 1
                positive = report["in_demo_range"] and arm_matches
                correct = verdict == "correct"
                tp += positive and correct
                fp += positive and not correct
                fn += not positive and correct
                tn += not positive and not correct
        truth = label.get("measured_angle_degrees")
        if truth is not None:
            if isinstance(truth, bool) or not isfinite(truth) or not 0 <= truth <= 180:
                raise ValueError("measured angle must be finite and within 0–180")
            if label.get("angle_convention") != "shoulder-elbow-wrist interior" or not label.get("angle_source"):
                raise ValueError("measured angles require an independent source and the interior-angle convention")
            measured_total += 1
            if analyzed and arm_matches:
                estimate = report.get("angle_degrees")
                if estimate is None or not isfinite(estimate):
                    raise ValueError("analyzed reports must contain a finite angle")
                errors.append(abs(estimate - truth))

    def ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    return {
        "photos": len(rows), "accepted": accepted,
        "accepted_coverage": ratio(accepted, len(rows)),
        "visually_labelled_preparation": preparation,
        "preparation_accepted": preparation_accepted,
        "preparation_coverage": ratio(preparation_accepted, preparation),
        "visually_labelled_unsuitable": unsuitable,
        "unsuitable_false_acceptances": false_accept,
        "unsuitable_false_acceptance_rate": ratio(false_accept, unsuitable),
        "accepted_wrong_arm": wrong_arm,
        "accepted_unknown_label_arm": unknown_arm,
        "coach_proxy": {
            "labelled": coach_total, "analyzed": coach_analyzed,
            "accepted_same_arm": coach_accepted,
            "refused": coach_total - coach_analyzed,
            "wrong_or_unknown_arm_excluded": coach_analyzed-coach_accepted,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": ratio(tp, tp + fp),
            "recall_among_accepted": ratio(tp, tp + fn),
            "agreement_among_accepted": ratio(tp + tn, coach_accepted),
            "scope": "elbow-range green proxy; not a trained full-form classifier",
        },
        "measured_3d": {
            "labelled": measured_total, "accepted_same_arm": len(errors),
            "mean_absolute_error_degrees": mean(errors) if errors else None,
            "median_absolute_error_degrees": median(errors) if errors else None,
            "maximum_absolute_error_degrees": max(errors) if errors else None,
        },
    }
