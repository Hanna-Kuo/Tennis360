"""Tests for selective deletion of saved history records.

Progress accumulates one record per saved analysis. The user keeps the
records she chooses and deletes the rest: delete_records() must remove
exactly the targeted ids (and nothing else), report how many rows were
actually removed, and treat empty or unknown id sets as a safe no-op.
record_ids_marked_for_deletion() is the pure mapping from the Progress
table editor's marked rows to the id list delete_records() consumes.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tennis360 import history
from tennis360.history import AnalysisRecord


def _entry(
    action,
    *,
    angle=100.0,
    rep_index=None,
    video_time_s=None,
    captured_at=None,
    stamp,
):
    return AnalysisRecord(
        recorded_at=stamp,
        source_file="clip.mp4",
        action=action,
        angle_deg=angle,
        in_range=True,
        main_issue_en="Angle in Range",
        rep_index=rep_index,
        video_time_s=video_time_s,
        captured_at=captured_at,
    )


class DeleteRecordsTest(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.connection = history.open_db(
            Path(self._folder.name) / "history.db"
        )
        self.addCleanup(self.connection.close)
        # Two records for one stroke (a single analysis and one stroke of
        # a multi-stroke clip), plus one record each for two other
        # strokes, so a deletion can be checked against same-stroke and
        # other-stroke neighbours.
        self.forehand_single = history.record(
            self.connection,
            _entry("forehand", stamp="2026-10-25T10:00:00+00:00"),
        )
        self.forehand_rep = history.record(
            self.connection,
            _entry(
                "forehand",
                angle=95.0,
                rep_index=2,
                video_time_s=12.4,
                stamp="2026-10-25T10:01:00+00:00",
            ),
        )
        self.backhand = history.record(
            self.connection,
            _entry("backhand-two", stamp="2026-10-25T10:02:00+00:00"),
        )
        self.serve = history.record(
            self.connection,
            _entry("serve", stamp="2026-10-25T10:03:00+00:00"),
        )

    def _remaining_ids(self):
        return {
            row["id"] for row in history.list_records(self.connection)
        }

    def test_list_records_exposes_stable_ids(self):
        rows = history.list_records(self.connection, action="forehand")
        self.assertEqual(
            {row["id"] for row in rows},
            {self.forehand_single, self.forehand_rep},
        )

    def test_delete_removes_exactly_the_targeted_records(self):
        deleted = history.delete_records(
            self.connection, [self.forehand_single, self.backhand]
        )
        self.assertEqual(deleted, 2)
        self.assertEqual(
            self._remaining_ids(), {self.forehand_rep, self.serve}
        )
        # Same-stroke and other-stroke survivors keep their contents,
        # and the trend for the kept stroke still reads from the store.
        forehand_rows = history.list_records(
            self.connection, action="forehand"
        )
        self.assertEqual(len(forehand_rows), 1)
        self.assertEqual(forehand_rows[0]["rep_index"], 2)
        self.assertEqual(
            history.trend_points(self.connection, "forehand"),
            [("2026-10-25T10:01:00+00:00", 95.0)],
        )
        self.assertEqual(
            len(history.list_records(self.connection, action="serve")), 1
        )

    def test_delete_empty_selection_changes_nothing(self):
        self.assertEqual(history.delete_records(self.connection, []), 0)
        self.assertEqual(len(self._remaining_ids()), 4)

    def test_delete_unknown_ids_changes_nothing(self):
        self.assertEqual(
            history.delete_records(self.connection, [999999, -1]), 0
        )
        self.assertEqual(len(self._remaining_ids()), 4)

    def test_delete_mixed_known_and_unknown_reports_actual_count(self):
        deleted = history.delete_records(
            self.connection, [self.serve, 424242]
        )
        self.assertEqual(deleted, 1)
        self.assertNotIn(self.serve, self._remaining_ids())
        self.assertEqual(len(self._remaining_ids()), 3)

    def test_delete_duplicate_ids_count_once(self):
        deleted = history.delete_records(
            self.connection,
            [self.backhand, self.backhand, self.backhand],
        )
        self.assertEqual(deleted, 1)
        self.assertNotIn(self.backhand, self._remaining_ids())

    def test_deleted_id_cannot_be_deleted_twice(self):
        self.assertEqual(
            history.delete_records(self.connection, [self.serve]), 1
        )
        self.assertEqual(
            history.delete_records(self.connection, [self.serve]), 0
        )


class MarkedForDeletionTest(unittest.TestCase):
    def test_only_marked_rows_contribute_ids(self):
        rows = [
            {"record_id": 11, "delete": True},
            {"record_id": 12, "delete": False},
            {"record_id": 13, "delete": True},
            {"record_id": 14},
        ]
        self.assertEqual(
            history.record_ids_marked_for_deletion(rows), [11, 13]
        )

    def test_no_marks_returns_empty(self):
        rows = [
            {"record_id": 11, "delete": False},
            {"record_id": 12, "delete": False},
        ]
        self.assertEqual(history.record_ids_marked_for_deletion(rows), [])
        self.assertEqual(history.record_ids_marked_for_deletion([]), [])

    def test_marked_ids_keep_row_order_without_duplicates(self):
        rows = [
            {"record_id": 30, "delete": True},
            {"record_id": 10, "delete": True},
            {"record_id": 30, "delete": True},
        ]
        self.assertEqual(
            history.record_ids_marked_for_deletion(rows), [30, 10]
        )

    def test_marked_row_without_id_is_skipped(self):
        rows = [{"record_id": None, "delete": True}]
        self.assertEqual(history.record_ids_marked_for_deletion(rows), [])


class TrendChartAxisTest(unittest.TestCase):
    """The Progress chart x-axis counts attempts, not calendar dates.

    trend_chart_axis() maps trend points (oldest first) to strictly
    uniform ordinal positions 1..N in saved order — the spacing is
    exactly equal everywhere, always. Dates appear only in a label
    row under the axis, grouped into sections whose unit (day, week,
    month, year) is the finest one yielding at most 15 sections.
    Small charts (at most 15 points) label every point with its
    angle; dense charts (more than 60 points) drop the markers so
    the points merge into one clean line.
    """

    def test_positions_are_attempt_numbers_in_saved_order(self):
        points = [
            ("2026-10-25T10:00:00+00:00", 100.0),
            ("2026-10-25T11:00:00+00:00", 95.0),
            ("2026-10-26T09:00:00+00:00", 110.0),
        ]
        axis = history.trend_chart_axis(points)
        self.assertEqual(axis.positions, [1, 2, 3])
        self.assertEqual(axis.angles, [100.0, 95.0, 110.0])
        self.assertEqual(axis.tick_positions, [1, 2, 3])
        self.assertEqual(axis.tick_labels, ["1", "2", "3"])
        self.assertEqual(
            [(s.unit, s.label, s.start_position, s.end_position)
             for s in axis.sections],
            [("day", "10-25", 1, 2), ("day", "10-26", 3, 3)],
        )
        self.assertEqual(axis.sections[0].center, 1.5)
        self.assertEqual(axis.sections[1].center, 3.0)
        self.assertEqual(
            axis.value_labels, ["100.0°", "95.0°", "110.0°"]
        )
        self.assertTrue(axis.show_markers)

    def test_same_day_records_still_get_separate_positions(self):
        # The field failure: on the old calendar axis, every record
        # saved on one day stacked into a single vertical line.
        points = [
            ("2026-10-25T10:0%d:00+00:00" % minute, 100.0 + minute)
            for minute in range(5)
        ]
        axis = history.trend_chart_axis(points)
        self.assertEqual(axis.positions, [1, 2, 3, 4, 5])
        self.assertEqual(
            axis.angles, [100.0, 101.0, 102.0, 103.0, 104.0]
        )

    def test_empty_points_give_an_empty_axis(self):
        axis = history.trend_chart_axis([])
        self.assertEqual(axis.positions, [])
        self.assertEqual(axis.angles, [])
        self.assertEqual(axis.tick_positions, [])
        self.assertEqual(axis.tick_labels, [])
        self.assertEqual(axis.sections, [])
        self.assertEqual(axis.value_labels, [])

    def test_single_point_is_attempt_one_in_a_day_section(self):
        axis = history.trend_chart_axis(
            [("2026-10-25T10:00:00+00:00", 100.0)]
        )
        self.assertEqual(axis.positions, [1])
        self.assertEqual(axis.tick_positions, [1])
        self.assertEqual(axis.tick_labels, ["1"])
        self.assertEqual(len(axis.sections), 1)
        self.assertEqual(axis.sections[0].unit, "day")
        self.assertEqual(axis.sections[0].label, "10-25")
        self.assertEqual(axis.sections[0].center, 1.0)

    def test_moderate_counts_label_every_attempt(self):
        points = [
            ("2026-10-25T10:00:00+00:00", 100.0) for _ in range(20)
        ]
        axis = history.trend_chart_axis(points)
        self.assertEqual(axis.tick_positions, list(range(1, 21)))
        self.assertEqual(
            axis.tick_labels,
            [str(attempt) for attempt in range(1, 21)],
        )
        # One practice day is one section, however many attempts.
        self.assertEqual(len(axis.sections), 1)
        self.assertEqual(axis.sections[0].end_position, 20)

    def test_many_points_thin_attempt_labels_only(self):
        start = datetime(2026, 10, 25, tzinfo=timezone.utc)
        points = [
            ((start + timedelta(days=index)).isoformat(), 100.0)
            for index in range(120)
        ]
        axis = history.trend_chart_axis(points)
        # Spacing stays strictly uniform at any count.
        self.assertEqual(axis.positions, list(range(1, 121)))
        # Attempt ticks: at most the label cap, plus the final point;
        # labels are bare attempt numbers (dates live in sections).
        self.assertLessEqual(len(axis.tick_labels), 31)
        self.assertTrue(
            all(label.isdigit() for label in axis.tick_labels)
        )
        self.assertEqual(axis.tick_positions[0], 1)
        self.assertEqual(axis.tick_positions, sorted(axis.tick_positions))
        self.assertEqual(axis.tick_positions[-1], 120)
        # 120 distinct days roll up past weeks (about 18) to months.
        self.assertEqual(
            [s.label for s in axis.sections],
            ["2026-10", "2026-11", "2026-12", "2027-01", "2027-02"],
        )
        self.assertTrue(
            all(s.unit == "month" for s in axis.sections)
        )
        self.assertEqual(axis.value_labels, [])
        self.assertFalse(axis.show_markers)

    def test_few_attempts_spread_over_months_stay_day_sections(self):
        # Section choice is by section count, not calendar span: a
        # handful of attempts keeps one day section per practice day
        # even when the days are months apart.
        points = [
            ("2026-01-10T10:00:00+00:00", 100.0),
            ("2026-02-05T10:00:00+00:00", 101.0),
            ("2026-03-01T10:00:00+00:00", 102.0),
            ("2026-03-20T10:00:00+00:00", 103.0),
            ("2026-04-02T10:00:00+00:00", 104.0),
        ]
        axis = history.trend_chart_axis(points)
        self.assertEqual(
            [(s.unit, s.label) for s in axis.sections],
            [("day", "01-10"), ("day", "02-05"), ("day", "03-01"),
             ("day", "03-20"), ("day", "04-02")],
        )
        self.assertEqual(
            [s.center for s in axis.sections], [1.0, 2.0, 3.0, 4.0, 5.0]
        )

    def test_more_than_15_days_roll_up_to_monday_weeks(self):
        # One attempt per day for 20 days starting Wednesday
        # 2026-10-21: 20 day sections exceed the cap, so the chart
        # groups by calendar weeks starting on Monday.
        start = datetime(2026, 10, 21, tzinfo=timezone.utc)
        points = [
            ((start + timedelta(days=index)).isoformat(), 100.0)
            for index in range(20)
        ]
        axis = history.trend_chart_axis(points)
        self.assertEqual(
            [(s.label, s.start_position, s.end_position)
             for s in axis.sections],
            [("Week of 10-19", 1, 5), ("Week of 10-26", 6, 12),
             ("Week of 11-02", 13, 19), ("Week of 11-09", 20, 20)],
        )
        self.assertTrue(all(s.unit == "week" for s in axis.sections))

    def test_multi_year_span_rolls_up_to_year_sections(self):
        # One attempt per week for three years: days, weeks, and
        # months all exceed 15 sections, so years win.
        start = datetime(2026, 1, 5, tzinfo=timezone.utc)
        points = [
            ((start + timedelta(weeks=index)).isoformat(), 100.0)
            for index in range(156)
        ]
        axis = history.trend_chart_axis(points)
        self.assertEqual(
            [s.label for s in axis.sections], ["2026", "2027", "2028"]
        )
        self.assertTrue(all(s.unit == "year" for s in axis.sections))

    def test_positions_stay_uniform_across_section_boundaries(self):
        # Sections never move points: across every boundary the
        # spacing between consecutive attempts is exactly one step.
        points = [
            ("2026-10-25T10:00:00+00:00", 100.0),
            ("2026-10-25T11:00:00+00:00", 101.0),
            ("2026-10-25T12:00:00+00:00", 102.0),
            ("2026-11-30T10:00:00+00:00", 103.0),
            ("2026-11-30T11:00:00+00:00", 104.0),
            ("2027-01-15T10:00:00+00:00", 105.0),
        ]
        axis = history.trend_chart_axis(points)
        self.assertEqual(axis.positions, [1, 2, 3, 4, 5, 6])
        steps = [
            later - earlier
            for earlier, later in zip(
                axis.positions, axis.positions[1:]
            )
        ]
        self.assertEqual(steps, [1, 1, 1, 1, 1])
        self.assertEqual(len(axis.sections), 3)

    def test_value_labels_switch_off_above_15_points(self):
        fifteen = [
            ("2026-10-25T10:00:00+00:00", 100.0 + index)
            for index in range(15)
        ]
        axis = history.trend_chart_axis(fifteen)
        self.assertEqual(len(axis.value_labels), 15)
        self.assertEqual(axis.value_labels[0], "100.0°")
        self.assertEqual(axis.value_labels[-1], "114.0°")
        sixteen = fifteen + [("2026-10-25T11:00:00+00:00", 115.0)]
        self.assertEqual(history.trend_chart_axis(sixteen).value_labels, [])

    def test_markers_switch_off_above_60_points(self):
        sixty = [
            ("2026-10-25T10:00:00+00:00", 100.0) for _ in range(60)
        ]
        self.assertTrue(history.trend_chart_axis(sixty).show_markers)
        sixty_one = sixty + [("2026-10-25T11:00:00+00:00", 100.0)]
        self.assertFalse(
            history.trend_chart_axis(sixty_one).show_markers
        )

    def test_attempt_numbers_renumber_after_middle_record_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            connection = history.open_db(Path(folder) / "history.db")
            try:
                specs = [
                    ("2026-10-25T10:00:00+00:00", 100.0),
                    ("2026-10-26T10:00:00+00:00", 110.0),
                    ("2026-10-27T10:00:00+00:00", 120.0),
                ]
                ids = [
                    history.record(
                        connection,
                        _entry("serve", angle=angle, stamp=stamp),
                    )
                    for stamp, angle in specs
                ]
                self.assertEqual(
                    history.delete_records(connection, [ids[1]]), 1
                )
                axis = history.trend_chart_axis(
                    history.trend_points(connection, "serve")
                )
            finally:
                connection.close()
        # The two survivors renumber to attempts 1 and 2, keeping
        # their own angles, and the sections recompute over just the
        # surviving days.
        self.assertEqual(axis.positions, [1, 2])
        self.assertEqual(axis.angles, [100.0, 120.0])
        self.assertEqual(axis.tick_labels, ["1", "2"])
        self.assertEqual(
            [(s.unit, s.label) for s in axis.sections],
            [("day", "10-25"), ("day", "10-27")],
        )


class RecordAttemptNumbersTest(unittest.TestCase):
    """Table Attempt numbers and chart attempt numbers must correspond.

    record_attempt_numbers() maps each charted record's id to its
    1-based position in trend_records() — the same ordered set the
    trend chart plots — so the number beside a record in the Progress
    table (which lists newest first) is exactly the number the chart
    plots for that record, and a deletion renumbers both together.
    """

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.connection = history.open_db(
            Path(self._folder.name) / "history.db"
        )
        self.addCleanup(self.connection.close)
        # Four forehand records oldest to newest, with one backhand
        # record interleaved: the mapping is per stroke, so the
        # backhand record must not shift the forehand numbers.
        self.forehand_ids = [
            history.record(
                self.connection,
                _entry(
                    "forehand",
                    angle=angle,
                    stamp="2026-10-25T10:0%d:00+00:00" % index,
                ),
            )
            for index, angle in enumerate([100.0, 95.0, 110.0, 105.0])
        ]
        self.backhand_id = history.record(
            self.connection,
            _entry("backhand-two", stamp="2026-10-25T10:05:00+00:00"),
        )

    def test_attempt_numbers_follow_saved_order(self):
        numbers = history.record_attempt_numbers(
            self.connection, "forehand"
        )
        self.assertEqual(
            numbers,
            {record_id: index + 1
             for index, record_id in enumerate(self.forehand_ids)},
        )
        self.assertEqual(
            history.record_attempt_numbers(
                self.connection, "backhand-two"
            ),
            {self.backhand_id: 1},
        )
        self.assertEqual(
            history.record_attempt_numbers(self.connection, "lob"), {}
        )

    def test_attempt_numbers_match_chart_positions_and_angles(self):
        numbers = history.record_attempt_numbers(
            self.connection, "forehand"
        )
        axis = history.trend_chart_axis(
            history.trend_points(self.connection, "forehand")
        )
        self.assertEqual(axis.positions, [1, 2, 3, 4])
        # The record the mapping calls attempt N is the one whose
        # angle the chart plots at position N.
        rows_by_id = {
            row["id"]: row
            for row in history.list_records(
                self.connection, action="forehand"
            )
        }
        for record_id, attempt in numbers.items():
            self.assertEqual(
                axis.angles[attempt - 1],
                rows_by_id[record_id]["angle_deg"],
            )

    def test_newest_first_table_order_runs_attempts_high_to_low(self):
        # The Progress table lists newest first; with the mapping
        # applied, its Attempt values run N, N-1, ..., 1 top to
        # bottom while still naming the same records as the chart.
        numbers = history.record_attempt_numbers(
            self.connection, "forehand"
        )
        displayed = history.list_records(
            self.connection, action="forehand"
        )
        self.assertEqual(
            [numbers[row["id"]] for row in displayed], [4, 3, 2, 1]
        )

    def test_same_timestamp_records_number_in_save_order(self):
        # One multi-stroke run saves several records within the same
        # second; their attempt order must be the order they were
        # saved, for the mapping and the chart alike.
        connection = history.open_db(
            Path(self._folder.name) / "batch.db"
        )
        try:
            stamp = "2026-10-25T19:24:12+00:00"
            ids = [
                history.record(
                    connection,
                    _entry(
                        "serve",
                        angle=angle,
                        rep_index=index + 1,
                        stamp=stamp,
                    ),
                )
                for index, angle in enumerate([90.0, 100.0, 110.0])
            ]
            numbers = history.record_attempt_numbers(connection, "serve")
            points = history.trend_points(connection, "serve")
        finally:
            connection.close()
        self.assertEqual(
            numbers, {ids[0]: 1, ids[1]: 2, ids[2]: 3}
        )
        self.assertEqual(
            [angle for _, angle in points], [90.0, 100.0, 110.0]
        )

    def test_unmeasured_record_is_not_numbered_and_shifts_nothing(self):
        # A saved record without an angle is listed in the table but
        # never plotted, so it carries no attempt number; the charted
        # records keep exactly their chart positions.
        connection = history.open_db(
            Path(self._folder.name) / "mixed.db"
        )
        try:
            first = history.record(
                connection,
                _entry(
                    "serve",
                    angle=100.0,
                    stamp="2026-10-25T10:00:00+00:00",
                ),
            )
            history.record(
                connection,
                _entry(
                    "serve",
                    angle=None,
                    stamp="2026-10-25T10:01:00+00:00",
                ),
            )
            second = history.record(
                connection,
                _entry(
                    "serve",
                    angle=120.0,
                    stamp="2026-10-25T10:02:00+00:00",
                ),
            )
            numbers = history.record_attempt_numbers(connection, "serve")
            table_ids = [
                row["id"]
                for row in history.list_records(
                    connection, action="serve"
                )
            ]
        finally:
            connection.close()
        self.assertEqual(numbers, {first: 1, second: 2})
        self.assertEqual(len(table_ids), 3)

    def test_attempt_numbers_renumber_with_chart_after_deletion(self):
        self.assertEqual(
            history.delete_records(
                self.connection, [self.forehand_ids[1]]
            ),
            1,
        )
        numbers = history.record_attempt_numbers(
            self.connection, "forehand"
        )
        axis = history.trend_chart_axis(
            history.trend_points(self.connection, "forehand")
        )
        # The survivors shift down together in both views, each
        # keeping its own angle.
        self.assertEqual(
            numbers,
            {
                self.forehand_ids[0]: 1,
                self.forehand_ids[2]: 2,
                self.forehand_ids[3]: 3,
            },
        )
        self.assertEqual(axis.positions, [1, 2, 3])
        self.assertEqual(axis.angles, [100.0, 110.0, 105.0])
        displayed = history.list_records(
            self.connection, action="forehand"
        )
        self.assertEqual(
            [numbers[row["id"]] for row in displayed], [3, 2, 1]
        )


class EffectiveTimeTest(unittest.TestCase):
    """One effective time point per record: capture time, else save time.

    The user's rule: a record belongs to the moment its photo or
    video was recorded when the file carries a recording time, and
    to the moment the analysis was saved only when it does not. That
    one effective time drives the trend order, the Attempt numbers,
    the chart's date sections, and the table's sort — so a video
    filmed on Saturday and analyzed on Monday is Saturday's record
    in every view.
    """

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.connection = history.open_db(
            Path(self._folder.name) / "history.db"
        )
        self.addCleanup(self.connection.close)

    def test_effective_time_prefers_the_capture_time(self):
        self.assertEqual(
            history.effective_time(
                "2026-10-26T09:00:00+00:00", "2026-10-24T17:00:00+00:00"
            ),
            "2026-10-24T17:00:00+00:00",
        )
        self.assertEqual(
            history.effective_time("2026-10-26T09:00:00+00:00", None),
            "2026-10-26T09:00:00+00:00",
        )
        self.assertEqual(
            history.effective_time("2026-10-26T09:00:00+00:00", ""),
            "2026-10-26T09:00:00+00:00",
        )

    def test_record_stores_its_capture_time(self):
        history.record(
            self.connection,
            _entry(
                "serve",
                stamp="2026-10-26T09:00:00+00:00",
                captured_at="2026-10-24T17:00:00+00:00",
            ),
        )
        history.record(
            self.connection,
            _entry("serve", stamp="2026-10-26T10:00:00+00:00"),
        )
        rows = {
            row["recorded_at"]: row["captured_at"]
            for row in history.list_records(self.connection)
        }
        self.assertEqual(
            rows,
            {
                "2026-10-26T09:00:00+00:00": "2026-10-24T17:00:00+00:00",
                "2026-10-26T10:00:00+00:00": None,
            },
        )

    def test_saturday_filmed_monday_analyzed_belongs_to_saturday(self):
        # Saved on Monday, filmed on Saturday: the capture time is
        # the earlier save's junior in save order but must win
        # everywhere the record is placed in time.
        saturday_id = history.record(
            self.connection,
            _entry(
                "serve",
                angle=100.0,
                stamp="2026-10-26T09:00:00+00:00",  # analyzed Monday
                captured_at="2026-10-24T17:00:00+00:00",  # filmed Saturday
            ),
        )
        sunday_id = history.record(
            self.connection,
            _entry(
                "serve",
                angle=110.0,
                stamp="2026-10-25T09:00:00+00:00",  # analyzed Sunday
            ),
        )
        # Trend order and the stamps it carries follow capture time.
        self.assertEqual(
            history.trend_points(self.connection, "serve"),
            [
                ("2026-10-24T17:00:00+00:00", 100.0),
                ("2026-10-25T09:00:00+00:00", 110.0),
            ],
        )
        # Attempt numbers follow the same order.
        self.assertEqual(
            history.record_attempt_numbers(self.connection, "serve"),
            {saturday_id: 1, sunday_id: 2},
        )
        # The chart sections are the recording days.
        axis = history.trend_chart_axis(
            history.trend_points(self.connection, "serve")
        )
        self.assertEqual(
            [(section.unit, section.label) for section in axis.sections],
            [("day", "10-24"), ("day", "10-25")],
        )
        # The table sorts by the same effective time, newest first.
        displayed = history.list_records(
            self.connection, action="serve"
        )
        self.assertEqual(
            [row["id"] for row in displayed], [sunday_id, saturday_id]
        )

    def test_records_without_capture_time_behave_as_before(self):
        first = history.record(
            self.connection,
            _entry("serve", stamp="2026-10-25T09:00:00+00:00"),
        )
        second = history.record(
            self.connection,
            _entry("serve", stamp="2026-10-25T08:00:00+00:00"),
        )
        # Pure save-time order: the earlier save is attempt 1 even
        # though it was stored second.
        self.assertEqual(
            history.record_attempt_numbers(self.connection, "serve"),
            {second: 1, first: 2},
        )
        self.assertEqual(
            [
                stamp
                for stamp, _ in history.trend_points(
                    self.connection, "serve"
                )
            ],
            ["2026-10-25T08:00:00+00:00", "2026-10-25T09:00:00+00:00"],
        )

    def test_open_db_migrates_a_pre_capture_time_database(self):
        # A database from the previous release: rep_index and
        # video_time_s exist, captured_at does not. Opening it adds
        # the column, and the old rows behave exactly as before
        # (their effective time is their save time).
        import sqlite3

        path = Path(self._folder.name) / "old.db"
        raw = sqlite3.connect(str(path))
        raw.execute(
            """
            CREATE TABLE analyses (
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
            )
            """
        )
        raw.execute(
            "INSERT INTO analyses (recorded_at, source_file, action,"
            " angle_deg) VALUES"
            " ('2026-10-25T10:00:00+00:00', 'old.mp4', 'serve', 100.0)"
        )
        raw.commit()
        raw.close()

        connection = history.open_db(path)
        try:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(analyses)")
            }
            self.assertIn("captured_at", columns)
            rows = history.list_records(connection)
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0]["captured_at"])
            self.assertEqual(
                history.trend_points(connection, "serve"),
                [("2026-10-25T10:00:00+00:00", 100.0)],
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
