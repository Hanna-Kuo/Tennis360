"""Streamlit entry point for Tennis360's local photo and video analysis."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from tennis360.annotate import POSE_CONNECTIONS
from tennis360.cli import ACTION_CHOICES, _issue_text
from tennis360.config import load_targets
from tennis360.history import (
    AnalysisRecord,
    list_records,
    open_db,
    record as save_history_record,
    trend_points,
    utc_now_iso,
)
from tennis360.image_input import UploadedImageError, decode_uploaded_image
from tennis360.pose_detector import (
    DEFAULT_MINIMUM_VISIBILITY,
    DEFAULT_TROPHY_MAXIMUM,
    DEFAULT_TROPHY_MINIMUM,
    LEFT_ARM_INDICES,
    RIGHT_ARM_INDICES,
    AnalysisReport,
    ModelFileMissingError,
    analyze_rgb_image,
    get_detector,
)
from tennis360.video import _detect_single, analyze_groundstroke, analyze_video

MAX_DISPLAY_WIDTH = 1000

ARM_CHOICES = {
    "Auto-detect racket arm": "auto",
    "Player's right arm": "right",
    "Player's left arm": "left",
}

VIDEO_FILE_TYPES = ("mp4", "mov", "m4v")
VIDEO_ARM_LABELS = {"auto": "Auto", "left": "Left", "right": "Right"}

# Display names for the internal action keys, in ACTION_CHOICES order.
ACTION_LABELS = {
    "serve": "Serve",
    "forehand": "Forehand: Topspin",
    "forehand-slice": "Forehand: Slice",
    "backhand-two": "Backhand: Topspin – Two-Handed",
    "backhand-one": "Backhand: Topspin – One-Handed",
    "backhand-slice": "Backhand: Slice",
    "volley-forehand": "Volley: Forehand",
    "volley-backhand": "Volley: Backhand",
    "half-volley": "Half-Volley: Forehand",
    "overhead": "Overhead Smash",
    "drop-shot": "Drop Shot: Forehand",
    "lob": "Lob: Forehand",
}

# Display names for the internal mode values.
MODE_LABELS = {
    "Serve photo": "Serve Photo Analysis",
    "Stroke video": "Stroke Video Analysis",
    "Progress": "Progress",
}

st.set_page_config(page_title="Tennis360", page_icon="🎾", layout="wide")


@st.cache_resource(show_spinner=False)
def load_detector() -> object:
    """Load the pose model once per server process rather than once per upload."""

    return get_detector()


def fit_result_image(image_rgb: np.ndarray) -> np.ndarray:
    """Downscale only very large photos so the annotation stays sharp on screen."""

    height, width = image_rgb.shape[:2]
    if width <= MAX_DISPLAY_WIDTH:
        return image_rgb
    scale = MAX_DISPLAY_WIDTH / width
    return cv2.resize(
        image_rgb,
        (MAX_DISPLAY_WIDTH, max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def render_verdict(report: AnalysisReport, minimum: float, maximum: float) -> None:
    """Show the headline result: one angle, one colour, one sentence."""

    angle_column, status_column, range_column = st.columns(3)
    angle_column.metric("Estimated Elbow Angle", f"{report.angle_degrees:.1f}°")
    range_column.metric("Target Range", f"{minimum:.0f}°–{maximum:.0f}°")

    if report.in_demo_range:
        status_column.metric("Result", "🟢 Green")
        st.success(f"**Green — In Range.** {report.message}")
    else:
        status_column.metric("Result", "🔴 Red")
        st.error(f"**Red — Needs Adjustment.** {report.message}")

    if report.confidence == "moderate":
        st.warning(
            "Repeat agreement is moderate: some readings differ, or a pass was "
            "rejected. Treat this angle as an estimate."
        )
    st.caption(
        "The Green or Red result compares this elbow estimate with your target "
        "range. It does not grade the entire serve."
    )


def render_measurement_detail(report: AnalysisReport) -> None:
    """Expose the working behind the number so the result stays checkable."""

    spread = report.spread_degrees or 0.0
    with st.expander("How This Number Was Measured"):
        st.markdown(
            f"""
- **Measured Arm:** Player's {report.arm} Arm
  ({'Auto-Detected' if report.arm_was_detected else 'Selected'})
- **Angle Source:** Estimated from MediaPipe 3D world landmarks (shoulder → elbow → wrist)
- **Valid Passes:** {report.sample_count}/{report.attempted_passes} (original, downscaled, mirrored, two small rotations) —
  the reported value is their median
