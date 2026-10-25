"""Local MediaPipe pose inference, arm selection, and annotation for one photo.

The pipeline is deliberately explicit so every number shown to a user can be
traced back to a landmark:

1. run the pose model over a few cheap variants of the same photo;
2. reject arms the model could not actually see;
3. reject photos that are not a serve preparation at all;
4. pool the surviving 3D elbow angles into one median with a spread; and
5. only then apply the configurable green/red demonstration range.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Sequence

import cv2
import mediapipe as mp
import numpy as np

from tennis360.annotate import (
    AMBER,
    GREEN,
    RED,
    draw_banner,
    draw_measured_arm,
    draw_skeleton,
)
from tennis360.pose_math import (
    DEFAULT_MINIMUM_VISIBILITY,
    DEFAULT_TROPHY_MAXIMUM,
    DEFAULT_TROPHY_MINIMUM,
    AngleResult,
    Arm,
    ArmGeometry,
    Point,
    Point3,
    arm_geometry,
    body_scale,
    calculate_elbow_angle,
    calculate_elbow_angle_3d,
    has_reliable_point,
    is_in_preparation_position,
    MIN_TOSS_WRIST_RISE,
    pool_angles,
    torso_up_axis,
)


DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent.parent / "models" / "pose_landmarker_heavy.task"
)

# Kept as aliases so existing callers and docs that referenced the demo range
# continue to work after the trophy-position rename.
DEFAULT_DEMO_MINIMUM = DEFAULT_TROPHY_MINIMUM
DEFAULT_DEMO_MAXIMUM = DEFAULT_TROPHY_MAXIMUM

LEFT_ARM_INDICES = (11, 13, 15)
RIGHT_ARM_INDICES = (12, 14, 16)
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24

ArmChoice = Literal["auto", "left", "right"]
Status = Literal["analyzed", "cannot_analyze"]


class ModelFileMissingError(FileNotFoundError):
    """Raised when the local MediaPipe model has not been downloaded."""


@dataclass(frozen=True)
class ArmObservation:
    """Everything measured about one arm in the primary detection pass."""

    arm: Arm
    shoulder: Point
    elbow: Point
    wrist: Point
    geometry: ArmGeometry
    angle_3d: float | None
    angle_2d: float | None
    minimum_visibility: float
    reliable: bool
    in_preparation: bool


@dataclass(frozen=True)
class AnalysisReport:
    """The explainable result shown by the Streamlit interface."""

    status: Status
    arm: Arm | None
    angle_degrees: float | None
    in_demo_range: bool | None
    message: str
    confidence: str | None = None
    spread_degrees: float | None = None
    sample_count: int = 0
    projected_angle_degrees: float | None = None
    arm_was_detected: bool = False
    reason_code: str = ""
    minimum_angle_degrees: float | None = None
    maximum_angle_degrees: float | None = None
    attempted_passes: int = 0
    focused_on_player: bool = False


_detector_lock = threading.Lock()
_detector_cache: dict[str, object] = {}


def get_detector(model_path: Path = DEFAULT_MODEL_PATH) -> object:
    """Return a process-wide PoseLandmarker, loading the model at most once.

    Building the landmarker costs roughly half a second while a detection costs
    about thirty milliseconds, so caching it dominates perceived speed.
    """

    if not model_path.is_file():
        raise ModelFileMissingError(
            f"Local MediaPipe model not found at {model_path}. "
            "Follow the README download step before analyzing a photo."
        )

    key = str(model_path)
    with _detector_lock:
        detector = _detector_cache.get(key)
        if detector is None:
            vision = mp.tasks.vision
            options = vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(
                    model_asset_path=key,
                    delegate=mp.tasks.BaseOptions.Delegate.CPU,
                ),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            detector = vision.PoseLandmarker.create_from_options(options)
            _detector_cache[key] = detector
        return detector


def analyze_rgb_image(
    image_rgb: np.ndarray,
    arm: ArmChoice = "auto",
    *,
    minimum_visibility: float = DEFAULT_MINIMUM_VISIBILITY,
    demo_minimum: float = DEFAULT_TROPHY_MINIMUM,
    demo_maximum: float = DEFAULT_TROPHY_MAXIMUM,
    model_path: Path = DEFAULT_MODEL_PATH,
    stability_passes: bool = True,
    focus_player: bool = True,
) -> tuple[np.ndarray, AnalysisReport]:
    """Analyze one RGB photo locally and return an RGB annotation and report.

    ``arm`` may be ``"auto"`` to infer the racket arm, or an explicit side. An
    explicit side overrides arm identification, never reliability or phase gates.

    Photo bytes, landmarks, and the result stay in process memory for this call.
    """

    if not 0 <= minimum_visibility <= 1:
        raise ValueError("minimum_visibility must be between 0 and 1")
    if not (0 <= demo_minimum <= demo_maximum <= 180):
        raise ValueError("demo range must be finite, ordered, and within 0 to 180")
    if arm not in ("auto", "left", "right"):
        raise ValueError("arm must be 'auto', 'left', or 'right'")
    if image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise ValueError("image_rgb must be a three-channel RGB image")

    image_rgb = np.ascontiguousarray(image_rgb)
    canvas = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    detector = get_detector(model_path)

    focused = False

    def _refuse(canvas, selected_arm, message, reason_code, *, hint=""):
        return _cannot_analyze(canvas, selected_arm, message, reason_code,
                               hint=hint, focused_on_player=focused)

    primary = _detect(detector, image_rgb)
    if primary is None:
        return _refuse(
            canvas,
            None,
            "No person was detected in this photo.",
            "no_pose",
            hint="Use a photo where one whole player is clearly visible.",
        )

    landmarks, world_landmarks = primary
    if len(landmarks) != 33 or len(world_landmarks) != 33:
        return _refuse(canvas, None, "The detector returned incomplete landmarks.",
                               "invalid_landmarks", hint="Try another clear photo.")
    box = _player_focus_box(landmarks) if focus_player else None
    height, width = image_rgb.shape[:2]
    if box is not None:
        pixels = _focus_pixels(box, width, height)
        if (pixels[2]-pixels[0] < 64 or pixels[3]-pixels[1] < 64 or
                body_scale(*(landmarks[i] for i in (11, 12, 23, 24)), width, height) is None):
            box = None
    if box is not None:
        x0, y0, x1, y1 = _focus_pixels(box, width, height)
        crop = np.ascontiguousarray(image_rgb[y0:y1, x0:x1])
        detection = _detect(detector, crop)
        if detection is None or len(detection[0]) != 33 or len(detection[1]) != 33:
            return _refuse(canvas, None, "The focused player could not be measured.",
                                   "focus_lost", hint="Try a closer photo showing both arms.")
        transform = np.array([[1., 0, -x0], [0, 1., -y0]])
        restored = _restore_landmarks(detection[0], transform, (x1-x0, y1-y0),
                                      (width, height), False)
        if not _same_torso(landmarks, restored, width, height):
            return _refuse(canvas, None, "The focus changed the detected player.",
                                   "focus_lost", hint="Use a photo containing one clear player.")
        image_rgb = crop
        canvas = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
        landmarks, world_landmarks = detection
        focused = True
    draw_skeleton(canvas, landmarks)

    height, width = image_rgb.shape[:2]
    scale = body_scale(
        landmarks[LEFT_SHOULDER],
        landmarks[RIGHT_SHOULDER],
        landmarks[LEFT_HIP],
        landmarks[RIGHT_HIP],
        width,
        height,
    )
    if scale is None:
        return _refuse(
            canvas,
            None,
            "The player is too small or too cropped to measure.",
            "no_scale",
            hint="Fill more of the frame with the player, from head to hips.",
        )

    up = torso_up_axis(landmarks, width, height)
    observations = {
        side: _observe_arm(
            side, landmarks, world_landmarks, scale, width, height, minimum_visibility, up
        )
        for side in ("left", "right")
    }

    selection = _select_arm(arm, observations)
    if selection.report is not None:
        return _refuse(
            canvas,
            selection.report.arm,
            selection.report.message,
            selection.report.reason_code,
            hint=selection.hint,
        )

    chosen = observations[selection.arm]
    angles = _collect_angles(
        detector, image_rgb, selection.arm, chosen.angle_3d, stability_passes,
        minimum_visibility=minimum_visibility,
        primary_landmarks=landmarks,
    )
    pooled = pool_angles(angles, demo_minimum, demo_maximum)
    if pooled is None:
        return _refuse(
            canvas,
            selection.arm,
            "The selected elbow geometry was invalid, so no angle was shown.",
            "invalid_geometry",
            hint="Try a photo where the shoulder, elbow, and wrist are all visible.",
        )

    if pooled.confidence == "low":
        return _refuse(
            canvas,
            selection.arm,
            "The measurement was not stable enough to report a result.",
            "unstable",
            hint=(
                f"{pooled.sample_count} valid passes survived; their full spread was "
                f"{pooled.spread_degrees:.1f} degrees. At least three passes and a "
                "spread of at most 20 degrees are required. A clear side-on photo gives a "
                "steadier estimate."
            ),
        )

    if not pooled.verdict_consistent:
        return _refuse(
            canvas, selection.arm,
            "The repeat readings cross a target boundary, so no Green or Red result is supported.",
            "borderline", hint="Try a clearer view or review the chosen target range.",
        )

    # Missing passes reduce support even when the survivors happen to agree.
    if pooled.sample_count < 5 and pooled.confidence == "high":
        pooled = replace(pooled, confidence="moderate")

    return _analyzed(
        canvas,
        chosen,
        pooled,
        demo_minimum,
        demo_maximum,
        arm_was_detected=selection.arm_was_detected,
        attempted_passes=5 if stability_passes else 1,
        focused_on_player=focused,
    )


# --- arm selection -----------------------------------------------------------


@dataclass(frozen=True)
class _Selection:
    """Which arm to measure, or the reason no arm could be chosen."""

    arm: Arm = "right"
    arm_was_detected: bool = False
    report: AnalysisReport | None = None
    hint: str = ""


def _select_arm(
    requested: ArmChoice,
    observations: dict[str, ArmObservation],
) -> _Selection:
    """Choose the racket arm, or explain why the photo cannot be scored.

    In ``auto`` mode the racket arm is the more bent of the arms that are both
    visible and already raised into a preparation position: at the trophy
    position the tossing arm is nearly straight and high, while the hitting arm
    is folded to roughly a right angle near shoulder height.
    """

    if requested != "auto":
        chosen = observations[requested]
        if not chosen.reliable:
            return _Selection(
                report=_reason(
                    requested,
                    f"The {requested} arm is not clearly visible in this photo.",
                    "arm_not_visible",
                ),
                hint="Choose a photo where that whole arm is unobstructed.",
            )
        if chosen.angle_3d is None:
            return _Selection(
                report=_reason(
                    requested,
                    "The selected elbow geometry was invalid, so no angle was shown.",
                    "invalid_geometry",
                ),
            )
        other = observations["left" if requested == "right" else "right"]
        if not other.reliable:
            return _Selection(report=_reason(requested,
                "The opposite arm is hidden, so the serve preparation cannot be verified.",
                "ambiguous_arm"), hint="Use a photo showing both arms.")
        if not _is_trophy_candidate(chosen, other):
            return _not_trophy(requested)
        if _is_trophy_candidate(other, chosen) and (
            other.angle_3d is None or chosen.angle_3d > other.angle_3d - 20
        ):
            return _Selection(report=_reason(requested,
                "The selected arm cannot be distinguished from the tossing arm.",
                "ambiguous_arm"), hint="Select the racket arm or use a clearer side view.")
        return _Selection(arm=requested)

    reliable = {side: item for side, item in observations.items() if item.reliable}
    if not reliable:
        return _Selection(
            report=_reason(
                None,
                "Neither arm was clearly enough visible to measure.",
                "no_reliable_arm",
            ),
            hint="Use a brighter, sharper photo with both arms unobstructed.",
        )

    if len(reliable) == 1:
        return _Selection(report=_reason(None,
            "Both arms must be visible to verify the serve preparation.", "ambiguous_arm"),
            hint="Use a photo showing both the racket arm and tossing arm.")

    candidates = {
        side: item
        for side, item in reliable.items()
        if _is_trophy_candidate(item, observations["left" if side == "right" else "right"])
    }
    if not candidates:
        return _not_trophy(None)

    # The tossing arm is the straighter one, so the most bent candidate is the
    # arm holding the racket.
    chosen = min(candidates.values(), key=lambda item: item.angle_3d)
    if len(candidates) == 2 and abs(observations["left"].angle_3d - observations["right"].angle_3d) < 20:
        return _Selection(report=_reason(None,
            "The two arms are too similar to identify the racket arm reliably.", "ambiguous_arm"),
            hint="Use a clearer side view or select the racket arm.")
    return _Selection(arm=chosen.arm, arm_was_detected=True)


def _is_trophy_candidate(chosen: ArmObservation, other: ArmObservation) -> bool:
    """Use phase cues independent of the configurable elbow feedback interval.

    A near-shoulder racket arm with an ascending forearm, plus an elevated
    opposite hand, supports preparation. This cannot establish a temporal TP
    event, racket location, or the correctness of the entire serve.
    """
    return (chosen.reliable and other.reliable and chosen.angle_3d is not None
            and other.angle_3d is not None and chosen.in_preparation
            and other.geometry.wrist_rise >= MIN_TOSS_WRIST_RISE
            and other.geometry.elbow_rise >= -0.10)


def _not_trophy(arm: Arm | None) -> _Selection:
    return _Selection(report=_reason(arm,
        "This photo does not provide clear trophy-position preparation cues.", "not_trophy_pose"),
        hint="Show the racket forearm rising near the shoulder and the opposite hand raised. "
             "Ready stance, contact, and follow-through frames cannot be scored here.")


def _reason(arm: Arm | None, message: str, reason_code: str) -> AnalysisReport:
    return AnalysisReport(
        status="cannot_analyze",
        arm=arm,
        angle_degrees=None,
        in_demo_range=None,
        message=message,
        reason_code=reason_code,
    )


# --- measurement -------------------------------------------------------------


def _observe_arm(
    arm: Arm,
    landmarks: Sequence[Point],
    world_landmarks: Sequence[Point3],
    scale: float,
    width: int,
    height: int,
    minimum_visibility: float,
    up: tuple[float, float] = (0.0, -1.0),
) -> ArmObservation:
    """Measure one arm's visibility, raised-ness, and elbow angle in one pass."""

    indices = LEFT_ARM_INDICES if arm == "left" else RIGHT_ARM_INDICES
    shoulder, elbow, wrist = (landmarks[index] for index in indices)
    world = tuple(world_landmarks[index] for index in indices)

    geometry = arm_geometry(shoulder, elbow, wrist, scale, height, width=width, up=up)
    reliable = all(
        has_reliable_point(point, minimum_visibility) for point in (shoulder, elbow, wrist)
    )
    reliable = reliable and all(
        np.isfinite((point.x, point.y, point.z, point.visibility, point.presence)).all()
        and minimum_visibility <= point.visibility <= 1 and 0.5 <= point.presence <= 1
        for point in world
    )
    lengths = [np.linalg.norm(np.array((p.x - world[1].x, p.y - world[1].y, p.z - world[1].z)))
               for p in (world[0], world[2])]
    reliable = reliable and all(0.05 <= length <= 0.8 for length in lengths)
    reliable = reliable and 0.5 <= lengths[0] / max(lengths[1], 1e-9) <= 2.0
    return ArmObservation(
        arm=arm,
        shoulder=shoulder,
        elbow=elbow,
        wrist=wrist,
        geometry=geometry,
        angle_3d=calculate_elbow_angle_3d(*world),
        angle_2d=calculate_elbow_angle(shoulder, elbow, wrist, width=width, height=height),
        minimum_visibility=min(
            shoulder.visibility, elbow.visibility, wrist.visibility
        ),
        reliable=reliable,
        in_preparation=is_in_preparation_position(geometry),
    )


