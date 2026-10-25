"""Coach-adjustable target ranges for TennisPose analysis.

All default values are DEMONSTRATION references, not validated coaching,
medical, or biomechanical standards. A coach edits the YAML file to replace
them with their own standards; the app always labels where each number came
from. All user-visible output is English-only, matching the mobile Live app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a declared dependency.
    yaml = None

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_TARGETS_PATH = PACKAGE_DIR / "default_targets.yaml"

DEMO_DISCLAIMER_EN = "Demonstration reference only, not coach-validated"


@dataclass(frozen=True)
class TargetRange:
    """One named angular target with its provenance label."""

    name: str
    minimum_deg: float
    maximum_deg: float
    source: str  # e.g. "demo" or "coach"


@dataclass(frozen=True)
class Targets:
    """All configured target ranges, keyed by action name.

    ``extras`` holds non-angle demo thresholds (e.g. groundstroke_extras)
    that a coach can also override.
    """

    ranges: dict[str, TargetRange]
    extras: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get(self, action: str) -> TargetRange | None:
        return self.ranges.get(action)


def _coerce_range(name: str, raw: Any) -> TargetRange:
    if not isinstance(raw, dict):
        raise ValueError(f"Target '{name}' must be a mapping")
    minimum = float(raw.get("min_deg", 0.0))
    maximum = float(raw.get("max_deg", 0.0))
    if minimum > maximum:
        raise ValueError(f"Target '{name}': min_deg cannot exceed max_deg")
    source = str(raw.get("source", "demo"))
    return TargetRange(name=name, minimum_deg=minimum, maximum_deg=maximum, source=source)


def load_targets(path: str | Path | None = None) -> Targets:
    """Load target ranges from YAML, falling back to the shipped defaults.

    ``path`` may point at a coach-edited file; when omitted, the packaged
    demonstration defaults are used. Top-level keys carrying min_deg/max_deg
    become angle ranges keyed by action name; other mappings are kept as
    extras. Raises ``ValueError`` on malformed files.
    """

    if yaml is None:
        raise ImportError("PyYAML is required to load target ranges (pip install pyyaml)")

    target_path = Path(path) if path is not None else DEFAULT_TARGETS_PATH
    if not target_path.is_file():
        raise FileNotFoundError(f"Target ranges file not found: {target_path}")

    with target_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    if not isinstance(raw, dict):
        raise ValueError("Target ranges file must contain a mapping of action names")

    ranges: dict[str, TargetRange] = {}
    extras: dict[str, dict[str, Any]] = {}
    for name, item in raw.items():
        if isinstance(item, dict) and ("min_deg" in item or "max_deg" in item):
            ranges[name] = _coerce_range(name, item)
        elif isinstance(item, dict):
            extras[name] = dict(item)
        else:
            raise ValueError(f"Target '{name}' must be a mapping")
    return Targets(ranges=ranges, extras=extras)


def disclaimer(source: str) -> str:
    """Return the English provenance label for a target range source."""

    if source == "coach":
        return "Coach-defined"
    return DEMO_DISCLAIMER_EN


def write_example_config(path: str | Path) -> Path:
    """Write a commented coach-editable example next to the shipped defaults."""

    example = """\
# Tennis360 target ranges
# All values below are DEMONSTRATION references (source: demo),
# not validated coaching/medical/biomechanical standards.
# Replace them with your own standards and set source to coach.
serve:
  min_deg: 80.0
  max_deg: 120.0
  source: demo
forehand:
  min_deg: 130.0
  max_deg: 170.0
  source: demo
forehand-slice:
  min_deg: 150.0
  max_deg: 175.0
  source: demo
backhand-one:
  min_deg: 140.0
  max_deg: 175.0
  source: demo
backhand-two:
  min_deg: 140.0
  max_deg: 175.0
  source: demo
backhand-slice:
  min_deg: 150.0
  max_deg: 175.0
  source: demo
overhead:
  min_deg: 150.0
  max_deg: 180.0
  source: demo
volley-forehand:
  min_deg: 90.0
  max_deg: 130.0
  source: demo
volley-backhand:
  min_deg: 90.0
  max_deg: 130.0
  source: demo
drop-shot:
  min_deg: 120.0
  max_deg: 160.0
  source: demo
half-volley:
  min_deg: 120.0
  max_deg: 165.0
  source: demo
lob:
  min_deg: 130.0
  max_deg: 170.0
  source: demo
groundstroke_extras:
  followthrough_min_rise: 0.2
  shoulder_turn_min_deg: 20.0
  contact_in_front_min: 0.15
  source: demo
stroke_extras:
  overhead_contact_height_min: 1.2
  overhead_lateral_offset_max: 0.5
  volley_backswing_max: 0.4
  drop_followthrough_max: 0.6
  halfvolley_followthrough_max: 0.6
  halfvolley_knee_bend_min: 0.05
  halfvolley_contact_height_max: 0.3
  slice_wrist_stability_max: 0.15
  lob_backswing_depth_max: 0.1
  lob_followthrough_min_rise: 0.5
  source: demo
"""
    destination = Path(path)
    destination.write_text(example, encoding="utf-8")
    return destination
