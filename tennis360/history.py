"""Local cross-day analysis history.

Results (numbers and verdicts, never photo bytes) are stored in a SQLite
database on the user's own computer. This is the desktop counterpart to the
web app's export/import workflow: here persistence is allowed because it is a
local program the user runs themselves.

Every record carries two timestamps: ``recorded_at``, when the analysis
was saved, and ``captured_at``, when its source photo or video was
recorded (read from the file's own metadata by capture_time.py; NULL
when the file carries no recording time). A record's one effective
time point — see effective_time() — is the capture time when present
and the save time otherwise, and it drives everything: attempt
numbering, trend ordering and chart sections, and the Progress table's
sort and displayed date/time all read the same effective time, so a
video filmed on Saturday and analyzed on Monday belongs to Saturday
in every view.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".tennis360" / "history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    source_file TEXT NOT NULL,
    action TEXT NOT NULL,
    camera_angle TEXT NOT NULL DEFAULT '',
    arm TEXT NOT NULL DEFAULT '',
    angle_deg REAL,
    in_range INTEGER,
    confidence TEXT NOT NULL DEFAULT '',
    spread_deg REAL,
    main_issue_zh TEXT NOT NULL DEFAULT '',
    main_issue_en TEXT NOT NULL DEFAULT '',
    target_source TEXT NOT NULL DEFAULT 'demo',
    rep_index INTEGER,
    video_time_s REAL
);
"""

# Columns added after the first release; databases created earlier are
# migrated in place by open_db() so old and new records share one table.
_ADDED_COLUMNS = {
    "rep_index": "INTEGER",
    "video_time_s": "REAL",
    "captured_at": "TEXT",
}


@dataclass
class AnalysisRecord:
    """One stored analysis result (no image data)."""

    recorded_at: str  # ISO 8601
    source_file: str
    action: str  # e.g. "serve", "forehand", "backhand"
    camera_angle: str = ""  # e.g. "side", "front"
    arm: str = ""
    angle_deg: float | None = None
    in_range: bool | None = None
    confidence: str = ""
    spread_deg: float | None = None
    main_issue_zh: str = ""
    main_issue_en: str = ""
    target_source: str = "demo"
    # Multi-repetition analyses only: which repetition of the source video
    # this record came from (1-based) and when its key moment occurs in the
    # video. Both stay None for single analyses, so several records from one
    # video remain distinguishable without changing single-record behavior.
    rep_index: int | None = None
    video_time_s: float | None = None
    # When the source photo or video was recorded, as an ISO 8601 UTC
    # timestamp read from the file's own metadata, or None when the file
    # carries no recording time. For a repetition record this is the
    # video's recording start plus the repetition's time in the video,
    # so repetitions of one clip keep their true hit order. When present
    # it — not recorded_at — is the record's effective time point.
    captured_at: str | None = None


