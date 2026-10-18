"""Pure, testable geometry, gating rules, and feedback thresholds.

This module deliberately imports nothing from MediaPipe or OpenCV so that every
decision the product makes can be unit tested without a model file or an image.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, hypot, isfinite, sqrt
from statistics import median
from typing import Literal, Sequence


Arm = Literal["left", "right"]

# --- Trophy-position feedback thresholds -------------------------------------
# Configurable demonstration interval. Neither the reference photos nor
# repeat-pass agreement establish a calibrated error bound or coaching standard.
DEFAULT_TROPHY_MINIMUM = 80.0
DEFAULT_TROPHY_MAXIMUM = 120.0

# MediaPipe visibility below this is treated as "the model is guessing".
# 0.55 was previously used and rejected usable dim photos; 0.35 still rejects
# a fully hidden arm, which reports visibility near 0.01.
DEFAULT_MINIMUM_VISIBILITY = 0.35

# Full observed range between test-time-augmentation passes, in degrees.
# A tight majority cannot hide an otherwise reliable conflicting reading.
STABLE_SPREAD_DEGREES = 8.0
MAX_SPREAD_DEGREES = 20.0
MINIMUM_VALID_PASSES = 3

# Trophy-position gate, expressed in body-scale units where 1.0 is the distance
# from the shoulder line to the hip line. Positive means "above the shoulder".
MIN_WRIST_RISE = -0.25
MIN_ELBOW_RISE = -0.45
MAX_WRIST_RISE = 0.65
MAX_ELBOW_RISE = 0.30
MIN_FOREARM_RISE = 0.10
MIN_TOSS_WRIST_RISE = 0.25

Confidence = Literal["high", "moderate", "low"]


@dataclass(frozen=True)
class Point:
    """One normalized image-space point with detector visibility.

    ``y`` grows downward, matching image coordinates.
    """

    x: float
    y: float
    visibility: float = 1.0
    presence: float = 1.0


@dataclass(frozen=True)
class Point3:
    """One metric world-space point in meters, relative to the hip midpoint."""

    x: float
    y: float
    z: float
    visibility: float = 1.0
    presence: float = 1.0


@dataclass(frozen=True)
class ArmGeometry:
    """Scale-normalized position of one arm relative to its own shoulder."""

    wrist_rise: float
    elbow_rise: float


@dataclass(frozen=True)
class AngleResult:
    """A pooled elbow-angle measurement and its demonstration feedback.

    Repeat agreement is not a calibrated accuracy probability. Bounds are the
    observed minimum and maximum, not a symmetric confidence interval.
    """

    degrees: float
    spread_degrees: float
    consensus_degrees: float
    confidence: Confidence
    in_demo_range: bool
    sample_count: int
    minimum_degrees: float
    maximum_degrees: float
    verdict_consistent: bool


def has_reliable_point(point: Point, minimum_visibility: float) -> bool:
    """Return whether a point is finite and meets the visibility threshold."""

    return (
        isfinite(point.x)
        and isfinite(point.y)
        and isfinite(point.visibility)
        and isfinite(point.presence)
        and 0 <= point.x <= 1
        and 0 <= point.y <= 1
        and minimum_visibility <= point.visibility <= 1
        and 0.5 <= point.presence <= 1
    )


def calculate_elbow_angle(
    shoulder: Point, elbow: Point, wrist: Point, *, width: int = 1, height: int = 1
) -> float | None:
    """Return the projected shoulder-elbow-wrist angle, or ``None`` if degenerate.

    This is the flat image-plane angle. It is kept for transparency and testing
    only: an arm pointing toward or away from the camera is foreshortened, so
    this value can understate a real bend by 50 degrees or more. Product
    decisions use :func:`calculate_elbow_angle_3d` instead.
    """

    if not all(
        isfinite(value)
        for value in (shoulder.x, shoulder.y, elbow.x, elbow.y, wrist.x, wrist.y)
    ):
        return None

    return _angle_between(
        ((shoulder.x - elbow.x) * width, (shoulder.y - elbow.y) * height),
        ((wrist.x - elbow.x) * width, (wrist.y - elbow.y) * height),
    )


def calculate_elbow_angle_3d(
    shoulder: Point3,
    elbow: Point3,
    wrist: Point3,
) -> float | None:
    """Return the interior angle from estimated world landmarks.

    The depth is inferred from one image, not measured by a depth sensor.
    """

    values = (
        shoulder.x, shoulder.y, shoulder.z,
        elbow.x, elbow.y, elbow.z,
        wrist.x, wrist.y, wrist.z,
    )
    if not all(isfinite(value) for value in values):
        return None

    return _angle_between(
        (shoulder.x - elbow.x, shoulder.y - elbow.y, shoulder.z - elbow.z),
        (wrist.x - elbow.x, wrist.y - elbow.y, wrist.z - elbow.z),
    )


def _angle_between(first: Sequence[float], second: Sequence[float]) -> float | None:
    """Return the angle in degrees between two vectors of equal dimension."""

    first_length = hypot(*first)
    second_length = hypot(*second)
    if not isfinite(first_length) or not isfinite(second_length):
        return None
    if first_length < 1e-9 or second_length < 1e-9:
        return None

    cosine = max(-1.0, min(1.0, sum(
        (a / first_length) * (b / second_length) for a, b in zip(first, second)
    )))
    angle = degrees(acos(cosine))
    return angle if isfinite(angle) else None


def body_scale(
    left_shoulder: Point,
    right_shoulder: Point,
    left_hip: Point,
    right_hip: Point,
    width: int,
    height: int,
) -> float | None:
    """Return a pixel length that one torso spans, used to normalize positions.

    Falls back to shoulder width when the hips are missing or implausible, so a
    cropped upper-body photo still yields a usable scale. Returns ``None`` when
    the person is too small to measure.
    """

    if not all(has_reliable_point(point, 0.2) for point in (left_shoulder, right_shoulder)):
        return None

    def pixel(point: Point) -> tuple[float, float]:
        return (point.x * width, point.y * height)

    def distance(first: tuple[float, float], second: tuple[float, float]) -> float:
        return sqrt((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2)

    shoulder_mid = _midpoint(pixel(left_shoulder), pixel(right_shoulder))
    hip_mid = _midpoint(pixel(left_hip), pixel(right_hip))
    torso = distance(shoulder_mid, hip_mid)
    shoulders = distance(pixel(left_shoulder), pixel(right_shoulder))

    hips_usable = (
        has_reliable_point(left_hip, 0.2)
        and has_reliable_point(right_hip, 0.2)
        and isfinite(torso)
    )
    scale = max(torso if hips_usable else 0.0, shoulders)
    return scale if isfinite(scale) and scale >= 20.0 else None


def _midpoint(first: tuple[float, float], second: tuple[float, float]) -> tuple[float, float]:
    return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)


def arm_geometry(
    shoulder: Point,
    elbow: Point,
    wrist: Point,
    scale: float,
    height: int,
    *,
    width: int = 1,
    up: tuple[float, float] = (0.0, -1.0),
) -> ArmGeometry:
    """Return how far the elbow and wrist sit above the shoulder, in body scales.

    Positive values mean "above the shoulder" because image ``y`` grows downward.
    """

    return ArmGeometry(
        wrist_rise=((wrist.x - shoulder.x) * width * up[0]
                    + (wrist.y - shoulder.y) * height * up[1]) / scale,
        elbow_rise=((elbow.x - shoulder.x) * width * up[0]
                    + (elbow.y - shoulder.y) * height * up[1]) / scale,
    )


def torso_up_axis(
    landmarks: Sequence[Point], width: int, height: int
) -> tuple[float, float]:
    """Normalize camera roll/torso lean; use image-up when hips are unavailable."""

    if not all(has_reliable_point(landmarks[i], 0.2) for i in (11, 12, 23, 24)):
        return (0.0, -1.0)
    dx = (landmarks[11].x + landmarks[12].x - landmarks[23].x - landmarks[24].x) * width / 2
    dy = (landmarks[11].y + landmarks[12].y - landmarks[23].y - landmarks[24].y) * height / 2
    length = hypot(dx, dy)
    return (dx / length, dy / length) if length >= 20 else (0.0, -1.0)


def is_in_preparation_position(geometry: ArmGeometry) -> bool:
    """Return whether one arm is raised into a serve preparation position.

    At the trophy position the hitting wrist sits near or just above shoulder
    height and the elbow is at most a little below it. A hand resting at the
    waist, or an arm that has already swung down after contact, fails this test.
    """

    return (
        isfinite(geometry.wrist_rise)
        and isfinite(geometry.elbow_rise)
        and MIN_WRIST_RISE <= geometry.wrist_rise <= MAX_WRIST_RISE
        and MIN_ELBOW_RISE <= geometry.elbow_rise <= MAX_ELBOW_RISE
        and geometry.wrist_rise - geometry.elbow_rise >= MIN_FOREARM_RISE
    )


def classify_confidence(
    consensus_degrees: float,
    *,
    stable_spread: float = STABLE_SPREAD_DEGREES,
    maximum_spread: float = MAX_SPREAD_DEGREES,
) -> Confidence:
    """Grade repeat agreement using the full observed spread."""

    if consensus_degrees <= stable_spread:
        return "high"
    if consensus_degrees <= maximum_spread:
        return "moderate"
    return "low"


def pool_angles(
    angles: Sequence[float],
    demo_minimum: float,
    demo_maximum: float,
    *,
    stable_spread: float = STABLE_SPREAD_DEGREES,
    maximum_spread: float = MAX_SPREAD_DEGREES,
) -> AngleResult | None:
    """Combine repeated measurements of one elbow into a single graded result.

    The median is the point estimate; the full spread grades repeat agreement.
    At least three valid readings are required. A target boundary crossing is
    reported separately so the pipeline can withhold a red/green verdict.
    """

    usable = [angle for angle in angles if isfinite(angle) and 0 <= angle <= 180]
    if not usable:
        return None

    pooled = float(median(usable))
    spread = max(usable) - min(usable)
    consensus = float(median([abs(angle - pooled) for angle in usable]))

    confidence = classify_confidence(
        spread, stable_spread=stable_spread, maximum_spread=maximum_spread
    )
    if len(usable) < MINIMUM_VALID_PASSES:
        confidence = "low"

    def category(angle: float) -> str:
        return "below" if angle < demo_minimum else "above" if angle > demo_maximum else "in"

    return AngleResult(
        degrees=pooled,
        spread_degrees=spread,
        consensus_degrees=consensus,
        confidence=confidence,
        in_demo_range=demo_minimum <= pooled <= demo_maximum,
        sample_count=len(usable),
        minimum_degrees=min(usable),
        maximum_degrees=max(usable),
        verdict_consistent=len({category(angle) for angle in usable}) == 1,
    )


def make_angle_result(
    angle: float,
    demo_minimum: float,
    demo_maximum: float,
) -> AngleResult:
    """Apply the inclusive demonstration range to one already valid angle."""

    return AngleResult(
        degrees=angle,
        spread_degrees=0.0,
        consensus_degrees=0.0,
        confidence="low",
        in_demo_range=demo_minimum <= angle <= demo_maximum,
        sample_count=1,
        minimum_degrees=angle,
        maximum_degrees=angle,
        verdict_consistent=True,
    )