- **Observed Readings:** {report.minimum_angle_degrees:.1f}°–{report.maximum_angle_degrees:.1f}° (Full Spread {spread:.1f}°)
- **Repeat Agreement:** {report.confidence.capitalize()}; this is not an accuracy probability or confidence interval
- **Stage Check:** The serve preparation position is verified on every accepted pass; manual arm selection uses the same check
"""
        )
        if report.focused_on_player:
            st.caption("One extra pass located the small player before the five measurement passes.")
        if report.projected_angle_degrees is not None:
            st.caption(
                f"For comparison, the angle measured on the flat 2D image is "
                f"{report.projected_angle_degrees:.0f}°. It differs whenever the arm "
                "points toward or away from the camera. Pixel aspect ratio is "
                "accounted for. Only the estimated 3D landmarks decide the result."
            )


def _video_targets():
    """Load the target ranges exactly as the command-line tool does.

    Returns None when the shipped defaults cannot be loaded; the video
    analysis functions then fall back to their built-in demonstration values.
    """

    try:
        return load_targets(None)
    except Exception:
        return None


def _target_source(targets, action: str) -> str:
    """Target-range provenance for a history record, mirroring the CLI.

    The CLI takes the source from the loaded target range for the action and
    falls back to "demo" when no range applies.
    """

    if targets is not None:
        hit = targets.get(action)
        if hit is not None:
            return hit.source
    return "demo"


def _photo_history_record(
    report, *, source_file: str, requested_arm: str, targets
) -> AnalysisRecord:
    """Build the history record for a serve-photo result, as the CLI does."""

    return AnalysisRecord(
        recorded_at=utc_now_iso(),
        source_file=source_file,
        action="serve",
        arm=report.arm or requested_arm,
        angle_deg=report.angle_degrees,
        in_range=report.in_demo_range,
        confidence=report.confidence or "",
        spread_deg=report.spread_degrees,
        main_issue_en=_issue_text(report),
        target_source=_target_source(targets, "serve"),
    )


def _serve_video_history_record(
    analysis,
    *,
    source_file: str,
    requested_arm: str,
    minimum: float,
    maximum: float,
    targets,
) -> AnalysisRecord | None:
    """Build the history record for a serve-video result, as the CLI does.

    Returns None when no trophy segment was found (nothing was measured).
    """

    if analysis.best_trophy_index is None:
        return None
    frame = analysis.frames[analysis.best_trophy_index]
    angle = frame.angle_3d
    in_range = angle is not None and minimum <= angle <= maximum
    if angle is not None and angle < minimum:
        issue = "Elbow Over-Bent"
    elif angle is not None and angle > maximum:
        issue = "Elbow Over-Extended"
    else:
        issue = "Angle in Range"
    return AnalysisRecord(
        recorded_at=utc_now_iso(),
        source_file=source_file,
        action="serve",
        arm=frame.arm or requested_arm,
        angle_deg=round(angle, 1) if angle else None,
        in_range=in_range,
        main_issue_en=issue,
        target_source=_target_source(targets, "serve"),
    )


def _swing_video_history_record(
    analysis, *, source_file: str, action: str, requested_arm: str, targets
) -> AnalysisRecord | None:
    """Build the history record for a swing-video result, as the CLI does.

    Returns None when no clear swing was found (nothing was measured).
    """

    if analysis.moments is None or analysis.metrics is None:
        return None
    metrics = analysis.metrics
    issue = (
        "; ".join(analysis.suggestions[:2])
        if analysis.suggestions
        else "Angle in Range"
    )
    return AnalysisRecord(
        recorded_at=utc_now_iso(),
        source_file=source_file,
        action=action,
        arm=analysis.arm or requested_arm,
        angle_deg=round(metrics.contact_elbow_deg, 1)
        if metrics.contact_elbow_deg
        else None,
        in_range=metrics.contact_elbow_in_range,
        main_issue_en=issue,
        target_source=_target_source(targets, action),
    )


def _save_history_once(entry: AnalysisRecord, guard_key) -> None:
    """Save one history record per distinct analysis run.

    Streamlit reruns the script on every interaction, so a session-state
    guard keeps one analysis from being stored repeatedly. The database is
    the same local history file the command-line tool writes to. A failed
    save only shows a warning; the analysis result stays on screen.
    """

    saved_keys = st.session_state.setdefault("history_saved_keys", set())
    if guard_key in saved_keys:
        return
    try:
        connection = open_db()
        try:
            save_history_record(connection, entry)
        finally:
            connection.close()
    except Exception:
        st.warning(
            "This result could not be saved to the local history, so it will "
            "not appear in Progress. The analysis itself is unaffected."
        )
        return
    saved_keys.add(guard_key)


def _serve_video_payload(analysis, targets) -> dict:
    """Flatten a serve VideoAnalysis into plain display data."""

    minimum = float(DEFAULT_TROPHY_MINIMUM)
    maximum = float(DEFAULT_TROPHY_MAXIMUM)
    if targets is not None:
        serve_target = targets.get("serve")
        if serve_target is not None:
            minimum = float(serve_target.minimum_deg)
            maximum = float(serve_target.maximum_deg)

    frames = analysis.frames
    payload = {
        "kind": "serve",
        "sampled_frames": analysis.sampled_frames,
        "fps": analysis.fps,
        "found": analysis.best_trophy_index is not None,
        "minimum": minimum,
        "maximum": maximum,
        "angle": None,
        "best_time": None,
        "arm": None,
        "segments": [],
        "contact_hint_time": None,
    }
    for start, end in analysis.trophy_segments:
        if 0 <= start < len(frames) and 0 <= end < len(frames):
            payload["segments"].append((frames[start].time_s, frames[end].time_s))
    if analysis.best_trophy_index is not None:
        frame = frames[analysis.best_trophy_index]
        payload["angle"] = frame.angle_3d
        payload["best_time"] = frame.time_s
        payload["arm"] = frame.arm
    contact_hint = analysis.contact_hint_index
    if contact_hint is not None and 0 <= contact_hint < len(frames):
        payload["contact_hint_time"] = frames[contact_hint].time_s
    return payload


def _format_degrees(value: float | None) -> str | None:
    return None if value is None else f"{value:.1f}°"


def _format_body_scales(value: float | None) -> str | None:
    return None if value is None else f"{value:.2f} body scales"


def _swing_video_payload(analysis) -> dict:
    """Flatten a GroundstrokeAnalysis into plain display data."""

    payload = {
        "kind": "swing",
        "action": analysis.action,
        "arm": analysis.arm,
        "second_arm": analysis.second_arm,
        "sampled_frames": analysis.sampled_frames,
        "fps": analysis.fps,
        "found": analysis.moments is not None and analysis.metrics is not None,
        "suggestions": list(analysis.suggestions),
        "moment_times": [],
        "metric_rows": [],
    }
    if not payload["found"]:
        return payload

    moments = analysis.moments
    times = analysis.sample_times

    def time_at(position: int) -> float:
        return times[position] if 0 <= position < len(times) else 0.0

    first_label = "Preparation" if analysis.action == "overhead" else "Backswing"
    payload["moment_times"] = [
        (first_label, time_at(moments.backswing)),
        ("Contact", time_at(moments.contact)),
        ("Follow-through", time_at(moments.followthrough)),
    ]

    metrics = analysis.metrics
    rows: list[tuple[str, str]] = []

    def add_row(label: str, formatted: str | None) -> None:
        if formatted is not None:
            rows.append((label, formatted))

    if metrics.contact_elbow_deg is not None:
        elbow_text = f"{metrics.contact_elbow_deg:.1f}°"
        if metrics.contact_elbow_in_range is not None:
            elbow_text += (
                " — Within the Demo Target Range"
                if metrics.contact_elbow_in_range
                else " — Outside the Demo Target Range"
            )
        rows.append(("Elbow Angle at Contact", elbow_text))
    add_row(
        "Support-Arm Elbow Angle at Contact",
        _format_degrees(metrics.second_elbow_deg),
    )
    add_row("Contact Point in Front of Body", _format_body_scales(metrics.contact_in_front))
    add_row("Follow-Through Wrist Height", _format_body_scales(metrics.followthrough_rise))
    add_row("Shoulder Turn (2D Image Estimate)", _format_degrees(metrics.shoulder_turn_deg))
    add_row("Wrist Height at Contact", _format_body_scales(metrics.contact_height))
    add_row(
        "Backswing Compactness (Backward Wrist Travel)",
        _format_body_scales(metrics.backswing_compactness),
    )
    add_row(
        "Backswing Depth (Wrist Height at Backswing)",
        _format_body_scales(metrics.backswing_depth),
    )
    add_row(
        "Follow-Through Length (Wrist Travel)",
        _format_body_scales(metrics.followthrough_length),
    )
    if metrics.knee_bend is not None:
        rows.append(
            ("Knee Bend (Shoulder Drop, 2D Image Estimate)", f"{metrics.knee_bend:.3f} Normalized Image Units")
        )
    add_row(
        "Wrist Stability (Spread of Wrist Height)",
        _format_body_scales(metrics.wrist_stability),
    )
    if metrics.push_forward is not None:
        rows.append(("Forward Push After Contact", "Yes" if metrics.push_forward else "No"))
    payload["metric_rows"] = rows
    return payload


def _extract_frame_landmarks(video_path: str, time_s: float):
    """Detect pose landmarks on one video frame, the pipeline's own way.

    Seeks to ``time_s``, reads that frame, and runs the same single-frame
    detection the video pipeline uses. Returns the 2D landmarks (normalized
    image coordinates), or None when no person is detected.
    """

    capture = cv2.VideoCapture(video_path)
    try:
        if not capture.isOpened():
            return None
        capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, time_s) * 1000.0)
        ok, frame_bgr = capture.read()
        if not ok:
            return None
        image_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        detected = _detect_single(load_detector(), image_rgb)
        if detected is None:
            return None
        landmarks, _world = detected
        return landmarks
    finally:
        capture.release()


def _video_diagram_data(temp_path, analysis, action, payload, targets):
    """Landmarks and measured angle for the skeleton diagram, when available.

    Best effort only: any failure returns None and the result simply shows
    no diagram. Nothing here changes the analysis itself.
    """

    if not payload["found"]:
        return None
    if action == "serve":
        frame = analysis.frames[analysis.best_trophy_index]
        time_s = frame.time_s
        arm = frame.arm
        angle = frame.angle_3d
        minimum, maximum = payload["minimum"], payload["maximum"]
        moment = "at the trophy frame"
    else:
        moments = analysis.moments
        times = analysis.sample_times
        if not (0 <= moments.contact < len(times)):
            return None
        time_s = times[moments.contact]
        arm = analysis.arm
        angle = analysis.metrics.contact_elbow_deg
        target = targets.get(action) if targets is not None else None
        minimum = float(target.minimum_deg) if target is not None else None
        maximum = float(target.maximum_deg) if target is not None else None
        moment = "at contact"
    if arm is None or angle is None:
        return None
    try:
        landmarks = _extract_frame_landmarks(temp_path, time_s)
    except Exception:
        return None
    if not landmarks:
        return None
    return {
        "points": [(float(point.x), float(point.y)) for point in landmarks],
        "arm": arm,
        "angle": float(angle),
        "minimum": minimum,
        "maximum": maximum,
        "moment": moment,
    }


def build_skeleton_diagram_png(
    points, *, arm: str, angle_deg: float, minimum=None, maximum=None
) -> bytes:
    """Render a clean 2D skeleton dot diagram for one measured moment.

    ``points`` are normalized image coordinates (x right, y down) for the
    pose landmarks. The measured arm is highlighted, the elbow-angle arc
    carries the measured value, and — when the angle is outside the target
    range — a dashed ghost forearm shows the nearest target-edge position
    (shoulder and upper arm stay fixed). Returns PNG bytes; the diagram
    exists only in memory and is never written to disk.
    """

    import math
    from io import BytesIO

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Arc

    xs = [point[0] for point in points]
    ys = [1.0 - point[1] for point in points]  # image y grows downward

    indices = LEFT_ARM_INDICES if arm == "left" else RIGHT_ARM_INDICES
    shoulder = (xs[indices[0]], ys[indices[0]])
    elbow = (xs[indices[1]], ys[indices[1]])
    wrist = (xs[indices[2]], ys[indices[2]])

    figure, axes = plt.subplots(figsize=(4.6, 4.6), dpi=150)
    figure.patch.set_facecolor("white")
    axes.set_facecolor("white")

    for start, end in POSE_CONNECTIONS:
        if start < len(points) and end < len(points):
            axes.plot(
                [xs[start], xs[end]],
                [ys[start], ys[end]],
                color="#b0b7bd",
                lw=1.4,
                zorder=1,
            )
    axes.scatter(xs, ys, s=16, color="#5f6368", zorder=2)

    axes.plot(
        [shoulder[0], elbow[0], wrist[0]],
        [shoulder[1], elbow[1], wrist[1]],
        color="#e8710a",
        lw=3.2,
        solid_capstyle="round",
        zorder=3,
    )
    axes.scatter(
        [shoulder[0], elbow[0], wrist[0]],
        [shoulder[1], elbow[1], wrist[1]],
        s=58,
        color="#e8710a",
        edgecolors="white",
        linewidths=1.0,
        zorder=4,
    )

    upper = (shoulder[0] - elbow[0], shoulder[1] - elbow[1])
    fore = (wrist[0] - elbow[0], wrist[1] - elbow[1])
    upper_len = math.hypot(*upper)
    fore_len = math.hypot(*fore)
    frame_x = list(xs)
    frame_y = list(ys)
    if upper_len > 1e-6 and fore_len > 1e-6:

        def _interior(vec) -> float:
            cosine = (upper[0] * vec[0] + upper[1] * vec[1]) / (
                upper_len * math.hypot(*vec)
            )
            return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))

        def _rotate(vec, degrees: float):
            radians = math.radians(degrees)
            cosine, sine = math.cos(radians), math.sin(radians)
            return (
                vec[0] * cosine - vec[1] * sine,
                vec[0] * sine + vec[1] * cosine,
            )

        start_angle = math.degrees(math.atan2(upper[1], upper[0]))
        end_angle = math.degrees(math.atan2(fore[1], fore[0]))
        sweep = (end_angle - start_angle + 180.0) % 360.0 - 180.0
        radius = 0.38 * min(upper_len, fore_len)
        axes.add_patch(
            Arc(
                elbow,
                width=2 * radius,
                height=2 * radius,
                angle=0.0,
                theta1=min(start_angle, start_angle + sweep),
                theta2=max(start_angle, start_angle + sweep),
                color="#e8710a",
                lw=1.6,
                zorder=5,
            )
        )
        mid_angle = math.radians(start_angle + sweep / 2.0)
        label_radius = radius + 0.05
        axes.text(
            elbow[0] + label_radius * math.cos(mid_angle),
            elbow[1] + label_radius * math.sin(mid_angle),
            f"{angle_deg:.0f}°",
            color="#e8710a",
            fontsize=11,
            fontweight="bold",
            ha="center",
            va="center",
            zorder=6,
        )

        if (
            minimum is not None
            and maximum is not None
            and not minimum <= angle_deg <= maximum
        ):
            edge = minimum if angle_deg < minimum else maximum
            delta = edge - _interior(fore)
            if abs(delta) > 0.5:
                trial = _rotate(fore, 1.0)
                sense = 1.0 if (_interior(trial) - _interior(fore)) * delta > 0 else -1.0
                ghost = _rotate(fore, sense * abs(delta))
                ghost_wrist = (elbow[0] + ghost[0], elbow[1] + ghost[1])
                axes.plot(
                    [elbow[0], ghost_wrist[0]],
                    [elbow[1], ghost_wrist[1]],
                    color="#e8710a",
                    lw=2.2,
                    linestyle=(0, (4, 3)),
                    alpha=0.55,
                    zorder=3,
                )
                axes.scatter(
                    [ghost_wrist[0]],
                    [ghost_wrist[1]],
                    s=46,
                    facecolors="none",
                    edgecolors="#e8710a",
                    linewidths=1.4,
                    alpha=0.7,
                    zorder=4,
                )
                frame_x.append(ghost_wrist[0])
                frame_y.append(ghost_wrist[1])

    padding = 0.08
    axes.set_xlim(min(frame_x) - padding, max(frame_x) + padding)
    axes.set_ylim(min(frame_y) - padding, max(frame_y) + padding)
    axes.set_aspect("equal")
    axes.axis("off")
    figure.tight_layout(pad=0.2)
    buffer = BytesIO()
    figure.savefig(buffer, format="png", facecolor="white")
    plt.close(figure)
    return buffer.getvalue()


def _diagram_caption(diagram) -> str:
    """One line tying the diagram to the measured result (real values only)."""

    angle = diagram["angle"]
    minimum = diagram["minimum"]
    maximum = diagram["maximum"]
    moment = diagram["moment"]
    if minimum is None or maximum is None:
        return f"Your elbow {moment}: {angle:.0f}°. This diagram shows your measured pose."
    if angle > maximum:
        return (
            f"Your elbow {moment}: {angle:.0f}°. Target range: "
            f"{minimum:.0f}°–{maximum:.0f}°. Bend the elbow a little more, "
            "as shown by the dashed arm."
        )
    if angle < minimum:
        return (
            f"Your elbow {moment}: {angle:.0f}°. Target range: "
            f"{minimum:.0f}°–{maximum:.0f}°. Straighten the elbow a little "
            "more, as shown by the dashed arm."
        )
    return (
        f"Your elbow {moment}: {angle:.0f}°. Target range: "
        f"{minimum:.0f}°–{maximum:.0f}°. Your elbow is within the target range."
    )


def _render_diagram(payload: dict) -> None:
    """Show the skeleton diagram for a video result, when one was built."""

    diagram = payload.get("diagram")
    if not diagram:
        return
    try:
        png = build_skeleton_diagram_png(
            diagram["points"],
            arm=diagram["arm"],
            angle_deg=diagram["angle"],
            minimum=diagram["minimum"],
            maximum=diagram["maximum"],
        )
    except Exception:
        return
    st.image(png, caption=_diagram_caption(diagram), width=420)


def render_serve_video_result(payload: dict) -> None:
    """Show the serve-video outcome: found or not, frame, angle, segments."""

    st.caption(
        f"Sampled {payload['sampled_frames']} frames at {payload['fps']:.0f} fps "
        "from the uploaded clip. All processing is local."
    )
    if not payload["found"]:
        st.warning(
            "**No Trophy Segment Found.** The sampled frames do not show a serve "
            "preparation (trophy) segment, so no angle was measured."
        )
        st.caption(
            "Use a clip that shows the full serve from one clear viewpoint, "
            "with the player large in the frame."
        )
        return

    st.success("**Serve Found.** A trophy-position segment was detected in this clip.")
    time_column, angle_column, range_column = st.columns(3)
    time_column.metric("Best Trophy Frame", f"{payload['best_time']:.2f} s")
    if payload["angle"] is not None:
        angle_column.metric("Elbow Angle at Trophy Frame", f"{payload['angle']:.1f}°")
    else:
        angle_column.metric("Elbow Angle at Trophy Frame", "n/a")
    range_column.metric(
        "Target Range", f"{payload['minimum']:.0f}°–{payload['maximum']:.0f}°"
    )

    angle = payload["angle"]
    if angle is None:
        st.caption("The elbow angle could not be measured at the trophy frame.")
    elif angle < payload["minimum"]:
        st.caption("Elbow is over-bent at the trophy frame, outside the target range.")
    elif angle > payload["maximum"]:
        st.caption("Elbow is over-extended at the trophy frame, outside the target range.")
    else:
        st.caption("Elbow angle at the trophy frame is within the target range.")
    if payload["arm"]:
        st.caption(f"Measured Arm: Player's {payload['arm']} Arm.")
    if payload["segments"]:
        st.markdown("**Detected Trophy Segments:**")
        for start_s, end_s in payload["segments"]:
            st.markdown(f"- {start_s:.2f} s – {end_s:.2f} s")
    if payload["contact_hint_time"] is not None:
        st.caption(
            f"Estimated contact time: around {payload['contact_hint_time']:.2f} s. "
            "This is an estimate only — the exact contact frame cannot be "
            "confirmed from a single camera view."
        )
    _render_diagram(payload)
    st.caption(
        "The target range is a configurable demonstration value, not a "
        "medically or professionally validated standard."
    )


def render_swing_video_result(payload: dict) -> None:
    """Show the swing-video outcome: key moments, metrics, suggestions."""

    st.caption(
        f"Sampled {payload['sampled_frames']} frames at {payload['fps']:.0f} fps "
        "from the uploaded clip. All processing is local."
    )
    if not payload["found"]:
        st.warning(
            "**No Clear Swing Found.** The sampled frames do not show a distinct "
            "swing motion, so no checkpoints were measured."
        )
        if payload["suggestions"]:
            st.markdown("**What the Analysis Reported:**")
            for suggestion in payload["suggestions"]:
                st.markdown(f"- {suggestion}")
        return

    action_label = ACTION_LABELS.get(payload["action"], payload["action"])
    st.success(
        f"**Swing Found.** Key moments were detected for this {action_label} clip."
    )
    moment_columns = st.columns(3)
    for column, (label, time_s) in zip(moment_columns, payload["moment_times"]):
        column.metric(label, f"{time_s:.2f} s")
    st.caption(
        "Key-moment times are estimates from the wrist path. "
        "They are not exact contact frames."
    )
    if payload["arm"]:
        arm_text = f"Player's {payload['arm']} Arm"
        if payload["second_arm"]:
            arm_text += f" (Support Arm: Player's {payload['second_arm']} Arm)"
        st.caption(f"Measured Arm: {arm_text}.")
    if payload["metric_rows"]:
        st.markdown("**Measurements at the Key Moments:**")
        for label, value in payload["metric_rows"]:
            st.markdown(f"- **{label}:** {value}")
    if payload["suggestions"]:
        st.markdown("**Suggestions:**")
        for suggestion in payload["suggestions"]:
            st.markdown(f"- {suggestion}")
    _render_diagram(payload)


def run_stroke_video_analysis(uploaded_video, action: str, arm: str, selection_key) -> None:
    """Run the same analysis functions the CLI uses, on a temporary copy.

    The uploaded bytes are written to one temporary file because the video
    pipeline reads from disk; the file is deleted as soon as the analysis
    finishes, including when it fails. Uploaded bytes are never stored
    anywhere else.
    """

    suffix = Path(uploaded_video.name).suffix.lower()
    if suffix not in (".mp4", ".mov", ".m4v"):
        suffix = ".mp4"
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(uploaded_video.getvalue())
            temp_path = handle.name
        targets = _video_targets()
        with st.spinner("Analyzing Video Locally…"):
            if action == "serve":
                analysis = analyze_video(temp_path, arm=arm)
                payload = _serve_video_payload(analysis, targets)
            else:
                analysis = analyze_groundstroke(
                    temp_path, action=action, arm=arm, targets=targets
                )
                payload = _swing_video_payload(analysis)
        payload["diagram"] = _video_diagram_data(
            temp_path, analysis, action, payload, targets
        )
        st.session_state["stroke_video_result"] = {
            "key": selection_key,
            "payload": payload,
        }
        if action == "serve":
            entry = _serve_video_history_record(
                analysis,
                source_file=uploaded_video.name,
                requested_arm=arm,
                minimum=payload["minimum"],
                maximum=payload["maximum"],
                targets=targets,
            )
        else:
            entry = _swing_video_history_record(
                analysis,
                source_file=uploaded_video.name,
                action=action,
                requested_arm=arm,
                targets=targets,
            )
        if entry is not None:
            _save_history_once(entry, ("Stroke video",) + tuple(selection_key))
    except ModelFileMissingError as error:
        st.error("The local pose model is not installed yet.")
        st.code(str(error), language=None)
        st.caption("Run start.command or start.bat to install and verify the model, then reopen the app.")
    except ValueError as error:
        st.error(str(error))
    except Exception:  # MediaPipe returns platform-specific runtime errors.
        st.error("The local pose analysis could not finish for this video.")
        st.caption("Choose a clear MP4, MOV, or M4V clip with one visible person, then try again.")
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def stroke_video_mode() -> None:
    """Analyze one uploaded clip of any supported stroke, in the browser UI."""

    st.caption(
        "Upload one stroke video. Tennis360 samples the clip locally, finds the "
        "key moments of the selected stroke, and shows the measured checkpoints "
        "with adjustment suggestions."
    )

    with st.sidebar:
        action = st.selectbox(
            "Stroke Type",
            options=ACTION_CHOICES,
            format_func=lambda value: ACTION_LABELS[value],
        )
        arm = st.selectbox(
            "Arm",
            options=tuple(VIDEO_ARM_LABELS),
            format_func=lambda value: VIDEO_ARM_LABELS[value],
            help="Auto uses the same defaults as the command-line tool.",
        )

        st.divider()
        st.caption(
            "One uploaded video is processed in the local Python app. A temporary "
            "working copy is created for the analysis and deleted as soon as the "
            "analysis finishes. Nothing is uploaded to a cloud service. When a "
            "stroke is measured, the measurements (not the video) are saved to "
            "the local history shown in Progress mode."
        )
        uploaded_video = st.file_uploader(
            "Upload a stroke video",
            type=VIDEO_FILE_TYPES,
            help="One clip showing a single stroke (MP4, MOV, or M4V, max 200 MB).",
        )

    if uploaded_video is None:
        st.info(
            "Choose one stroke video from the sidebar, pick the stroke type and arm, "
            "then run the analysis. A side-on clip of one full stroke works best."
        )
        return

    st.write(f"**Selected Clip:** {uploaded_video.name}")
    selection_key = (uploaded_video.name, uploaded_video.size, action, arm)
    if st.button("Analyze Video"):
        run_stroke_video_analysis(uploaded_video, action, arm, selection_key)

    stored = st.session_state.get("stroke_video_result")
    if stored is not None and stored["key"] == selection_key:
        if stored["payload"]["kind"] == "serve":
            render_serve_video_result(stored["payload"])
        else:
            render_swing_video_result(stored["payload"])
    elif stored is not None:
        st.caption("The clip, stroke type, or arm changed — click Analyze Video to run the analysis again.")


def _render_progress_chart(points, target) -> None:
    """Plot saved angles oldest to newest, with the demo target band."""

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    times = [datetime.fromisoformat(stamp) for stamp, _ in points]
    angles = [angle for _, angle in points]
    figure, axes = plt.subplots(figsize=(8, 3.2))
    if target is not None:
        axes.axhspan(
            target.minimum_deg,
            target.maximum_deg,
            color="green",
            alpha=0.12,
            label=(
                f"Demo Target Range: "
                f"{target.minimum_deg:.0f}°–{target.maximum_deg:.0f}°"
            ),
        )
    axes.plot(times, angles, marker="o", label="Your Elbow Angle")
    axes.set_ylabel("Elbow Angle (Degrees)")
    axes.set_title("Your Elbow Angles Over Time")
    axes.grid(True, alpha=0.3)
    axes.legend(loc="best")
    figure.autofmt_xdate()
    figure.tight_layout()
    st.pyplot(figure)
    plt.close(figure)


def progress_mode() -> None:
    """Show how the user's own saved measurements change over time."""

    st.caption(
        "Progress charts the elbow angles from your own saved analyses, "
        "oldest to newest, so you can see how your measured angles change "
        "over time. It is not a score or grade, and the target ranges are "
        "demonstration values, not coach-validated standards. Records are "
        "read from the same local history database the command-line tool "
        "uses; it stores measurements only, never photos or videos."
    )

    with st.sidebar:
        action = st.selectbox(
            "Stroke Type",
            options=ACTION_CHOICES,
            format_func=lambda value: ACTION_LABELS[value],
            key="progress_action",
        )

    try:
        connection = open_db()
        try:
            points = trend_points(connection, action)
            rows = list_records(connection, action=action, limit=20)
        finally:
            connection.close()
    except Exception:
        st.error("The local analysis history could not be opened.")
        return

    if len(points) < 2:
        st.info(
            "Progress appears after more analyses are saved. Analyze this "
            "stroke in Serve Photo Analysis or Stroke Video Analysis mode a "
            "few times, then "
            "come back — each saved measurement adds one point to the chart."
        )
    else:
        targets = _video_targets()
        target = targets.get(action) if targets is not None else None
        _render_progress_chart(points, target)

    if rows:
        st.markdown("**Most Recent Saved Analyses for This Stroke:**")
        table = []
        for row in rows:
            angle = row["angle_deg"]
            in_range = row["in_range"]
            table.append(
                {
                    "Date/Time (UTC)": row["recorded_at"].replace("T", " ")[:19],
                    "Angle": "n/a" if angle is None else f"{angle:.1f}°",
                    "In Target Range": (
                        "—" if in_range is None else ("Yes" if in_range else "No")
                    ),
                    "Analysis Result": row["main_issue_en"] or "—",
                }
            )
        st.table(table)


