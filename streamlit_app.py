"""Streamlit entry point for Tennis360's local photo and video analysis."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from tennis360.annotate import POSE_CONNECTIONS
from tennis360.capture_time import (
    offset_timestamp,
    photo_capture_time,
    to_utc_iso,
    video_capture_time,
)
from tennis360.cli import ACTION_CHOICES, _issue_text
from tennis360.config import load_targets
from tennis360.history import (
    AnalysisRecord,
    delete_records,
    effective_time,
    list_records,
    open_db,
    record as save_history_record,
    record_attempt_numbers,
    record_ids_marked_for_deletion,
    trend_chart_axis,
    trend_points,
    utc_now_iso,
)
from tennis360.image_input import UploadedImageError, decode_uploaded_image
from tennis360.repetitions import (
    format_time_window,
    invalid_rep_result,
    render_stroke_diagrams,
    serve_rep_invalid_reason,
    serve_rep_record,
    swing_rep_invalid_reason,
)
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
from tennis360.video import (
    _detect_single,
    analyze_groundstroke_reps,
    analyze_serve_repetitions,
)

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

# The label of the one analysis button in Stroke Video Analysis mode,
# defined once here so it can be renamed in a single line.
ANALYZE_ALL_STROKES_LABEL = "Analyze All Strokes"

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


def _serve_target_range(targets) -> tuple[float, float]:
    """Serve target range (minimum, maximum) from targets or the defaults."""

    minimum = float(DEFAULT_TROPHY_MINIMUM)
    maximum = float(DEFAULT_TROPHY_MAXIMUM)
    if targets is not None:
        serve_target = targets.get("serve")
        if serve_target is not None:
            minimum = float(serve_target.minimum_deg)
            maximum = float(serve_target.maximum_deg)
    return minimum, maximum


def _photo_history_record(
    report,
    *,
    source_file: str,
    requested_arm: str,
    targets,
    captured_at: str | None = None,
) -> AnalysisRecord:
    """Build the history record for a serve-photo result, as the CLI does.

    ``captured_at`` is the photo's EXIF capture time (ISO UTC) when
    the photo carries one; the record's effective time point is then
    the moment the photo was taken, not the moment it was analyzed.
    """

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
        captured_at=captured_at,
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


def run_stroke_video_repetitions(uploaded_video, action: str, arm: str, selection_key) -> None:
    """Analyze EVERY repetition of the stroke in one practice video.

    Same temporary-copy discipline as the single analysis: the uploaded
    bytes exist on disk only for this run. Each successfully analyzed
    repetition is saved to the local history as its own record, tagged
    with its repetition number and its time in the video; repetitions
    that cannot be analyzed are listed but never saved.
    """

    suffix = Path(uploaded_video.name).suffix.lower()
    if suffix not in (".mp4", ".mov", ".m4v"):
        suffix = ".mp4"
    temp_path: str | None = None
    try:
        video_bytes = uploaded_video.getvalue()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(video_bytes)
            temp_path = handle.name
        # The video's own recording start, when the file carries one:
        # every record saved from this clip is timed from it (plus the
        # stroke's own time in the video), so the records belong to
        # the day the clip was filmed, not the day it was analyzed.
        capture_moment = video_capture_time(video_bytes)
        capture_start = (
            to_utc_iso(capture_moment) if capture_moment is not None else None
        )
        targets = _video_targets()
        rows: list[dict] = []
        candidates: list[dict] = []
        recorded = 0
        with st.spinner("Analyzing All Strokes Locally…"):
            if action == "serve":
                minimum, maximum = _serve_target_range(targets)
                reps = analyze_serve_repetitions(
                    temp_path, arm=arm, demo_minimum=minimum, demo_maximum=maximum
                )
                for rep in reps:
                    entry = serve_rep_record(
                        rep_index=rep.rep_index,
                        trophy_time_s=rep.trophy_time_s,
                        source_file=uploaded_video.name,
                        angle_degrees=rep.angle_degrees,
                        in_range=rep.in_range,
                        arm=rep.arm,
                        requested_arm=arm,
                        target_source=_target_source(targets, "serve"),
                        capture_start=capture_start,
                    )
                    if entry is not None:
                        _save_history_once(
                            entry,
                            ("Stroke video repetitions",)
                            + tuple(selection_key)
                            + (rep.rep_index, round(rep.trophy_time_s, 2)),
                        )
                        recorded += 1
                    rows.append(
                        {
                            "rep": rep.rep_index,
                            "time_s": rep.trophy_time_s,
                            "window_start_s": rep.segment_start_s,
                            "window_end_s": rep.segment_end_s,
                            "invalid": entry is None,
                            "angle": (
                                rep.angle_degrees
                                if entry is not None
                                else None
                            ),
                            "in_range": (
                                rep.in_range
                                if entry is not None
                                else None
                            ),
                            "result": (
                                entry.main_issue_en
                                if entry is not None
                                else invalid_rep_result(
                                    serve_rep_invalid_reason(rep.error)
                                )
                            ),
                        }
                    )
                    candidates.append(
                        {
                            "rep_index": rep.rep_index,
                            "analyzed": entry is not None,
                            "time_s": rep.trophy_time_s,
                            "arm": rep.arm,
                            "angle": (
                                rep.angle_degrees
                                if entry is not None
                                else None
                            ),
                            "minimum": minimum,
                            "maximum": maximum,
                            "moment": "at the trophy frame",
                            "window_start_s": rep.segment_start_s,
                            "window_end_s": rep.segment_end_s,
                        }
                    )
                found = len(reps)
            else:
                result = analyze_groundstroke_reps(
                    temp_path, action=action, arm=arm, targets=targets
                )
                target = targets.get(action) if targets is not None else None
                swing_minimum = (
                    float(target.minimum_deg) if target is not None else None
                )
                swing_maximum = (
                    float(target.maximum_deg) if target is not None else None
                )
                for rep, rep_analysis in zip(
                    result.rep_results, result.rep_analyses
                ):
                    if rep.analyzed and rep.metrics is not None:
                        entry = _swing_video_history_record(
                            rep_analysis,
                            source_file=uploaded_video.name,
                            action=action,
                            requested_arm=arm,
                            targets=targets,
                        )
                        if entry is not None:
                            entry.rep_index = rep.rep_index
                            entry.video_time_s = rep.contact_time_s
                            entry.captured_at = offset_timestamp(
                                capture_start, rep.contact_time_s
                            )
                            _save_history_once(
                                entry,
                                ("Stroke video repetitions",)
                                + tuple(selection_key)
                                + (
                                    rep.rep_index,
                                    round(rep.contact_time_s or 0.0, 2),
                                ),
                            )
                            recorded += 1
                        rows.append(
                            {
                                "rep": rep.rep_index,
                                "time_s": rep.contact_time_s,
                                "window_start_s": rep.window_start_s,
                                "window_end_s": rep.window_end_s,
                                "invalid": False,
                                "angle": rep.metrics.contact_elbow_deg,
                                "in_range": rep.metrics.contact_elbow_in_range,
                                "result": (
                                    rep.suggestions[0]
                                    if rep.suggestions
                                    else "Angle in Range"
                                ),
                            }
                        )
                        candidates.append(
                            {
                                "rep_index": rep.rep_index,
                                "analyzed": True,
                                "time_s": rep.contact_time_s,
                                "arm": result.arm,
                                "angle": rep.metrics.contact_elbow_deg,
                                "minimum": swing_minimum,
                                "maximum": swing_maximum,
                                "moment": "at contact",
                                "window_start_s": rep.window_start_s,
                                "window_end_s": rep.window_end_s,
                            }
                        )
                    else:
                        rows.append(
                            {
                                "rep": rep.rep_index,
                                "time_s": rep.peak_time_s,
                                "window_start_s": rep.window_start_s,
                                "window_end_s": rep.window_end_s,
                                "invalid": True,
                                "angle": None,
                                "in_range": None,
                                "result": invalid_rep_result(
                                    swing_rep_invalid_reason(rep)
                                ),
                            }
                        )
                        candidates.append(
                            {
                                "rep_index": rep.rep_index,
                                "analyzed": False,
                                "time_s": rep.peak_time_s,
                                "arm": None,
                                "angle": None,
                                "minimum": swing_minimum,
                                "maximum": swing_maximum,
                                "moment": "at contact",
                                "window_start_s": rep.window_start_s,
                                "window_end_s": rep.window_end_s,
                            }
                        )
                found = len(result.rep_results)
        diagrams = []
        for rep_index, png in render_stroke_diagrams(
            candidates,
            lambda time_s: _extract_frame_landmarks(temp_path, time_s),
            build_skeleton_diagram_png,
        ):
            candidate = next(
                item for item in candidates if item["rep_index"] == rep_index
            )
            diagrams.append(
                {
                    "rep": rep_index,
                    "png": png,
                    "caption": (
                        f"Stroke {rep_index} — "
                        + format_time_window(
                            candidate["window_start_s"],
                            candidate["window_end_s"],
                        )
                    ),
                    "note": _diagram_caption(candidate),
                }
            )
        st.session_state["stroke_video_reps_result"] = {
            "key": selection_key,
            "data": {
                "kind": "serve" if action == "serve" else "swing",
                "action": action,
                "rows": rows,
                "found": found,
                "recorded": recorded,
                "invalid": found - recorded,
                "diagrams": diagrams,
            },
        }
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


def render_reps_result(data: dict) -> None:
    """Show the per-stroke list for a multi-stroke analysis."""

    st.markdown("**All Detected Strokes in This Video:**")
    st.caption(
        f"Strokes Detected: {data['found']} | Successfully Analyzed: "
        f"{data['recorded']}"
    )
    st.caption(
        "Each stroke is numbered by its order in the video, whether or "
        "not it could be analyzed. Successfully analyzed strokes are "
        "recorded to Progress. "
        f"Invalid and skipped (not recorded): {data['invalid']}. "
        "Strokes that could not be analyzed are listed with the reason "
        "and blank measurements; they are never saved to Progress. "
        "Reanalyzing the same video will not create duplicate records."
    )
    if not data["rows"]:
        st.warning(
            "**No Strokes Detected.** The sampled frames do not show a "
            "repeated swing of the selected stroke."
        )
        return
    time_label = (
        "Trophy Frame Time" if data["kind"] == "serve" else "Contact Time"
    )
    table = []
    for row in data["rows"]:
        window_start = row.get("window_start_s")
        window_end = row.get("window_end_s")
        if window_start is not None and window_end is not None:
            window_text = format_time_window(window_start, window_end)
        elif row["time_s"] is not None:
            window_text = f"{row['time_s']:.1f} s"
        else:
            window_text = "n/a"
        table.append(
            {
                "Stroke": row["rep"],
                time_label: (
                    "n/a" if row["time_s"] is None else f"{row['time_s']:.2f} s"
                ),
                "Time in Video": window_text,
                "Elbow Angle": (
                    ""
                    if row["invalid"]
                    else (
                        "n/a"
                        if row["angle"] is None
                        else f"{row['angle']:.1f}°"
                    )
                ),
                "In Target Range": (
                    ""
                    if row["invalid"]
                    else (
                        "—"
                        if row["in_range"] is None
                        else ("Yes" if row["in_range"] else "No")
                    )
                ),
                "Analysis Result": row["result"],
            }
        )
    st.table(table)
    for diagram in data.get("diagrams", []):
        st.image(diagram["png"], caption=diagram["caption"], width=420)
        st.caption(diagram["note"])
    st.caption(
        "Key-moment times are estimates from the wrist path. They are not "
        "exact contact frames. The target range is a configurable "
        "demonstration value, not a medically or professionally validated "
        "standard."
    )


def stroke_video_mode() -> None:
    """Analyze one uploaded clip of any supported stroke, in the browser UI."""

    st.caption(
        "Each uploaded video may contain multiple strokes of the selected "
        "type. Tennis360 identifies individual strokes and analyzes each "
        f"one separately: {ANALYZE_ALL_STROKES_LABEL} measures every "
        "stroke in the clip and records each successfully analyzed "
        "stroke in Progress."
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
            help="One clip of a single stroke, or a practice clip repeating the same stroke (MP4, MOV, or M4V, max 200 MB).",
        )

    if uploaded_video is None:
        st.info(
            "Choose one stroke video from the sidebar, pick the stroke type and arm, "
            "then run the analysis. A side-on clip of one full stroke works best."
        )
        return

    st.write(f"**Selected Clip:** {uploaded_video.name}")
    selection_key = (uploaded_video.name, uploaded_video.size, action, arm)
    button_column, _ = st.columns(2)
    if button_column.button(ANALYZE_ALL_STROKES_LABEL):
        run_stroke_video_repetitions(uploaded_video, action, arm, selection_key)

    stored_reps = st.session_state.get("stroke_video_reps_result")
    if stored_reps is not None and stored_reps["key"] == selection_key:
        render_reps_result(stored_reps["data"])
    elif stored_reps is not None:
        st.caption(
            "The clip, stroke type, or arm changed — click "
            f"{ANALYZE_ALL_STROKES_LABEL} to run the analysis again."
        )


def _render_progress_chart(points, target) -> None:
    """Plot saved angles by attempt number, with the demo target band.

    The x-axis counts attempts (1, 2, 3, ...) at exactly equal spacing
    in effective-time order, oldest to newest — the spacing between consecutive
    attempts is uniform everywhere, always, so more attempts simply
    make the chart denser. Dates appear only in a label row under the
    axis, grouped into sections (days, weeks, months, or years — the
    finest unit that keeps the section count at or below 15); a
    section label is centered under its section's span and never moves
    a point. With at most 15 points every point is also labeled with
    its angle; with more than 60 points the markers are dropped so the
    chart reads as one clean line instead of a dotted blur.
    """

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chart_axis = trend_chart_axis(points)
    figure, axes = plt.subplots(figsize=(8, 3.6))
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
    axes.plot(
        chart_axis.positions,
        chart_axis.angles,
        marker="o" if chart_axis.show_markers else None,
        label="Your Elbow Angle",
    )
    for position, angle, text in zip(
        chart_axis.positions, chart_axis.angles, chart_axis.value_labels
    ):
        axes.annotate(
            text,
            (position, angle),
            textcoords="offset points",
            xytext=(0, 6),
            ha="center",
            fontsize=8,
        )
    axes.set_xticks(chart_axis.tick_positions)
    axes.set_xticklabels(chart_axis.tick_labels)
    for section in chart_axis.sections:
        axes.text(
            section.center,
            -0.32,
            section.label,
            transform=axes.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=9,
            clip_on=False,
        )
    axes.set_xlabel("Attempt")
    axes.set_ylabel("Elbow Angle (Degrees)")
    axes.set_title("Your Elbow Angles by Attempt")
    axes.grid(True, alpha=0.3)
    axes.legend(loc="best")
    figure.tight_layout()
    figure.subplots_adjust(bottom=0.30)
    st.pyplot(figure)
    plt.close(figure)


def _progress_record_editor_rows(rows, attempt_numbers) -> list[dict]:
    """Build the editable display rows for the saved records of one stroke.

    Each row carries the record's stable id (hidden in the editor) beside
    a Delete checkbox, so the user's marks can be mapped back to exactly
    the records she chose; the visible columns match the previous static
    table, plus the record's time in its source video when it has one.
    The Attempt column comes from ``attempt_numbers`` — the same
    ordered record set the trend chart plots — so a record carries the
    same number in the table and on the chart; a record without a
    measured angle is not charted and shows "—" instead of a number.
    Attempt is the only numbering shown: the per-video stroke number
    is not repeated here. The Date/Time column shows the record's one
    effective time point — its capture time when the source photo or
    video carries one, else the time the analysis was saved.
    """

    editor_rows = []
    for row in rows:
        angle = row["angle_deg"]
        in_range = row["in_range"]
        video_time = (
            row["video_time_s"] if "video_time_s" in row.keys() else None
        )
        captured_at = (
            row["captured_at"] if "captured_at" in row.keys() else None
        )
        stamp = effective_time(row["recorded_at"], captured_at)
        attempt = attempt_numbers.get(int(row["id"]))
        editor_rows.append(
            {
                "Delete": False,
                "Record ID": int(row["id"]),
                "Attempt": "—" if attempt is None else str(attempt),
                "Date/Time (UTC)": stamp.replace("T", " ")[:19],
                "Angle": "n/a" if angle is None else f"{angle:.1f}°",
                "In Target Range": (
                    "—" if in_range is None else ("Yes" if in_range else "No")
                ),
                "Video Time": (
                    "—" if video_time is None else f"{video_time:.1f} s"
                ),
                "Analysis Result": row["main_issue_en"] or "—",
            }
        )
    return editor_rows


def _render_progress_records(rows, action: str, attempt_numbers) -> None:
    """Show one stroke's saved records, with selective deletion.

    Deletion is a two-step action on purpose: marking records and
    clicking Delete only arms the confirmation; the records are removed
    (permanently) when the user confirms. Unmarked records are never
    touched.
    """

    st.markdown("**Most Recent Saved Analyses for This Stroke:**")

    notice_key = f"progress_delete_notice_{action}"
    notice = st.session_state.pop(notice_key, None)
    if notice:
        st.success(notice)

    edited = st.data_editor(
        _progress_record_editor_rows(rows, attempt_numbers),
        key=f"progress_record_editor_{action}",
        hide_index=True,
        disabled=[
            "Record ID",
            "Attempt",
            "Date/Time (UTC)",
            "Angle",
            "In Target Range",
            "Video Time",
            "Analysis Result",
        ],
        column_config={
            "Delete": st.column_config.CheckboxColumn(
                "Delete", default=False
            ),
            "Record ID": None,
        },
    )
    edited_rows = (
        edited.to_dict("records")
        if hasattr(edited, "to_dict")
        else list(edited)
    )
    selected_ids = record_ids_marked_for_deletion(
        {
            "record_id": edited_row.get("Record ID"),
            "delete": bool(edited_row.get("Delete")),
        }
        for edited_row in edited_rows
    )
    selected = len(selected_ids)

    arm_key = f"progress_delete_armed_{action}"
    if not st.session_state.get(arm_key, False):
        if st.button(
            "Delete Selected Records"
            + (f" ({selected})" if selected else ""),
            disabled=selected == 0,
            key=f"progress_delete_button_{action}",
        ):
            st.session_state[arm_key] = True
            st.rerun()
        if selected == 0:
            st.caption(
                "Tick the Delete box beside each record you no longer "
                "want to keep, then use this button. Unmarked records "
                "stay."
            )
        return

    if selected == 0:
        st.session_state[arm_key] = False
        st.rerun()
        return

    st.warning(
        f"Delete {selected} selected record(s)? This cannot be undone. "
        "The chart and this table will then show only the records that "
        "remain."
    )
    confirm_column, cancel_column = st.columns(2)
    if confirm_column.button(
        f"Confirm Delete ({selected})",
        key=f"progress_delete_confirm_{action}",
    ):
        try:
            connection = open_db()
            try:
                deleted = delete_records(connection, selected_ids)
            finally:
                connection.close()
        except Exception:
            st.session_state[arm_key] = False
            st.error("The selected records could not be deleted.")
            return
        st.session_state[arm_key] = False
        st.session_state[notice_key] = (
            f"Deleted {deleted} record(s). The records that remain are "
            "unchanged."
        )
        st.rerun()
    if cancel_column.button(
        "Cancel", key=f"progress_delete_cancel_{action}"
    ):
        st.session_state[arm_key] = False
        st.rerun()


def progress_mode() -> None:
    """Show how the user's own saved measurements change per attempt."""

    st.caption(
        "Progress charts the elbow angles from your own saved analyses, "
        "oldest to newest: each point is one saved attempt, numbered "
        "along the axis in time order — each record's time point is "
        "the moment its photo or video was recorded when the file "
        "carries a recording time, and the moment the analysis was "
        "saved otherwise — grouped underneath "
        "into date sections (days, weeks, months, or years — the "
        "finest grouping that keeps the number of sections at or "
        "below 15), so you can see how your measured angles change "
        "from attempt to attempt. The records table below numbers each "
        "record with the same Attempt value the chart plots for it. "
        "It is not a score or grade, and the "
        "target ranges are demonstration values, not coach-validated "
        "standards. Records are read from the same local history "
        "database the command-line tool uses; it stores measurements "
        "only, never photos or videos."
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
            rows = list_records(connection, action=action)
            attempt_numbers = record_attempt_numbers(connection, action)
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
        _render_progress_records(rows, action, attempt_numbers)


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

    uploaded_bytes = uploaded_file.getvalue()
    # The photo's EXIF capture time, when it carries one: the history
    # record is then timed at the moment the photo was taken.
    photo_moment = photo_capture_time(uploaded_bytes)
    photo_captured_at = (
        to_utc_iso(photo_moment) if photo_moment is not None else None
    )

    try:
        image_rgb = decode_uploaded_image(uploaded_bytes)
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
                captured_at=photo_captured_at,
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
