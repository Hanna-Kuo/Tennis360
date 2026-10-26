"""Exports and visualizations for the desktop deep-analysis workflow.

- Excel/CSV reports with English headers;
- angle trend charts with the demonstration target band;
- 2D/3D wrist-trajectory plots from video frame data.

All user-visible output is English-only, matching the mobile Live app.
All target bands are labeled as demonstration references, never as
validated coaching or biomechanical standards.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

REPORT_COLUMNS = [
    ("recorded_at", "Date/Time"),
    ("source_file", "Source File"),
    ("action", "Action"),
    ("camera_angle", "Camera Angle"),
    ("arm", "Arm"),
    ("angle_deg", "Angle (°)"),
    ("in_range", "In Target Range"),
    ("confidence", "Confidence"),
    ("main_issue", "Analysis Result"),
    ("target_source", "Target Source"),
]


def _rows_to_frame(rows: Sequence[Mapping]) -> "object":
    import pandas as pd

    records = []
    for row in rows:
        mapping = dict(row)
        issue = mapping.get("main_issue_en") or ""
        records.append(
            {
                # The record's effective time point: its capture time
                # when the source carries one, else its save time —
                # the same time every other view shows.
                "Date/Time": mapping.get("captured_at")
                or mapping.get("recorded_at", ""),
                "Source File": mapping.get("source_file", ""),
                "Action": str(mapping.get("action", "")),
                "Camera Angle": mapping.get("camera_angle", ""),
                "Arm": mapping.get("arm", ""),
                "Angle (°)": mapping.get("angle_deg", ""),
                "In Target Range": (
                    ""
                    if mapping.get("in_range") is None
                    else ("Yes" if mapping.get("in_range") else "No")
                ),
                "Confidence": mapping.get("confidence", ""),
                "Analysis Result": issue,
                "Target Source": mapping.get("target_source", "demo"),
            }
        )
    return pd.DataFrame(records, columns=[header for _, header in REPORT_COLUMNS])


def export_excel(rows: Sequence[Mapping], path: str | Path) -> str:
    """Write analysis records to .xlsx with English headers."""

    destination = str(path)
    frame = _rows_to_frame(rows)
    frame.to_excel(destination, index=False, engine="openpyxl")
    return destination


def export_csv(rows: Sequence[Mapping], path: str | Path) -> str:
    """Write analysis records to .csv with English headers (UTF-8)."""

    destination = str(path)
    frame = _rows_to_frame(rows)
    frame.to_csv(destination, index=False, encoding="utf-8")
    return destination


def plot_trend(
    points: Sequence[tuple[str, float]],
    path: str | Path,
    *,
    target_min: float,
    target_max: float,
    action_label: str = "serve",
    target_source: str = "demo",
) -> str:
    """Plot angle-over-time with the demonstration target band shaded.

    ``points`` are (ISO datetime, angle) pairs oldest-first.
    """

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import dates as mdates

    destination = str(path)
    fig, axis = plt.subplots(figsize=(10, 5))

    if points:
        datetimes = [p[0] for p in points]
        angles = [p[1] for p in points]
        axis.plot(datetimes, angles, marker="o", label="Angle (°)")
        axis.axhspan(
            target_min,
            target_max,
            color="green",
            alpha=0.15,
            label=(
                f"Demo Target Range {target_min:.0f}°–{target_max:.0f}° "
                f"({target_source})"
            ),
        )
    else:
        axis.text(0.5, 0.5, "No data", ha="center", va="center")

    axis.set_title(f"Angle Trend — {action_label}")
    axis.set_xlabel("Date")
    axis.set_ylabel("Angle (°)")
    axis.legend()
    fig.autofmt_xdate()
    try:
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    except Exception:
        pass
    fig.tight_layout()
    fig.savefig(destination, dpi=120)
    plt.close(fig)
    return destination


def plot_trajectory(
    points: Sequence[tuple[float, object]],
    path: str | Path,
    *,
    three_d: bool = False,
) -> str:
    """Plot the wrist path over time from per-frame world landmarks.

    ``points`` are (time_s, Point3 wrist) pairs. Axes are labeled neutrally;
    the plot shows the shape of the swing path, not an absolute orientation.
    """

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    destination = str(path)
    times = [p[0] for p in points]
    xs = [p[1].x for p in points]
    ys = [p[1].y for p in points]

    if three_d:
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

        zs = [p[1].z for p in points]
        fig = plt.figure(figsize=(8, 6))
        axis = fig.add_subplot(111, projection="3d")
        scatter = axis.scatter(xs, ys, zs, c=times, cmap="viridis")
        axis.set_xlabel("X (m)")
        axis.set_ylabel("Y (m)")
        axis.set_zlabel("Z (m)")
        fig.colorbar(scatter, label="Time (s)")
    else:
        fig, axis = plt.subplots(figsize=(8, 6))
        scatter = axis.scatter(xs, ys, c=times, cmap="viridis")
        axis.set_xlabel("X (m)")
        axis.set_ylabel("Y (m)")
        axis.set_aspect("equal", adjustable="datalim")
        fig.colorbar(scatter, label="Time (s)")

    axis.set_title("Wrist Swing Trajectory")
    fig.tight_layout()
    fig.savefig(destination, dpi=120)
    plt.close(fig)
    return destination
