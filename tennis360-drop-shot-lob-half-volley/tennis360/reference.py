"""Reference-motion comparison interface.

Compares a measured result against a user-supplied reference file (JSON).
No professional-player data is bundled: the user must provide their own
reference numbers (for example from their coach), and every comparison labels
the reference source. This module only defines the file format and the math;
it never invents reference values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReferenceEntry:
    """One reference checkpoint supplied by the user/coach."""

    action: str
    metric: str  # e.g. "elbow_angle_deg"
    value: float
    source: str  # free text: who measured it, e.g. "coach Wang, 2026-10"
    note: str = ""


@dataclass(frozen=True)
class Comparison:
    """Measured value vs reference value for one metric."""

    action: str
    metric: str
    measured: float
    reference: float
    delta: float
    reference_source: str


def load_reference(path: str | Path) -> list[ReferenceEntry]:
    """Load user-supplied reference checkpoints from a JSON file.

    Expected format::

        {
          "entries": [
            {"action": "serve", "metric": "elbow_angle_deg",
             "value": 95.0, "source": "coach, Oct 2026", "note": ""}
          ]
        }
    """

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = raw.get("entries", []) if isinstance(raw, dict) else []
    loaded: list[ReferenceEntry] = []
    for item in entries:
        loaded.append(
            ReferenceEntry(
                action=str(item["action"]),
                metric=str(item["metric"]),
                value=float(item["value"]),
                source=str(item.get("source", "user-supplied")),
                note=str(item.get("note", "")),
            )
        )
    return loaded


def compare(
    measured: dict[str, float], references: list[ReferenceEntry], action: str
) -> list[Comparison]:
    """Compare measured metrics against references for one action."""

    results: list[Comparison] = []
    for entry in references:
        if entry.action != action or entry.metric not in measured:
            continue
        value = measured[entry.metric]
        results.append(
            Comparison(
                action=action,
                metric=entry.metric,
                measured=value,
                reference=entry.value,
                delta=value - entry.value,
                reference_source=entry.source,
            )
        )
    return results


def write_template(path: str | Path) -> Path:
    """Write an empty, clearly-labeled reference template for the user to fill."""

    template = {
        "_comment": (
            "TEMPLATE ONLY - fill in your own reference data. "
            "No professional-player data is included. "
            "Fill in values measured by your coach; every comparison will cite 'source'."
        ),
        "entries": [
            {
                "action": "serve",
                "metric": "elbow_angle_deg",
                "value": 0.0,
                "source": "fill in the source, e.g. coach-measured 2026-10",
                "note": "trophy pose elbow angle reference",
            }
        ],
    }
    destination = Path(path)
    destination.write_text(
        json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return destination