def main() -> None:
    st.title("🎾 Tennis360")

    with st.sidebar:
        st.header("Analysis Settings")
        mode = st.radio(
            "Analysis Type",
            options=("Serve photo", "Stroke video", "Progress"),
            format_func=lambda value: MODE_LABELS[value],
            help=(
                "Serve Photo Analysis checks one trophy-position still photo. "
                "Stroke Video Analysis analyzes a video clip of any supported stroke. "
                "Progress charts the angles from your saved analyses."
            ),
        )

    if mode == "Stroke video":
        stroke_video_mode()
        return

    if mode == "Progress":
        progress_mode()
        return

    st.caption(
        "Upload one serve photo. Tennis360 finds the shoulder, elbow, and wrist, "
        "estimates the racket-arm elbow angle in 3D, and shows a Green, Red, "
        "or Cannot Analyze result."
    )

    with st.sidebar:
        arm_label = st.radio("Arm to Inspect", options=tuple(ARM_CHOICES))
        arm = ARM_CHOICES[arm_label]
        if arm == "auto":
            st.caption(
                "At the trophy position, the tossing arm is straight and high while "
                "the racket arm is bent near shoulder height. Auto-detect uses that "
                "difference. Manual selection also checks the preparation position."
            )

        minimum, maximum = st.slider(
            "Target Elbow Range (Degrees)",
            min_value=40,
            max_value=180,
            value=(int(DEFAULT_TROPHY_MINIMUM), int(DEFAULT_TROPHY_MAXIMUM)),
            help="The result is Green when the measured angle falls inside this range.",
        )

        st.divider()
        st.caption(
            "One uploaded photo is processed in the local Python app. "
            "The photo itself is not saved or uploaded to a cloud service; "
            "a successful measurement is stored in the local history "
            "shown in Progress mode."
        )
        uploaded_file = st.file_uploader(
            "Upload a Trophy Pose Photo",
            type=("jpg", "jpeg", "png", "heic", "heif"),
            help="A clear JPEG, PNG, or HEIC (iPhone) photo with one person and both arms visible (max 10 MB).",
        )

    if uploaded_file is None:
        st.info(
            "Choose one JPEG, PNG, or HEIC photo from the sidebar to begin. A side-on shot "
            "of the trophy position — racket up, elbow bent, tossing arm extended — "
            "works best."
        )
        with st.expander("What This App Checks and Does Not Check"):
            st.markdown(
                """
**It checks one thing:** the racket-arm elbow angle at the serve trophy
position, measured from a single still photo.

**It refuses rather than guesses** when the arm is hidden, the player is too
small in the frame, the photo is not a trophy position, or repeat measurements
of the same photo do not agree.

**It is not** a full serve analysis, a video tracker, a coach, or a medical or
injury-prevention tool. The target range is a configurable demonstration value,
not a validated coaching or clinical standard.
"""
            )
        return

    try:
        image_rgb = decode_uploaded_image(uploaded_file.getvalue())
    except UploadedImageError as error:
        st.error(str(error))
        st.caption(
            "Choose another JPEG or PNG photo within the 10 MB upload and "
            "20 megapixel decode limits."
        )
        return

    try:
        with st.spinner("Finding pose landmarks locally…"):
            load_detector()
            annotated_image, report = analyze_rgb_image(
                image_rgb,
                arm,
                minimum_visibility=DEFAULT_MINIMUM_VISIBILITY,
                demo_minimum=float(minimum),
                demo_maximum=float(maximum),
            )
    except ModelFileMissingError as error:
        st.error("The local pose model is not installed yet.")
        st.code(str(error), language=None)
        st.caption("Run start.command or start.bat to install and verify the model, then reopen the app.")
        return
    except Exception:  # MediaPipe returns platform-specific runtime errors.
        st.error("The local pose analysis could not finish for this photo.")
        st.caption("Choose a clear JPEG or PNG with one visible person, then try again.")
        return

    display_image = fit_result_image(annotated_image)
    if report.focused_on_player:
        st.caption("A fixed local crop focuses the small player. The displayed image is this crop; cropping does not establish angle accuracy.")
    image_options = {"width": 480} if report.focused_on_player else {"use_container_width": True}

    if report.status == "cannot_analyze":
        st.warning(f"**Cannot Analyze.** {report.message}")
        st.caption(
            f"Reason: {report.reason_code}. No score was generated. "
            "Use a clear view of both arms at the preparation checkpoint."
        )
        st.image(display_image, **image_options)
        return

    if report.status == "analyzed" and report.angle_degrees is not None:
        _save_history_once(
            _photo_history_record(
                report,
                source_file=uploaded_file.name,
                requested_arm=arm,
                targets=_video_targets(),
            ),
            (
                "Serve photo",
                uploaded_file.name,
                uploaded_file.size,
                arm,
                int(minimum),
                int(maximum),
            ),
        )

    render_verdict(report, float(minimum), float(maximum))
    st.image(display_image, **image_options)
    render_measurement_detail(report)
    st.caption(
        "The target range is a configurable demonstration value, not a "
        "medically or professionally validated standard."
    )


if __name__ == "__main__":
    main()
