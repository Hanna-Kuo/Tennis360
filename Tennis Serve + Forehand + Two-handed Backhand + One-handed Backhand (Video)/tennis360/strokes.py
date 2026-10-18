"""Stroke analysis: forehand and backhands (one-handed, two-handed).

Pure geometry and trajectory heuristics — this module imports nothing from
MediaPipe or OpenCV, so every decision is unit testable without a model file.

Key-moment detection (backswing / contact / follow-through) is HEURISTIC and
labeled as such throughout: the pipeline assumes a side-ish view of a single
swing and cannot certify the exact contact frame from monocular landmarks.

The key-moment model mirrors the mobile Live app so both versions analyze
the same checkpoints for each stroke (two-version parity).

All default thresholds are DEMONSTRATION references (source: demo), not
validated coaching, medical, or biomechanical standards. A coach should
replace them via ``default_targets.yaml`` and set source to "coach".
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from tennis360.config import Targets

# --- demonstration thresholds -------------------------------------------------
# Kept here as code-level fallbacks; the YAML file (groundstroke_extras) is the
# coach-editable surface and overrides these when present.
DEMO_FOLLOWTHROUGH_MIN_RISE = 0.2  # body scales; wrist above shoulder at finish
DEMO_SHOULDER_TURN_MIN_DEG = 20.0  # 2D proxy amplitude across the swing
DEMO_CONTACT_IN_FRONT_MIN = 0.15  # body scales ahead of the shoulder line
GROUNDSTROKE_ACTIONS = ("forehand", "backhand-one", "backhand-two")
# Every video-analyzable swing action. The CLI dispatches on this tuple.
SWING_ACTIONS = GROUNDSTROKE_ACTIONS


@dataclass(frozen=True)
class SwingSample:
    """One sampled video frame of a groundstroke swing."""

    index: int  # original video frame number
    time_s: float
    wrist_x: float  # normalized image x of the hitting wrist
    wrist_rise: float  # body scales, positive = above the shoulder
    elbow_angle: float | None  # hitting-arm 3D shoulder-elbow-wrist angle
    second_elbow_angle: float | None  # other arm (two-handed backhand only)
    shoulder_mid_x: float  # normalized image x of the shoulder midpoint
    shoulder_angle_deg: float | None  # shoulder segment vs horizontal, 2D proxy
    width_px: float
    scale_px: float  # pixels per body scale
    shoulder_mid_y: float = 0.5  # normalized image y of shoulder midpoint


@dataclass(frozen=True)
class KeyMoments:
    """Sample positions of the three analyzed instants.

    ``forward_sign`` is +1/-1: the image-x direction the wrist travels during
    the forward swing. Everything here is heuristic, never certified.
    """

    backswing: int
    contact: int
    followthrough: int
    forward_sign: float
    heuristic: bool = True


@dataclass
class StrokeMetrics:
    """Measured values at the key moments of one swing."""

    contact_elbow_deg: float | None
    contact_elbow_in_range: bool | None
    contact_in_front: float | None  # body scales; positive = in front of body
    followthrough_rise: float | None  # body scales
    shoulder_turn_deg: float | None  # amplitude across the swing, 2D proxy
    second_elbow_deg: float | None  # two-handed backhand only
    # Extended measurements (None when not applicable).
    contact_height: float | None = None  # wrist_rise at contact, body scales
    backswing_compactness: float | None = None  # backward wrist travel, body scales
    followthrough_length: float | None = None  # wrist travel contact->finish, body scales
    knee_bend: float | None = None  # shoulder drop, normalized image units, 2D proxy
    wrist_stability: float | None = None  # std dev of wrist rise, body scales
    push_forward: bool | None = None  # wrist keeps moving forward after contact
    backswing_depth: float | None = None  # wrist_rise at backswing, body scales;
    # lower = deeper take-back


def _smooth(values: list[float], window: int = 3) -> list[float]:
    """Centered moving average; edges use the available neighbors."""

    half = window // 2
    smoothed = []
    for i in range(len(values)):
        chunk = values[max(0, i - half) : i + half + 1]
        smoothed.append(sum(chunk) / len(chunk))
    return smoothed


def find_key_moments(samples: list[SwingSample]) -> KeyMoments | None:
    """Locate backswing, contact, and follow-through from the wrist path.

    Heuristic: contact is the sample just after the fastest wrist motion in
    image-x, backswing is the farthest-back wrist position before contact, and
    follow-through is the highest wrist after contact. Returns ``None`` when
    the series is too short or shows no clear swing.
    """

    if len(samples) < 3:
        return None
    xs = _smooth([s.wrist_x for s in samples])
    velocities = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    peak = max(range(len(velocities)), key=lambda i: abs(velocities[i]))
    if abs(velocities[peak]) < 1e-9:
        return None
    forward_sign = 1.0 if velocities[peak] > 0 else -1.0
    contact = min(peak + 1, len(samples) - 1)

    # Farthest wrist position opposite the swing direction, before contact.
    backswing = min(
        range(contact + 1), key=lambda i: xs[i] * forward_sign
    )
    if backswing >= contact:
        return None

    later = range(contact, len(samples))
    followthrough = max(later, key=lambda i: samples[i].wrist_rise)
    return KeyMoments(
        backswing=backswing,
        contact=contact,
        followthrough=followthrough,
        forward_sign=forward_sign,
    )



def _extra(
    targets: Targets | None, group: str, key: str, fallback: float
) -> float:
    """Read a coach-overridable demo threshold, falling back to the constant."""

    try:
        extras = (targets.extras if targets is not None else {}) or {}
        values = extras.get(group, {}) or {}
        return float(values.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def compute_metrics(
    samples: list[SwingSample], moments: KeyMoments
) -> StrokeMetrics:
    """Measure the graded quantities at the detected key moments."""

    contact_sample = samples[moments.contact]
    window = samples[moments.backswing : moments.followthrough + 1]
    turns = [
        s.shoulder_angle_deg
        for s in window
        if s.shoulder_angle_deg is not None and isfinite(s.shoulder_angle_deg)
    ]

    in_front = None
    if contact_sample.scale_px > 0:
        in_front = (
            (contact_sample.wrist_x - contact_sample.shoulder_mid_x)
            * contact_sample.width_px
            / contact_sample.scale_px
            * moments.forward_sign
        )

    # Extended measurements, all heuristic and labeled as such.
    seg = samples[moments.backswing : moments.contact + 1]
    ft_sample = samples[moments.followthrough]
    contact_height = contact_sample.wrist_rise
    backswing_compactness = None
    approach = samples[0 : moments.contact + 1]
    if len(approach) >= 2 and contact_sample.scale_px > 0:
        # Backward wrist travel measured from the ready position (first
        # sample), in body scales.
        xs_ready = [s.wrist_x for s in approach]
        backward = max(
            (xs_ready[0] - x) * moments.forward_sign for x in xs_ready
        )
        backswing_compactness = (
            backward * contact_sample.width_px / contact_sample.scale_px
        )
    followthrough_length = None
    if contact_sample.scale_px > 0:
        followthrough_length = (
            abs(ft_sample.wrist_x - contact_sample.wrist_x)
            * contact_sample.width_px
            / contact_sample.scale_px
        )
    shoulder_ys = [s.shoulder_mid_y for s in window]
    knee_bend = (
        max(shoulder_ys) - samples[moments.backswing].shoulder_mid_y
        if shoulder_ys
        else None
    )
    wrist_stability = None
    rises = [s.wrist_rise for s in seg]
    if len(rises) >= 2:
        mean = sum(rises) / len(rises)
        wrist_stability = (
            sum((r - mean) ** 2 for r in rises) / len(rises)
        ) ** 0.5
    push_forward = (
        (ft_sample.wrist_x - contact_sample.wrist_x) * moments.forward_sign > 0
    )
    backswing_depth = samples[moments.backswing].wrist_rise

    return StrokeMetrics(
        contact_elbow_deg=contact_sample.elbow_angle,
        contact_elbow_in_range=None,  # filled in by grade_stroke()
        contact_in_front=in_front,
        followthrough_rise=samples[moments.followthrough].wrist_rise,
        shoulder_turn_deg=(max(turns) - min(turns)) if len(turns) >= 2 else None,
        second_elbow_deg=contact_sample.second_elbow_angle,
        contact_height=contact_height,
        backswing_compactness=backswing_compactness,
        followthrough_length=followthrough_length,
        knee_bend=knee_bend,
        wrist_stability=wrist_stability,
        push_forward=push_forward,
        backswing_depth=backswing_depth,
    )


def _elbow_advice(
    angle: float | None,
    minimum: float,
    maximum: float,
    arm_label: str,
) -> list[str]:
    """English adjustment advice for one measured elbow angle (demo range)."""

    if angle is None or not isfinite(angle):
        return ["Elbow angle could not be measured at contact — check camera angle."]
    if angle < minimum:
        return [
            f"Elbow over-bent at contact ({angle:.0f}° on the {arm_label}) — "
            f"extend the arm more through the hitting zone. "
            f"Demo range {minimum:.0f}–{maximum:.0f}°."
        ]
    if angle > maximum:
        return [
            f"Elbow over-extended at contact ({angle:.0f}° on the {arm_label}) — "
            f"keep a slight bend at contact for control. "
            f"Demo range {minimum:.0f}–{maximum:.0f}°."
        ]
    return [
        f"Elbow angle at contact ({angle:.0f}° on the {arm_label}) is inside "
        f"the demo range ({minimum:.0f}–{maximum:.0f}°)."
    ]


def suggest_forehand(
    metrics: StrokeMetrics, targets: Targets | None
) -> list[str]:
    """Adjustment advice for a right-hand forehand (demo thresholds)."""

    advice: list[str] = []
    target = targets.get("forehand") if targets is not None else None
    minimum = target.minimum_deg if target else 130.0
    maximum = target.maximum_deg if target else 170.0
    advice.extend(_elbow_advice(metrics.contact_elbow_deg, minimum, maximum, "hitting arm"))

    in_front_min = _extra(targets, "groundstroke_extras", "contact_in_front_min", DEMO_CONTACT_IN_FRONT_MIN)
    if metrics.contact_in_front is not None and metrics.contact_in_front < in_front_min:
        advice.append(
            "Contact point is late — meet the ball further in front of the body."
        )

    rise_min = _extra(targets, "groundstroke_extras", "followthrough_min_rise", DEMO_FOLLOWTHROUGH_MIN_RISE)
    if metrics.followthrough_rise is not None and metrics.followthrough_rise < rise_min:
        advice.append(
            "Low finish — complete the follow-through higher, over the shoulder."
        )
    return advice


def suggest_backhand_one(
    metrics: StrokeMetrics, targets: Targets | None
) -> list[str]:
    """Adjustment advice for a one-handed backhand (demo thresholds)."""

    advice: list[str] = []
    target = targets.get("backhand-one") if targets is not None else None
    minimum = target.minimum_deg if target else 140.0
    maximum = target.maximum_deg if target else 175.0
    advice.extend(_elbow_advice(metrics.contact_elbow_deg, minimum, maximum, "hitting arm"))

    turn_min = _extra(targets, "groundstroke_extras", "shoulder_turn_min_deg", DEMO_SHOULDER_TURN_MIN_DEG)
    if metrics.shoulder_turn_deg is not None and metrics.shoulder_turn_deg < turn_min:
        advice.append(
            "Limited shoulder turn — rotate the shoulders more during the backswing. "
            "(2D proxy measurement.)"
        )

    rise_min = _extra(targets, "groundstroke_extras", "followthrough_min_rise", DEMO_FOLLOWTHROUGH_MIN_RISE)
    if metrics.followthrough_rise is not None and metrics.followthrough_rise < rise_min:
        advice.append("Low finish — extend the follow-through higher.")
    return advice


def suggest_backhand_two(
    metrics: StrokeMetrics, targets: Targets | None
) -> list[str]:
    """Adjustment advice for a two-handed backhand (demo thresholds)."""

    advice: list[str] = []
    target = targets.get("backhand-two") if targets is not None else None
    minimum = target.minimum_deg if target else 140.0
    maximum = target.maximum_deg if target else 175.0
    advice.extend(_elbow_advice(metrics.contact_elbow_deg, minimum, maximum, "hitting arm"))
    if metrics.second_elbow_deg is not None:
        advice.extend(
            _elbow_advice(metrics.second_elbow_deg, minimum, maximum, "support arm")
        )

    turn_min = _extra(targets, "groundstroke_extras", "shoulder_turn_min_deg", DEMO_SHOULDER_TURN_MIN_DEG)
    if metrics.shoulder_turn_deg is not None and metrics.shoulder_turn_deg < turn_min:
        advice.append(
            "Limited body rotation — turn the torso more fully into the shot. "
            "(2D proxy measurement.)"
        )

    in_front_min = _extra(targets, "groundstroke_extras", "contact_in_front_min", DEMO_CONTACT_IN_FRONT_MIN)
    if metrics.contact_in_front is not None and metrics.contact_in_front < in_front_min:
        advice.append(
            "Contact point is late — meet the ball further in front of the body."
        )
    return advice


_SUGGESTIONS = {
    "forehand": suggest_forehand,
    "backhand-one": suggest_backhand_one,
    "backhand-two": suggest_backhand_two,
}




def analyze_swing(
    action: str,
    samples: list[SwingSample],
    targets: Targets | None = None,
) -> tuple[KeyMoments | None, StrokeMetrics | None, list[str]]:
    """Run the full swing pipeline on sampled frames.

    Every swing action uses the backswing / contact / follow-through model.

    Returns (key moments, metrics, English suggestions). Moments and metrics
    are ``None`` when no clear swing is found; suggestions then explain why.
    """

    if action not in _SUGGESTIONS:
        raise ValueError(f"Unknown swing action: {action}")
    finder = find_key_moments
    moments = finder(samples)
    if moments is None:
        return None, None, [
            "No clear swing found in this clip — the wrist path shows no "
            "distinct swing motion. Check the camera angle."
        ]
    metrics = compute_metrics(samples, moments)
    target = targets.get(action) if targets is not None else None
    if target is not None and metrics.contact_elbow_deg is not None:
        metrics.contact_elbow_in_range = (
            target.minimum_deg <= metrics.contact_elbow_deg <= target.maximum_deg
        )
    suggestions = _SUGGESTIONS[action](metrics, targets)
    return moments, metrics, suggestions
