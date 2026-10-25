"""Video analysis for the desktop deep-analysis workflow.

Capabilities:
- batch analysis of many videos (or photos) through one call;
- per-frame trophy-gate scanning to find serve preparation segments;
- keyframe extraction (trophy pose + an estimated post-trophy frame);
- skeleton-annotated mp4 output;
- side + front multi-angle fusion (side: elbow angle, front: toss/turn).

Contact-moment detection is an estimate and labeled as one: the pipeline
finds the trophy position reliably, but the exact contact frame of a fast
serve cannot be certified from monocular landmarks alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from tennis360.annotate import draw_measured_arm, draw_skeleton
from tennis360.pose_detector import (
    LEFT_ARM_INDICES,
    LEFT_HIP,
    LEFT_SHOULDER,
    RIGHT_ARM_INDICES,
    RIGHT_HIP,
    RIGHT_SHOULDER,
    ArmChoice,
    get_detector,
)
from tennis360.pose_math import (
    DEFAULT_MINIMUM_VISIBILITY,
    Arm,
    Point3,
    arm_geometry,
    body_scale,
    calculate_elbow_angle_3d,
    has_reliable_point,
    is_in_preparation_position,
)
from tennis360.strokes import (
    SWING_ACTIONS,
    KeyMoments,
    StrokeMetrics,
    SwingSample,
    analyze_swing,
)

VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".m4v"})
PHOTO_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif"})


@dataclass
class FrameAnalysis:
    """What one sampled video frame tells us about the measured arm."""

    index: int
    time_s: float
    arm: Arm | None
    angle_3d: float | None
    wrist_rise: float | None
    elbow_rise: float | None
    in_preparation: bool
    wrist_world: Point3 | None = None


@dataclass
class VideoAnalysis:
    """Result of scanning one video for serve preparation segments."""

    source: str
    fps: float
    sampled_frames: int
    frames: list[FrameAnalysis] = field(default_factory=list)
    trophy_segments: list[tuple[int, int]] = field(default_factory=list)
    best_trophy_index: int | None = None
    contact_hint_index: int | None = None


def _detect_single(detector: object, image_rgb: np.ndarray):
    """One MediaPipe pass returning plain points, or None when no person."""

    import mediapipe as mp

    mp_image = mp.Image(
        image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(image_rgb)
    )
    result = detector.detect(mp_image)
    if not result.pose_landmarks or not result.pose_world_landmarks:
        return None
    from tennis360.pose_math import Point

    landmarks = [
        Point(
            x=float(item.x),
            y=float(item.y),
            visibility=float(getattr(item, "visibility", 0.0)),
        )
        for item in result.pose_landmarks[0]
    ]
    world = [
        Point3(x=float(item.x), y=float(item.y), z=float(item.z))
        for item in result.pose_world_landmarks[0]
    ]
    return landmarks, world


def _observe_frame_arm(
    arm: Arm,
    landmarks,
    world,
    scale: float,
    width: int,
    height: int,
    minimum_visibility: float,
) -> FrameAnalysis | None:
    indices = LEFT_ARM_INDICES if arm == "left" else RIGHT_ARM_INDICES
    shoulder, elbow, wrist = (landmarks[i] for i in indices)
    if not all(has_reliable_point(p, minimum_visibility) for p in (shoulder, elbow, wrist)):
        return None
    geometry = arm_geometry(shoulder, elbow, wrist, scale, height)
    angle = calculate_elbow_angle_3d(*(world[i] for i in indices))
    return FrameAnalysis(
        index=-1,
        time_s=0.0,
        arm=arm,
        angle_3d=angle,
        wrist_rise=geometry.wrist_rise,
        elbow_rise=geometry.elbow_rise,
        in_preparation=is_in_preparation_position(geometry),
        wrist_world=world[indices[2]],
    )


def analyze_video(
    path: str | Path,
    arm: ArmChoice = "auto",
    *,
    sample_fps: float = 5.0,
    minimum_visibility: float = DEFAULT_MINIMUM_VISIBILITY,
    model_path=None,
) -> VideoAnalysis:
    """Scan a video for trophy-position segments, one detection per sample.

    ``arm`` may be "auto", "left", or "right". In auto mode each sampled frame
    picks the more-bent arm that is raised into preparation, mirroring the
    still-photo logic.
    """

    from tennis360.pose_detector import DEFAULT_MODEL_PATH

    source = str(path)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {source}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, round(fps / sample_fps))
    detector = get_detector(DEFAULT_MODEL_PATH if model_path is None else model_path)

    frames: list[FrameAnalysis] = []
    index = 0
    while True:
        ok, frame_bgr = capture.read()
        if not ok:
            break
        if index % stride == 0:
            image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            detected = _detect_single(detector, image_rgb)
            if detected is not None:
                landmarks, world = detected
                height, width = image_rgb.shape[:2]
                scale = body_scale(
                    landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER],
                    landmarks[LEFT_HIP], landmarks[RIGHT_HIP], width, height,
                )
                if scale is not None:
                    observed = {}
                    for side in ("left", "right"):
                        item = _observe_frame_arm(
                            side, landmarks, world, scale, width, height,
                            minimum_visibility,
                        )
                        if item is not None and item.angle_3d is not None:
                            observed[side] = item
                    chosen = _pick_frame_arm(arm, observed)
                    if chosen is not None:
                        chosen.index = index
                        chosen.time_s = index / fps
                        frames.append(chosen)
        index += 1
    capture.release()

    analysis = VideoAnalysis(
        source=source, fps=fps, sampled_frames=len(frames), frames=frames
    )
    analysis.trophy_segments = _find_segments(frames)
    if analysis.trophy_segments:
        analysis.best_trophy_index = _best_trophy_frame(frames, analysis.trophy_segments)
        analysis.contact_hint_index = _contact_hint(frames, analysis.trophy_segments)
    return analysis


def _pick_frame_arm(
    requested: ArmChoice, observed: dict[str, FrameAnalysis]
) -> FrameAnalysis | None:
    if requested != "auto":
        return observed.get(requested)
    candidates = {s: f for s, f in observed.items() if f.in_preparation}
    if not candidates:
        return None
    return min(candidates.values(), key=lambda f: f.angle_3d or 180.0)


def _find_segments(frames: list[FrameAnalysis]) -> list[tuple[int, int]]:
    """Group contiguous preparation frames into (start, end) sample ranges."""

    segments: list[tuple[int, int]] = []
    start: int | None = None
    for position, frame in enumerate(frames):
        if frame.in_preparation:
            if start is None:
                start = position
        elif start is not None:
            segments.append((start, position - 1))
            start = None
    if start is not None:
        segments.append((start, len(frames) - 1))
    return [seg for seg in segments if seg[1] - seg[0] >= 1]


def _best_trophy_frame(
    frames: list[FrameAnalysis], segments: list[tuple[int, int]]
) -> int:
    """Pick the sampled frame with the highest wrist inside the longest segment."""

    longest = max(segments, key=lambda seg: seg[1] - seg[0])
    candidates = frames[longest[0] : longest[1] + 1]
    best = max(candidates, key=lambda f: f.wrist_rise if f.wrist_rise is not None else -9.0)
    return frames.index(best)


def _contact_hint(
    frames: list[FrameAnalysis], segments: list[tuple[int, int]]
) -> int | None:
    """Heuristic: first sampled frame after the trophy segment ends.

    Labeled a hint, not a certified contact frame: monocular landmarks cannot
    certify the exact contact instant of a fast serve.
    """

    longest = max(segments, key=lambda seg: seg[1] - seg[0])
    after = longest[1] + 1
    return after if after < len(frames) else None


def extract_keyframes(
    analysis: VideoAnalysis, output_dir: str | Path
) -> dict[str, str]:
    """Save the best trophy frame (and contact hint) as annotated PNGs."""

    from tennis360.pose_detector import analyze_rgb_image

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(analysis.source)
    saved: dict[str, str] = {}

    targets = {}
    if analysis.best_trophy_index is not None:
        frame = analysis.frames[analysis.best_trophy_index]
        targets[f"trophy_frame{frame.index:05d}.png"] = frame
    if analysis.contact_hint_index is not None:
        frame = analysis.frames[analysis.contact_hint_index]
        targets[f"contact_hint_frame{frame.index:05d}.png"] = frame

    for name, frame in targets.items():
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame.index)
        ok, frame_bgr = capture.read()
        if not ok:
            continue
        image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        try:
            annotated, _ = analyze_rgb_image(
                image_rgb, frame.arm or "auto", stability_passes=False
            )
        except Exception:
            annotated = image_rgb
        destination = output / name
        cv2.imwrite(str(destination), cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR))
        saved[name] = str(destination)
    capture.release()
    return saved


def write_annotated_video(
    source: str | Path,
    destination: str | Path,
    arm: ArmChoice = "auto",
    *,
    minimum_visibility: float = DEFAULT_MINIMUM_VISIBILITY,
    model_path=None,
) -> str:
    """Write an mp4 with the MediaPipe skeleton drawn on every frame.

    Frames passing the trophy gate also get the measured arm and angle label.
    Detection runs once per frame; a 30 fps clip processes at roughly 1x–2x
    realtime on CPU.
    """

    from tennis360.pose_detector import DEFAULT_MODEL_PATH
    from tennis360.pose_math import Point

    src = str(source)
    dst = str(destination)
    capture = cv2.VideoCapture(src)
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {src}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    detector = get_detector(DEFAULT_MODEL_PATH if model_path is None else model_path)

    while True:
        ok, frame_bgr = capture.read()
        if not ok:
            break
        canvas = frame_bgr.copy()
        image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        detected = _detect_single(detector, image_rgb)
        if detected is not None:
            landmarks, world = detected
            draw_skeleton(canvas, landmarks)
            scale = body_scale(
                landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER],
                landmarks[LEFT_HIP], landmarks[RIGHT_HIP], width, height,
            )
            if scale is not None:
                observed = {}
                for side in ("left", "right"):
                    item = _observe_frame_arm(
                        side, landmarks, world, scale, width, height, minimum_visibility
                    )
                    if item is not None and item.angle_3d is not None:
                        observed[side] = item
                chosen = _pick_frame_arm(arm, observed)
                if chosen is not None and chosen.in_preparation:
                    indices = (
                        LEFT_ARM_INDICES if chosen.arm == "left" else RIGHT_ARM_INDICES
                    )
                    from tennis360.annotate import GREEN

                    draw_measured_arm(
                        canvas,
                        landmarks[indices[0]],
                        landmarks[indices[1]],
                        landmarks[indices[2]],
                        GREEN,
                        chosen.angle_3d or 0.0,
                    )
        writer.write(canvas)

    capture.release()
    writer.release()
    return dst


# --- multi-angle fusion -------------------------------------------------------


@dataclass
class FrontMetrics:
    """What a front-view clip contributes: toss height and shoulder turn."""

    max_toss_wrist_rise: float | None
    shoulder_turn_amplitude_deg: float | None
    sampled_frames: int


def analyze_front_metrics(
    path: str | Path,
    *,
    sample_fps: float = 5.0,
    minimum_visibility: float = DEFAULT_MINIMUM_VISIBILITY,
    model_path=None,
) -> FrontMetrics:
    """Measure toss-arm rise and shoulder-line rotation from a front-view clip.

    The shoulder-turn amplitude is the max-minus-min angle of the shoulder
    segment (landmark 11 → 12) against horizontal across sampled frames. It is
    a 2D proxy for body rotation, labeled as such.
    """

    import math

    from tennis360.pose_detector import DEFAULT_MODEL_PATH
    from tennis360.pose_math import Point

    source = str(path)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {source}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, round(fps / sample_fps))
    detector = get_detector(DEFAULT_MODEL_PATH if model_path is None else model_path)

    toss_rises: list[float] = []
    shoulder_angles: list[float] = []
    sampled = 0
    index = 0
    while True:
        ok, frame_bgr = capture.read()
        if not ok:
            break
        if index % stride == 0:
            image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            detected = _detect_single(detector, image_rgb)
            if detected is not None:
                landmarks, _ = detected
                height, width = image_rgb.shape[:2]
                scale = body_scale(
                    landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER],
                    landmarks[LEFT_HIP], landmarks[RIGHT_HIP], width, height,
                )
                if scale is not None:
                    sampled += 1
                    # Tossing arm: the higher wrist of the two arms.
                    rises = []
                    for indices in (LEFT_ARM_INDICES, RIGHT_ARM_INDICES):
                        pts = [landmarks[i] for i in indices]
                        if all(
                            has_reliable_point(p, minimum_visibility) for p in pts
                        ):
                            geo = arm_geometry(pts[0], pts[1], pts[2], scale, height)
                            rises.append(geo.wrist_rise)
                    if rises:
                        toss_rises.append(max(rises))
                    left_s, right_s = landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER]
                    if has_reliable_point(left_s, minimum_visibility) and has_reliable_point(
                        right_s, minimum_visibility
                    ):
                        angle = math.degrees(
                            math.atan2(
                                (right_s.y - left_s.y) * height,
                                (right_s.x - left_s.x) * width,
                            )
                        )
                        shoulder_angles.append(angle)
        index += 1
    capture.release()

    turn = (
        max(shoulder_angles) - min(shoulder_angles)
        if len(shoulder_angles) >= 2
        else None
    )
    return FrontMetrics(
        max_toss_wrist_rise=max(toss_rises) if toss_rises else None,
        shoulder_turn_amplitude_deg=turn,
        sampled_frames=sampled,
    )


@dataclass
class FusedAnalysis:
    """Side + front clips of the same serve, analyzed with complementary logic."""

    side: VideoAnalysis
    front: FrontMetrics


def analyze_multi_angle(
    side_path: str | Path,
    front_path: str | Path,
    arm: ArmChoice = "auto",
    **kwargs,
) -> FusedAnalysis:
    """Cross-analyze one serve filmed from side and front.

    Side clip: elbow angle at the trophy position (3D world landmarks).
    Front clip: tossing-arm height and shoulder-turn amplitude (2D proxies).
    """

    side = analyze_video(side_path, arm=arm, **kwargs)
    front = analyze_front_metrics(front_path, **kwargs)
    return FusedAnalysis(side=side, front=front)


# --- swing analysis (forehand / backhands / slices / overhead / volleys) --
# Mirrors the mobile Live app's key-moment model so both versions analyze the
# same checkpoints per stroke.


@dataclass
class GroundstrokeAnalysis:
    """Result of analyzing one groundstroke clip."""

    source: str
    action: str
    fps: float
    arm: Arm | None
    second_arm: Arm | None
    sampled_frames: int
    moments: KeyMoments | None
    metrics: StrokeMetrics | None
    suggestions: list[str] = field(default_factory=list)
    sample_times: list[float] = field(default_factory=list)


def _resolve_groundstroke_arms(
    action: str, requested: ArmChoice
) -> tuple[Arm, Arm | None]:
    """Pick the hitting arm (and second arm for a two-handed backhand).

    Right-handed default per product requirement: forehand and one-handed
    backhand are measured on the right arm unless ``--arm`` says otherwise.
    """

    if action == "backhand-two":
        hitting: Arm = "right" if requested in ("auto", "right") else "left"
        second: Arm | None = "left" if hitting == "right" else "right"
        return hitting, second
    resolved: Arm = "right" if requested == "auto" else requested  # type: ignore[assignment]
    return resolved, None


def _observe_swing_sample(
    index: int,
    fps: float,
    hitting_arm: Arm,
    second_arm: Arm | None,
    landmarks,
    world,
    scale: float,
    width: int,
    height: int,
    minimum_visibility: float,
):
    """Build one SwingSample from a detected frame, or None if unusable."""

    indices = LEFT_ARM_INDICES if hitting_arm == "left" else RIGHT_ARM_INDICES
    shoulder, elbow, wrist = (landmarks[i] for i in indices)
    if not all(has_reliable_point(p, minimum_visibility) for p in (shoulder, elbow, wrist)):
        return None
    left_s, right_s = landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER]
    if not (
        has_reliable_point(left_s, minimum_visibility)
        and has_reliable_point(right_s, minimum_visibility)
    ):
        return None

    geometry = arm_geometry(shoulder, elbow, wrist, scale, height)
    second_angle = None
    if second_arm is not None:
        other = LEFT_ARM_INDICES if second_arm == "left" else RIGHT_ARM_INDICES
        pts = [landmarks[i] for i in other]
        if all(has_reliable_point(p, minimum_visibility) for p in pts):
            second_angle = calculate_elbow_angle_3d(*(world[i] for i in other))

    shoulder_angle = math.degrees(
        math.atan2(
            (right_s.y - left_s.y) * height,
            (right_s.x - left_s.x) * width,
        )
    )
    return SwingSample(
        index=index,
        time_s=index / fps,
        wrist_x=wrist.x,
        wrist_rise=geometry.wrist_rise,
        elbow_angle=calculate_elbow_angle_3d(*(world[i] for i in indices)),
        second_elbow_angle=second_angle,
        shoulder_mid_x=(left_s.x + right_s.x) / 2.0,
        shoulder_angle_deg=shoulder_angle,
        width_px=float(width),
        scale_px=scale,
        shoulder_mid_y=(left_s.y + right_s.y) / 2.0,
    )


def analyze_groundstroke(
    path: str | Path,
    action: str = "forehand",
    arm: ArmChoice = "auto",
    *,
    sample_fps: float = 5.0,
    minimum_visibility: float = DEFAULT_MINIMUM_VISIBILITY,
    model_path=None,
    targets=None,
) -> GroundstrokeAnalysis:
    """Analyze one swing clip with the key-moment model of the given action.

    ``action`` is one of the SWING_ACTIONS values (forehand, backhand-one,
    backhand-two, forehand-slice, backhand-slice, overhead,
    volley-forehand, volley-backhand).
    The overhead uses the vertical key-moment model; all others use
    backswing / contact / follow-through.
    Key-moment detection is an estimate (see tennis360.strokes).
    """

    if action not in SWING_ACTIONS:
        raise ValueError(f"Unknown swing action: {action}")

    from tennis360.pose_detector import DEFAULT_MODEL_PATH

    source = str(path)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {source}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, round(fps / sample_fps))
    detector = get_detector(DEFAULT_MODEL_PATH if model_path is None else model_path)
    hitting_arm, second_arm = _resolve_groundstroke_arms(action, arm)

    samples = []
    index = 0
    while True:
        ok, frame_bgr = capture.read()
        if not ok:
            break
        if index % stride == 0:
            image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            detected = _detect_single(detector, image_rgb)
            if detected is not None:
                landmarks, world = detected
                height, width = image_rgb.shape[:2]
                scale = body_scale(
                    landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER],
                    landmarks[LEFT_HIP], landmarks[RIGHT_HIP], width, height,
                )
                if scale is not None:
                    sample = _observe_swing_sample(
                        index, fps, hitting_arm, second_arm,
                        landmarks, world, scale, width, height,
                        minimum_visibility,
                    )
                    if sample is not None:
                        samples.append(sample)
        index += 1
    capture.release()

    moments, metrics, suggestions = analyze_swing(action, samples, targets)
    return GroundstrokeAnalysis(
        source=source,
        action=action,
        fps=fps,
        arm=hitting_arm,
        second_arm=second_arm,
        sampled_frames=len(samples),
        moments=moments,
        metrics=metrics,
        suggestions=suggestions,
        sample_times=[s.time_s for s in samples],
    )


# --- face anonymization -------------------------------------------------------

# MediaPipe Pose face landmark indices.
_FACE_INDICES = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)


def blur_faces_video(
    source: str | Path,
    destination: str | Path,
    *,
    minimum_visibility: float = 0.5,
    model_path=None,
) -> str:
    """Write a copy of the video with every detected face blurred.

    The face region is estimated from MediaPipe Pose face landmarks
    (nose, eyes, ears, mouth); a Gaussian blur is applied to that box.
    Body pose and motion are left untouched, so the clip stays usable
    as an anonymized coaching reference template.

    Frames where no face is found are copied unchanged.
    """

    from tennis360.pose_detector import DEFAULT_MODEL_PATH

    src = str(source)
    dst = str(destination)
    capture = cv2.VideoCapture(src)
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {src}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    detector = get_detector(DEFAULT_MODEL_PATH if model_path is None else model_path)

    while True:
        ok, frame_bgr = capture.read()
        if not ok:
            break
        canvas = frame_bgr.copy()
        image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        detected = _detect_single(detector, image_rgb)
        if detected is not None:
            landmarks, _ = detected
            pts = [
                landmarks[i] for i in _FACE_INDICES
                if landmarks[i] is not None
                and getattr(landmarks[i], "visibility", 1.0) >= minimum_visibility
            ]
            if len(pts) >= 3:
                xs = [p.x * width for p in pts]
                ys = [p.y * height for p in pts]
                pad = int(max(max(xs) - min(xs), max(ys) - min(ys)) * 0.4) + 10
                x1 = max(0, int(min(xs) - pad))
                y1 = max(0, int(min(ys) - pad))
                x2 = min(width, int(max(xs) + pad))
                y2 = min(height, int(max(ys) + pad))
                if x2 > x1 and y2 > y1:
                    face = canvas[y1:y2, x1:x2]
                    k = max(15, ((min(y2 - y1, x2 - x1) // 3) | 1))
                    canvas[y1:y2, x1:x2] = cv2.GaussianBlur(face, (k, k), 0)
        writer.write(canvas)

    capture.release()
    writer.release()
    return dst
