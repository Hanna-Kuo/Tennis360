"""Local cross-day analysis history.

Results (numbers and verdicts, never photo bytes) are stored in a SQLite
database on the user's own computer. This is the desktop counterpart to the
web app's export/import workflow: here persistence is allowed because it is a
local program the user runs themselves.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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
    target_source TEXT NOT NULL DEFAULT 'demo'
);
"""


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


def open_db(path: str | Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the local history database."""

    db_path = Path(path) if path is not None else DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.executescript(_SCHEMA)
    return connection


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(connection: sqlite3.Connection, entry: AnalysisRecord) -> int:
    """Insert one analysis record; returns the new row id."""

    cursor = connection.execute(
        """
        INSERT INTO analyses (
            recorded_at, source_file, action, camera_angle, arm,
            angle_deg, in_range, confidence, spread_deg,
            main_issue_zh, main_issue_en, target_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def list_records(
    connection: sqlite3.Connection,
    *,
    action: str | None = None,
    limit: int = 200,
) -> list[sqlite3.Row]:
    """Return stored records newest-first, optionally filtered by action."""

    if action:
        rows = connection.execute(
            "SELECT * FROM analyses WHERE action = ? ORDER BY recorded_at DESC LIMIT ?",
            (action, limit),
        )
    else:
        rows = connection.execute(
            "SELECT * FROM analyses ORDER BY recorded_at DESC LIMIT ?", (limit,)
        )
    return list(rows.fetchall())


def trend_points(
    connection: sqlite3.Connection, action: str
) -> list[tuple[str, float]]:
    """Return (recorded_at, angle_deg) pairs oldest-first for trend charts."""

    rows = connection.execute(
        """
        SELECT recorded_at, angle_deg FROM analyses
        WHERE action = ? AND angle_deg IS NOT NULL
        ORDER BY recorded_at ASC
        """,
        (action,),
    )
    return [(row["recorded_at"], float(row["angle_deg"])) for row in rows.fetchall()]