def _collect_angles(
    detector: object,
    image_rgb: np.ndarray,
    arm: Arm,
    primary_angle: float | None,
    stability_passes: bool,
    *, minimum_visibility: float = DEFAULT_MINIMUM_VISIBILITY,
    primary_landmarks: Sequence[Point],
) -> list[float]:
    """Measure the same elbow across cheap image variants to expose instability.

    Each variant must support the same arm, preparation cues and valid geometry.
    Agreement can reveal instability; it cannot establish absolute accuracy.
    """

    angles: list[float] = []
    if primary_angle is not None:
        angles.append(primary_angle)
    if not stability_passes:
        return angles

    height, width = image_rgb.shape[:2]
    scaled_width, scaled_height = max(64, round(width * .75)), max(64, round(height * .75))
    variants: list[tuple[np.ndarray, bool, np.ndarray]] = [
        (
            cv2.resize(
                image_rgb,
                (scaled_width, scaled_height),
                interpolation=cv2.INTER_AREA,
            ),
            False,
            np.array([[scaled_width / width, 0, 0], [0, scaled_height / height, 0]], dtype=float),
        ),
        (np.ascontiguousarray(image_rgb[:, ::-1]), True,
         np.array([[-1, 0, width - 1], [0, 1, 0]], dtype=float)),
    ]
    for degrees in (-8, 8):
        transform = cv2.getRotationMatrix2D((width / 2, height / 2), degrees, 1)
        variants.append((cv2.warpAffine(
            image_rgb, transform,
            (width, height), borderMode=cv2.BORDER_REFLECT_101,
        ), False, transform))

    for variant, mirrored, transform in variants:
        detected = _detect(detector, variant)
        if detected is None:
            continue
        landmarks, world_landmarks = detected
        if len(landmarks) != 33 or len(world_landmarks) != 33:
            continue
        vh, vw = variant.shape[:2]
        scale = body_scale(*(landmarks[i] for i in (11, 12, 23, 24)), vw, vh)
        if scale is None:
            continue
        up = torso_up_axis(landmarks, vw, vh)
        observations = {side: _observe_arm(side, landmarks, world_landmarks, scale,
                                         vw, vh, minimum_visibility, up)
                        for side in ("left", "right")}
        variant_arm = ("left" if arm == "right" else "right") if mirrored else arm
        selection = _select_arm(variant_arm, observations)
        if selection.report is None:
            canonical = _restore_landmarks(landmarks, transform, (vw, vh), (width, height), mirrored)
            if _same_subject_arm(primary_landmarks, canonical, arm, width, height):
                angles.append(observations[variant_arm].angle_3d)
    return angles


