"""Tests for the Progress records table rows.

The Progress table shows Attempt as its only numbering — the
per-video stroke number is not repeated there — and its Date/Time
column shows each record's effective time point (capture time when
the source carries one, else save time).

The row builder lives in streamlit_app.py, whose heavy dependencies
(cv2, streamlit, mediapipe) are not installed in every environment.
Where they are missing, stub them just long enough to import the
app module, then restore sys.modules exactly as it was: the stubs
must not leak into other test modules (several of them report the
missing dependencies as loader errors on purpose). The builder
itself is pure — it reads stored rows and the attempt-number
mapping and returns plain dicts.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from tennis360 import history
from tennis360.history import AnalysisRecord


def _load_app_module():
    try:
        import streamlit_app

        return streamlit_app
    except ImportError:
        pass
    before = set(sys.modules)
    stubbed = []
    for name in ("cv2", "streamlit", "mediapipe"):
        if name not in sys.modules:
            sys.modules[name] = MagicMock()
            stubbed.append(name)
    try:
        import streamlit_app
    finally:
        # Undo every import side effect of the stubbed load except
        # the app module itself, so the rest of the suite observes
        # the same import state as if this module were not here.
        for name in stubbed:
            sys.modules.pop(name, None)
        for name in set(sys.modules) - before - {"streamlit_app"}:
            sys.modules.pop(name, None)
    return streamlit_app


APP = _load_app_module()


class ProgressRecordEditorRowsTest(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.connection = history.open_db(
            Path(self._folder.name) / "history.db"
        )
        self.addCleanup(self.connection.close)
        # One charted record (second stroke of a clip filmed on
        # Saturday, analyzed on Monday) and one unmeasured record
        # (listed but never charted, so it has no attempt number).
        self.charted_id = history.record(
            self.connection,
            AnalysisRecord(
                recorded_at="2026-10-26T09:00:00+00:00",
                source_file="practice.mp4",
                action="serve",
                angle_deg=100.0,
                in_range=True,
                main_issue_en="Angle in Range",
                rep_index=2,
                video_time_s=12.4,
                captured_at="2026-10-24T17:00:12+00:00",
            ),
        )
        self.unmeasured_id = history.record(
            self.connection,
            AnalysisRecord(
                recorded_at="2026-10-26T10:00:00+00:00",
                source_file="practice.mp4",
                action="serve",
                main_issue_en="No Trophy Segment Found",
            ),
        )
        rows = history.list_records(self.connection, action="serve")
        numbers = history.record_attempt_numbers(self.connection, "serve")
        self.editor_rows = APP._progress_record_editor_rows(rows, numbers)
        self.by_id = {
            row["Record ID"]: row for row in self.editor_rows
        }

    def test_rows_have_no_stroke_column(self):
        # Attempt is the only numbering in Progress; the per-video
        # stroke number is stored but not shown in this table.
        self.assertEqual(len(self.editor_rows), 2)
        for row in self.editor_rows:
            self.assertNotIn("Stroke", row)

    def test_attempt_and_video_time_columns_remain(self):
        charted = self.by_id[self.charted_id]
        self.assertEqual(charted["Attempt"], "1")
        self.assertEqual(charted["Video Time"], "12.4 s")
        self.assertIn("Delete", charted)
        self.assertIn("Analysis Result", charted)
        unmeasured = self.by_id[self.unmeasured_id]
        self.assertEqual(unmeasured["Attempt"], "—")
        self.assertEqual(unmeasured["Video Time"], "—")

    def test_date_time_column_shows_the_effective_time_point(self):
        # Filmed Saturday, analyzed Monday: the table shows the
        # recording time, the record's one effective time point.
        self.assertEqual(
            self.by_id[self.charted_id]["Date/Time (UTC)"],
            "2026-10-24 17:00:12",
        )
        # No capture time: the save time is shown, as before.
        self.assertEqual(
            self.by_id[self.unmeasured_id]["Date/Time (UTC)"],
            "2026-10-26 10:00:00",
        )


if __name__ == "__main__":
    unittest.main()