def open_db(path: str | Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the local history database."""

    db_path = Path(path) if path is not None else DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.executescript(_SCHEMA)
    existing = {
        row[1] for row in connection.execute("PRAGMA table_info(analyses)")
    }
    for column, column_type in _ADDED_COLUMNS.items():
        if column not in existing:
            connection.execute(
                f"ALTER TABLE analyses ADD COLUMN {column} {column_type}"
            )
    connection.commit()
    return connection


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def effective_time(recorded_at: str, captured_at: str | None) -> str:
    """Return a record's one effective time point, as an ISO string.

    The capture time wins when the record has one; the save time is
    the fallback. Every ordering and display of a record — attempt
    numbering, the trend chart and its date sections, the Progress
    table — goes through this rule (in SQL as ``COALESCE(captured_at,
    recorded_at)``), so no view computes a different time for the
    same record.
    """

    return captured_at if captured_at else recorded_at


def record(connection: sqlite3.Connection, entry: AnalysisRecord) -> int:
    """Insert one analysis record; returns the new row id."""

    cursor = connection.execute(
        """
        INSERT INTO analyses (
            recorded_at, source_file, action, camera_angle, arm,
            angle_deg, in_range, confidence, spread_deg,
            main_issue_zh, main_issue_en, target_source,
            rep_index, video_time_s, captured_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.recorded_at,
            entry.source_file,
            entry.action,
            entry.camera_angle,
            entry.arm,
            entry.angle_deg,
            None if entry.in_range is None else int(entry.in_range),
            entry.confidence,
            entry.spread_deg,
            entry.main_issue_zh,
            entry.main_issue_en,
            entry.target_source,
            entry.rep_index,
            entry.video_time_s,
            entry.captured_at,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def delete_records(
    connection: sqlite3.Connection, record_ids
) -> int:
    """Delete saved records by id; returns how many rows were removed.

    Only the listed ids are removed. Ids that match no stored record are
    ignored, so a selection gathered earlier can be passed as-is; an
    empty selection changes nothing and returns 0.
    """

    unique_ids: list[int] = []
    seen: set[int] = set()
    for value in record_ids:
        try:
            record_id = int(value)
        except (TypeError, ValueError):
            continue
        if record_id not in seen:
            seen.add(record_id)
            unique_ids.append(record_id)
    if not unique_ids:
        return 0
    placeholders = ", ".join("?" for _ in unique_ids)
    cursor = connection.execute(
        f"DELETE FROM analyses WHERE id IN ({placeholders})", unique_ids
    )
    connection.commit()
    return int(cursor.rowcount)


def record_ids_marked_for_deletion(rows) -> list[int]:
    """Return the record ids whose row is marked for deletion.

    ``rows`` is an iterable of plain mappings as produced by the Progress
    table editor: each carries a ``record_id`` and a boolean ``delete``
    flag. Rows without the flag count as unmarked; ids keep their row
    order and duplicates collapse, matching delete_records().
    """

    marked: list[int] = []
    seen: set[int] = set()
    for row in rows:
        if not row.get("delete"):
            continue
        record_id = row.get("record_id")
        if record_id is None:
            continue
        record_id = int(record_id)
        if record_id not in seen:
            seen.add(record_id)
            marked.append(record_id)
    return marked


def list_records(
    connection: sqlite3.Connection,
    *,
    action: str | None = None,
    limit: int = 200,
) -> list[sqlite3.Row]:
    """Return stored records newest-first, optionally filtered by action.

    Newest-first is by each record's effective time point (capture
    time when present, else save time), the same time the Progress
    table displays; the row id breaks same-instant ties so the order
    is the exact reverse of the trend order.
    """

    if action:
        rows = connection.execute(
            "SELECT * FROM analyses WHERE action = ? "
            "ORDER BY COALESCE(captured_at, recorded_at) DESC, id DESC "
            "LIMIT ?",
            (action, limit),
        )
    else:
        rows = connection.execute(
            "SELECT * FROM analyses "
            "ORDER BY COALESCE(captured_at, recorded_at) DESC, id DESC "
            "LIMIT ?",
            (limit,),
        )
    return list(rows.fetchall())


def trend_records(
    connection: sqlite3.Connection, action: str
) -> list[sqlite3.Row]:
    """Return the stroke's charted records oldest-first.

    This ordered set is the single source of truth behind Progress:
    the trend chart plots these records (via trend_points) and the
    records table numbers them (via record_attempt_numbers), so a
    record's attempt number is the same in both places by
    construction. Only records with a measured angle are charted;
    ordering is by each record's effective time point (its capture
    time when the source carries one, else its save time) with the
    row id breaking same-instant ties (one analysis run can save
    several records within the same second), so the order is total
    and stable. The returned ``recorded_at`` value IS the effective
    time point, so every consumer downstream — chart sections
    included — reads the one time point without recomputing it.
    """

    rows = connection.execute(
        """
        SELECT id, COALESCE(captured_at, recorded_at) AS recorded_at,
               angle_deg
        FROM analyses
        WHERE action = ? AND angle_deg IS NOT NULL
        ORDER BY COALESCE(captured_at, recorded_at) ASC, id ASC
        """,
        (action,),
    )
    return list(rows.fetchall())


def trend_points(
    connection: sqlite3.Connection, action: str
) -> list[tuple[str, float]]:
    """Return (effective time, angle_deg) pairs oldest-first for charts.

    The timestamp is the record's effective time point: its capture
    time when the source photo or video carries one, else the time
    the analysis was saved.
    """

    return [
        (row["recorded_at"], float(row["angle_deg"]))
        for row in trend_records(connection, action)
    ]


def record_attempt_numbers(
    connection: sqlite3.Connection, action: str
) -> dict[int, int]:
    """Map each charted record's id to its Progress attempt number.

    The attempt number is the record's 1-based position in
    trend_records() — the same ordered set the trend chart plots — so
    the number beside a record in the Progress table is exactly the
    number the chart plots for it. Records without a measured angle
    are not charted and have no entry. Because the mapping is
    recomputed from the surviving records, a deletion renumbers the
    chart and the table together.
    """

    return {
        int(row["id"]): position
        for position, row in enumerate(
            trend_records(connection, action), start=1
        )
    }


@dataclass
class TrendSection:
    """One date section of the Progress chart's bottom label row.

    A section groups consecutive attempts whose records fall in the
    same calendar unit (day, week, month, or year — see
    trend_chart_axis). ``start_position`` / ``end_position`` are the
    1-based attempt positions of the section's first and last points
    and ``center`` is the x coordinate the section's label is drawn
    at. Sections only label the axis; they never move a point.
    """

    unit: str = ""
    label: str = ""
    start_position: int = 0
    end_position: int = 0
    center: float = 0.0


@dataclass
class TrendAxis:
    """Ordinal x-axis data for the Progress trend chart.

    ``positions`` holds strictly uniform x coordinates, one per trend
    point (1..N in effective-time order) — the spacing between consecutive
    attempts is exactly equal everywhere, always — and ``angles`` the
    matching y values. ``tick_positions`` / ``tick_labels`` give the
    labeled attempt-number ticks. ``sections`` describes the date
    label row drawn under the axis: one label per date section,
    centered under that section's span. ``value_labels`` holds one
    formatted angle per point when the chart is small enough to label
    every point, and is empty otherwise. ``show_markers`` says whether
    the points are drawn with markers or as one clean line only.
    """

    positions: list[int] = field(default_factory=list)
    angles: list[float] = field(default_factory=list)
    tick_positions: list[int] = field(default_factory=list)
    tick_labels: list[str] = field(default_factory=list)
    sections: list[TrendSection] = field(default_factory=list)
    value_labels: list[str] = field(default_factory=list)
    show_markers: bool = True


# Section units, finest first. The chart uses the first unit whose
# grouping of the records yields at most MAX_TREND_SECTIONS sections.
SECTION_UNITS = ("day", "week", "month", "year")
MAX_TREND_SECTIONS = 15
MAX_VALUE_LABEL_POINTS = 15
MAX_MARKER_POINTS = 60


def _record_date(recorded_at: str) -> date | None:
    """Parse the calendar date of an ISO timestamp, or None."""

    try:
        return datetime.fromisoformat(recorded_at).date()
    except ValueError:
        try:
            return datetime.strptime(recorded_at[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _section_key_label(unit: str, day: date) -> tuple[tuple, str]:
    """Return the grouping key and bottom-row label for one date.

    Weeks are calendar weeks starting on Monday; the label names the
    Monday the week starts ("Week of 10-26"). A partial week at
    either end of the record set is still one section.
    """

    if unit == "day":
        key = (day.year, day.month, day.day)
        return key, f"{day.month:02d}-{day.day:02d}"
    if unit == "week":
        monday = day - timedelta(days=day.weekday())
        key = (monday.year, monday.month, monday.day)
        return key, f"Week of {monday.month:02d}-{monday.day:02d}"
    if unit == "month":
        return (day.year, day.month), f"{day.year}-{day.month:02d}"
    return (day.year,), f"{day.year}"


def _group_sections(
    dates: list[date | None], stamps: list[str], unit: str
) -> list[TrendSection]:
    """Group consecutive points into sections of one calendar unit.

    Points arrive in effective-time order (oldest first), so equal keys are
    consecutive and each run of one key is one section. A point whose
    timestamp cannot be parsed falls back to a day key built from its
    raw text, so it still groups with its neighbours.
    """

    sections: list[TrendSection] = []
    current_key: tuple | None = None
    for index, day in enumerate(dates):
        if day is not None:
            key, label = _section_key_label(unit, day)
        else:
            key = ("raw", stamps[index][:10])
            label = stamps[index][5:10]
        position = index + 1
        if sections and key == current_key:
            sections[-1].end_position = position
            sections[-1].center = (
                sections[-1].start_position + position
            ) / 2
        else:
            sections.append(
                TrendSection(
                    unit=unit,
                    label=label,
                    start_position=position,
                    end_position=position,
                    center=float(position),
                )
            )
            current_key = key
    return sections


def trend_chart_axis(
    points: Sequence[tuple[str, float]],
    *,
    max_attempt_labels: int = 30,
    max_sections: int = MAX_TREND_SECTIONS,
    max_value_label_points: int = MAX_VALUE_LABEL_POINTS,
    max_marker_points: int = MAX_MARKER_POINTS,
) -> TrendAxis:
    """Map trend points to an attempt-number x-axis with date sections.

    The Progress chart numbers the saved analyses 1, 2, 3, ... in
    effective-time order (oldest first) at exactly equal spacing — the spacing
    between consecutive attempts is uniform everywhere, always, so
    more attempts simply make the chart denser. Record dates never
    drive the spacing.

    Dates appear only in the label row under the axis, grouped into
    sections. The section unit is chosen by section count, not by
    calendar span: the finest unit (day, then week, then month, then
    year) whose grouping yields at most ``max_sections`` sections
    wins, so a handful of attempts keeps one labelled day section per
    practice day however far apart they are, while long daily streaks
    roll up into weeks, then months, then years. Weeks are calendar
    weeks starting on Monday.

    When there are too many points to label every attempt tick, the
    attempt labels thin out (at most ``max_attempt_labels``, plus the
    final point). With at most ``max_value_label_points`` points each
    point also carries its angle as a value label; with more than
    ``max_marker_points`` points the markers are dropped so the chart
    reads as one clean line instead of a dotted blur.
    """

    count = len(points)
    if count == 0:
        return TrendAxis(show_markers=True)

    attempt_stride = max(1, -(-count // max_attempt_labels))
    tick_indexes = list(range(0, count, attempt_stride))
    if tick_indexes[-1] != count - 1:
        tick_indexes.append(count - 1)

    stamps = [stamp for stamp, _ in points]
    dates = [_record_date(stamp) for stamp in stamps]
    sections: list[TrendSection] = []
    for unit in SECTION_UNITS:
        sections = _group_sections(dates, stamps, unit)
        if len(sections) <= max_sections or unit == SECTION_UNITS[-1]:
            break

    angles = [float(angle) for _, angle in points]
    value_labels = (
        [f"{angle:.1f}°" for angle in angles]
        if count <= max_value_label_points
        else []
    )

    return TrendAxis(
        positions=list(range(1, count + 1)),
        angles=angles,
        tick_positions=[index + 1 for index in tick_indexes],
        tick_labels=[str(index + 1) for index in tick_indexes],
        sections=sections,
        value_labels=value_labels,
        show_markers=count <= max_marker_points,
    )