def _player_focus_box(landmarks: Sequence[Point]) -> tuple[float, float, float, float] | None:
    """Focus a small detected person before measuring, independent of feedback.

    The fixed box uses reliable coarse image landmarks only for localization.
    It never selects a crop by angle, phase, target, or green/red outcome.
    """
    if (len(landmarks) != 33 or
            not all(np.isfinite((p.x, p.y)).all() for p in landmarks) or
            not all(has_reliable_point(landmarks[i], .2) for i in (11, 12))):
        return None
    points = [p for p in landmarks if has_reliable_point(p, .2)]
    if len(points) < 8:
        return None
    left, right = min(p.x for p in points), max(p.x for p in points)
    top, bottom = min(p.y for p in points), max(p.y for p in points)
    width, height = right-left, bottom-top
    if width <= 0 or height <= 0 or width*height > .10:
        return None
    return (max(0., left-.3*width), max(0., top-.15*height),
            min(1., right+.3*width), min(1., bottom+.15*height))


def _focus_pixels(box: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    return (int(box[0]*width), int(box[1]*height),
            min(width, int(box[2]*width)+1), min(height, int(box[3]*height)+1))


def _same_torso(primary: Sequence[Point], repeated: Sequence[Point], width: int, height: int) -> bool:
    """Associate focus with the original shoulders without trusting coarse arms."""
    scale = body_scale(*(primary[i] for i in (11, 12, 23, 24)), width, height)
    if scale is None:
        return False
    return all(has_reliable_point(repeated[i], .2) and
               np.hypot((primary[i].x-repeated[i].x)*width,
                        (primary[i].y-repeated[i].y)*height) <= .25*scale
               for i in (11, 12))


def _restore_landmarks(
    landmarks: Sequence[Point], transform: np.ndarray,
    variant_size: tuple[int, int], original_size: tuple[int, int], mirrored: bool,
) -> list[Point]:
    """Undo the image affine and anatomical index swap before association."""
    vw, vh = variant_size
    width, height = original_size
    inverse = cv2.invertAffineTransform(transform)
    swap = {11: 12, 12: 11, 13: 14, 14: 13, 15: 16, 16: 15, 23: 24, 24: 23}
    result = []
    for i in range(33):
        point = landmarks[swap.get(i, i) if mirrored else i]
        x, y = inverse @ np.array([point.x * vw, point.y * vh, 1.0])
        result.append(replace(point, x=float(x / width), y=float(y / height)))
    return result


def _same_subject_arm(
    primary: Sequence[Point], repeated: Sequence[Point], arm: Arm, width: int, height: int
) -> bool:
    """Reject another person or a side swap instead of pooling a different elbow.

    These are conservative association tolerances, not identity recognition.
    """
    scale = body_scale(*(primary[i] for i in (11, 12, 23, 24)), width, height)
    repeated_scale = body_scale(*(repeated[i] for i in (11, 12, 23, 24)), width, height)
    if scale is None or repeated_scale is None or not .7 <= repeated_scale / scale <= 1.4:
        return False
    indices = LEFT_ARM_INDICES if arm == "left" else RIGHT_ARM_INDICES
    # Shoulders define location even when the hips are cropped/occluded.
    for i in (11, 12, *indices):
        if not has_reliable_point(repeated[i], .2):
            return False
        distance = np.hypot((primary[i].x - repeated[i].x) * width,
                            (primary[i].y - repeated[i].y) * height)
        if distance > (.25 if i in (11, 12) else .45) * scale:
            return False
    return True


def _detect(
    detector: object,
    image_rgb: np.ndarray,
) -> tuple[list[Point], list[Point3]] | None:
    """Run one detection and convert the result into plain, testable points."""

    input_image = mp.Image(
        image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(image_rgb)
    )
    with _detector_lock:
        result = detector.detect(input_image)

    if not result.pose_landmarks or not result.pose_world_landmarks:
        return None
    return (
        [
            Point(
                x=float(item.x),
                y=float(item.y),
                visibility=float(getattr(item, "visibility", 0.0)),
                presence=float(getattr(item, "presence", 0.0)),
            )
            for item in result.pose_landmarks[0]
        ],
        [
            Point3(x=float(item.x), y=float(item.y), z=float(item.z),
                   visibility=float(getattr(item, "visibility", 0.0)),
                   presence=float(getattr(item, "presence", 0.0)))
            for item in result.pose_world_landmarks[0]
        ],
    )


# --- reporting ---------------------------------------------------------------


def _analyzed(
    canvas: np.ndarray,
    observation: ArmObservation,
    pooled: AngleResult,
    demo_minimum: float,
    demo_maximum: float,
    *,
    arm_was_detected: bool,
    attempted_passes: int,
    focused_on_player: bool = False,
) -> tuple[np.ndarray, AnalysisReport]:
    """Draw and describe a completed measurement."""

    color = GREEN if pooled.in_demo_range else RED
    verdict = "GREEN - In Range" if pooled.in_demo_range else "RED - Adjust"
    if pooled.in_demo_range:
        message = "Elbow estimate is within the target range"
    elif pooled.degrees < demo_minimum:
        message = "Elbow estimate is below the target range (elbow more bent)"
    else:
        message = "Elbow estimate is above the target range (elbow straighter)"

    draw_measured_arm(
        canvas,
        observation.shoulder,
        observation.elbow,
        observation.wrist,
        color,
        pooled.degrees,
    )
    details = [
        f"{observation.arm.title()} Elbow {pooled.degrees:.0f} deg"
        f"  |  Target {demo_minimum:.0f}-{demo_maximum:.0f} deg",
        f"{message}  |  Repeat Agreement: {pooled.confidence.title()}",
    ]
    # A banner would hide most of a small focused player. The UI already shows
    # the verdict; keep the crop's annotated arm visible for inspection.
    if not focused_on_player:
        draw_banner(canvas, f"Tennis360  {verdict}", details, color)

    return cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB), AnalysisReport(
        status="analyzed",
        arm=observation.arm,
        angle_degrees=round(pooled.degrees, 1),
        in_demo_range=pooled.in_demo_range,
        message=f"{message}.",
        confidence=pooled.confidence,
        spread_degrees=round(pooled.spread_degrees, 1),
        sample_count=pooled.sample_count,
        projected_angle_degrees=(
            round(observation.angle_2d, 1) if observation.angle_2d is not None else None
        ),
        arm_was_detected=arm_was_detected,
        minimum_angle_degrees=round(pooled.minimum_degrees, 1),
        maximum_angle_degrees=round(pooled.maximum_degrees, 1),
        attempted_passes=attempted_passes,
        focused_on_player=focused_on_player,
    )


def _cannot_analyze(
    canvas: np.ndarray,
    arm: Arm | None,
    message: str,
    reason_code: str,
    *,
    hint: str = "",
    focused_on_player: bool = False,
) -> tuple[np.ndarray, AnalysisReport]:
    """Draw and describe a refusal, always with a reason the user can act on."""

    if not focused_on_player:
        draw_banner(
            canvas,
            "Tennis360  CANNOT ANALYZE",
            [line for line in (message, hint) if line],
            AMBER,
        )
    return cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB), AnalysisReport(
        status="cannot_analyze",
        arm=arm,
        angle_degrees=None,
        in_demo_range=None,
        message=f"{message} {hint}".strip(),
        reason_code=reason_code,
        focused_on_player=focused_on_player,
    )
