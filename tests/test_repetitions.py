"""Tests for multi-repetition analysis and its history recording.

Covers the repetition segmentation in tennis360.strokes, the sequential
serve scan, recording rules, and invalid-repetition display text in
tennis360.repetitions (every analyzed repetition becomes its own
history record; unanalyzable repetitions are never recorded but are
still listed, marked invalid), each repetition's start–end time window
in the video, the per-stroke skeleton-diagram rendering rule (one
diagram per analyzed stroke, never for invalid ones), and the history
schema migration that carries the repetition fields. Pure geometry and
SQLite only — no MediaPipe model or OpenCV needed.
"""

import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from tennis360 import history
from tennis360.config import TargetRange, Targets
from tennis360.history import AnalysisRecord
from tennis360.repetitions import (
    ServeSample,
    best_trophy_sample,
    find_serve_actions,
    format_time_window,
    invalid_rep_result,
    render_stroke_diagrams,
    serve_rep_invalid_reason,
    serve_rep_record,
    swing_rep_invalid_reason,
    swing_rep_records,
)
from tennis360.strokes import (
    SwingSample,
    analyze_repetitions,
    analyze_swing,
    find_rep_windows,
)


def _demo_targets() -> Targets:
    return Targets(
        ranges={
            "forehand": TargetRange("forehand", 130.0, 170.0, "demo"),
            "overhead": TargetRange("overhead", 150.0, 180.0, "demo"),
        },
        extras={},
    )


def _sample(index: int, wrist_x: float, wrist_rise: float, elbow: float):
    return SwingSample(
        index=index * 6,
        time_s=index * 0.2,
        wrist_x=wrist_x,
        wrist_rise=wrist_rise,
        elbow_angle=elbow,
        second_elbow_angle=None,
        shoulder_mid_x=0.50,
        shoulder_angle_deg=20.0,
        width_px=640.0,
        scale_px=200.0,
    )


def _forehand_swing(elbow_at_contact: float):
    """One right-hand forehand: back, whip forward, finish high."""

    xs = [0.50, 0.42, 0.32, 0.50, 0.80, 0.88, 0.90]
    rises = [0.05, 0.00, -0.10, 0.00, 0.25, 0.55, 0.85]
    elbows = [110.0, 110.0, 110.0, 110.0, elbow_at_contact, 120.0, 130.0]
    return list(zip(xs, rises, elbows))


_RECOVERY = [(0.70, 0.40, 110.0), (0.58, 0.15, 110.0), (0.52, 0.05, 110.0)]


def _overhead(elbow_at_peak: float):
    """One overhead: wrist rises to the smash point and falls again."""

    xs = [0.5] * 6
    rises = [-0.2, 0.3, 1.5, 0.4, -0.1, -0.3]
    elbows = [110.0, 110.0, elbow_at_peak, 120.0, 110.0, 110.0]
    return list(zip(xs, rises, elbows))


_OVERHEAD_GAP = [(0.5, 0.1, 110.0), (0.5, 0.0, 110.0)]


def _timeline(*parts) -> list[SwingSample]:
    data = [point for part in parts for point in part]
    return [
        _sample(i, x, rise, elbow) for i, (x, rise, elbow) in enumerate(data)
    ]


def _three_forehands() -> list[SwingSample]:
    return _timeline(
        _forehand_swing(150.0),
        _RECOVERY,
        _forehand_swing(165.0),
        _RECOVERY,
        _forehand_swing(140.0),
    )


class RepSegmentationTest(unittest.TestCase):
    def test_finds_three_forehand_repetitions_in_order(self):
        samples = _three_forehands()
        windows = find_rep_windows("forehand", samples)
        self.assertEqual(len(windows), 3)

        reps = analyze_repetitions("forehand", samples, _demo_targets())
        self.assertEqual([rep.rep_index for rep in reps], [1, 2, 3])
        self.assertTrue(all(rep.analyzed for rep in reps))
        contact_times = [rep.contact_time_s for rep in reps]
        self.assertEqual(contact_times, sorted(contact_times))
        # Each rep reports ITS OWN contact elbow, not a neighbor's.
        elbows = [
            rep.metrics.contact_elbow_deg if rep.metrics else None
            for rep in reps
        ]
        self.assertEqual(elbows, [150.0, 165.0, 140.0])
        # Key moments stay inside each rep's own window.
        for rep in reps:
            assert rep.moments is not None
            self.assertGreaterEqual(rep.moments.backswing, rep.start_pos)
            self.assertLessEqual(rep.moments.followthrough, rep.end_pos)
            self.assertLess(rep.moments.backswing, rep.moments.contact)
            self.assertLess(rep.moments.contact, rep.moments.followthrough)

    def test_finds_two_overhead_repetitions(self):
        samples = _timeline(_overhead(160.0), _OVERHEAD_GAP, _overhead(170.0))
        reps = analyze_repetitions("overhead", samples, _demo_targets())
        self.assertEqual(len(reps), 2)
        self.assertTrue(all(rep.analyzed for rep in reps))
        elbows = [
            rep.metrics.contact_elbow_deg if rep.metrics else None
            for rep in reps
        ]
        self.assertEqual(elbows, [160.0, 170.0])

    def test_single_swing_yields_one_rep_matching_single_analysis(self):
        samples = _timeline(_forehand_swing(150.0))
        single_moments, _, _ = analyze_swing("forehand", samples, _demo_targets())
        reps = analyze_repetitions("forehand", samples, _demo_targets())
        self.assertEqual(len(reps), 1)
        assert single_moments is not None and reps[0].moments is not None
        self.assertEqual(reps[0].moments.contact, single_moments.contact)
        self.assertEqual(reps[0].moments.backswing, single_moments.backswing)
        self.assertEqual(
            reps[0].moments.followthrough, single_moments.followthrough
        )

    def test_flat_clip_yields_no_repetitions(self):
        samples = [_sample(i, 0.5, 0.0, 110.0) for i in range(10)]
        self.assertEqual(find_rep_windows("forehand", samples), [])
        self.assertEqual(analyze_repetitions("forehand", samples), [])

    def test_unanalyzable_rep_is_reported_but_flagged(self):
        # The middle repetition's window yields no clear swing (mocked
        # single-swing refusal); it must surface as found-but-not-analyzed
        # rather than disappearing or borrowing a neighbor's result.
        from tennis360 import strokes

        real_analyze = strokes.analyze_swing
        calls = {"count": 0}

        def flaky(action, samples, targets=None):
            calls["count"] += 1
            if calls["count"] == 2:
                return None, None, ["No clear swing found in this clip."]
            return real_analyze(action, samples, targets)

        with mock.patch.object(strokes, "analyze_swing", side_effect=flaky):
            reps = analyze_repetitions(
                "forehand", _three_forehands(), _demo_targets()
            )
        self.assertEqual(len(reps), 3)
        self.assertEqual(
            [rep.analyzed for rep in reps], [True, False, True]
        )
        self.assertIsNone(reps[1].contact_time_s)


class SwingRepRecordTest(unittest.TestCase):
    def test_each_rep_becomes_its_own_record(self):
        reps = analyze_repetitions(
            "forehand", _three_forehands(), _demo_targets()
        )
        records = swing_rep_records(
            reps,
            source_file="practice.mp4",
            action="forehand",
            arm="right",
            target_source="demo",
        )
        self.assertEqual(len(records), 3)
        self.assertEqual([r.rep_index for r in records], [1, 2, 3])
        self.assertEqual(
            [r.angle_deg for r in records], [150.0, 165.0, 140.0]
        )
        # Repetitions are distinguishable by their time in the source video.
        times = [r.video_time_s for r in records]
        self.assertEqual(len(set(times)), 3)
        self.assertTrue(all(t is not None for t in times))

    def test_unanalyzed_reps_are_not_recorded(self):
        reps = analyze_repetitions(
            "forehand", _three_forehands(), _demo_targets()
        )
        reps[1].moments = None
        reps[1].metrics = None
        records = swing_rep_records(
            reps,
            source_file="practice.mp4",
            action="forehand",
            arm="right",
        )
        self.assertEqual([r.rep_index for r in records], [1, 3])

    def test_rep_records_are_stored_as_separate_rows(self):
        reps = analyze_repetitions(
            "forehand", _three_forehands(), _demo_targets()
        )
        records = swing_rep_records(
            reps,
            source_file="practice.mp4",
            action="forehand",
            arm="right",
        )
        with TemporaryDirectory() as folder:
            connection = history.open_db(Path(folder) / "history.db")
            try:
                for entry in records:
                    history.record(connection, entry)
                rows = history.list_records(connection, action="forehand")
                points = history.trend_points(connection, "forehand")
            finally:
                connection.close()
        self.assertEqual(len(rows), 3)
        stored = {(row["rep_index"], row["video_time_s"]) for row in rows}
        self.assertEqual(len(stored), 3)
        self.assertEqual(len(points), 3)
        self.assertEqual(
            sorted(angle for _, angle in points), [140.0, 150.0, 165.0]
        )

    def test_capture_start_offsets_each_record_from_the_recording(self):
        # One shared recording start for the whole clip; each stroke's
        # capture instant is the start plus its own time in the video,
        # so the strokes keep their true hit order under the
        # recording day.
        reps = analyze_repetitions(
            "forehand", _three_forehands(), _demo_targets()
        )
        records = swing_rep_records(
            reps,
            source_file="practice.mp4",
            action="forehand",
            arm="right",
            capture_start="2026-10-24T17:00:00+00:00",
        )
        base = datetime(2026, 10, 24, 17, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(len(records), 3)
        for entry in records:
            self.assertIsNotNone(entry.captured_at)
            assert entry.captured_at is not None
            captured = datetime.fromisoformat(entry.captured_at)
            delta = (captured - base).total_seconds()
            # Stored at second precision; the offset itself is the
            # stroke's stored time in the video.
            self.assertAlmostEqual(delta, entry.video_time_s, delta=1.0)
        stamps = [entry.captured_at for entry in records]
        self.assertEqual(stamps, sorted(stamps))
        self.assertEqual(len(set(stamps)), 3)

    def test_no_capture_start_leaves_capture_time_empty(self):
        reps = analyze_repetitions(
            "forehand", _three_forehands(), _demo_targets()
        )
        records = swing_rep_records(
            reps,
            source_file="practice.mp4",
            action="forehand",
            arm="right",
        )
        self.assertTrue(records)
        self.assertTrue(
            all(entry.captured_at is None for entry in records)
        )

    def test_single_record_keeps_rep_fields_empty(self):
        with TemporaryDirectory() as folder:
            connection = history.open_db(Path(folder) / "history.db")
            try:
                history.record(
                    connection,
                    AnalysisRecord(
                        recorded_at=history.utc_now_iso(),
                        source_file="serve.jpg",
                        action="serve",
                        angle_deg=98.0,
                        in_range=True,
                    ),
                )
                rows = history.list_records(connection)
            finally:
                connection.close()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["rep_index"])
        self.assertIsNone(rows[0]["video_time_s"])


class ServeRepRecordTest(unittest.TestCase):
    def test_measured_serve_rep_becomes_a_record(self):
        entry = serve_rep_record(
            rep_index=2,
            trophy_time_s=7.4,
            source_file="serves.mp4",
            angle_degrees=98.0,
            in_range=True,
            arm="right",
            requested_arm="auto",
        )
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.action, "serve")
        self.assertEqual(entry.rep_index, 2)
        self.assertEqual(entry.video_time_s, 7.4)
        self.assertEqual(entry.angle_deg, 98.0)
        self.assertTrue(entry.in_range)
        self.assertEqual(entry.arm, "right")
        self.assertEqual(entry.main_issue_en, "Angle in Range")

    def test_out_of_range_serve_rep_records_the_outside_issue(self):
        entry = serve_rep_record(
            rep_index=1,
            trophy_time_s=2.0,
            source_file="serves.mp4",
            angle_degrees=164.8,
            in_range=False,
            arm="right",
            requested_arm="right",
        )
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertFalse(entry.in_range)
        self.assertEqual(
            entry.main_issue_en, "Elbow Angle Outside Demo Range"
        )

    def test_unmeasured_serve_rep_is_not_recorded(self):
        entry = serve_rep_record(
            rep_index=1,
            trophy_time_s=2.0,
            source_file="serves.mp4",
            angle_degrees=None,
            in_range=None,
            arm="right",
            requested_arm="auto",
        )
        self.assertIsNone(entry)

    def test_capture_start_plus_trophy_time_is_the_capture_instant(self):
        entry = serve_rep_record(
            rep_index=1,
            trophy_time_s=90.0,
            source_file="serves.mp4",
            angle_degrees=98.0,
            in_range=True,
            arm="right",
            requested_arm="auto",
            capture_start="2026-10-24T17:00:00+00:00",
        )
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.captured_at, "2026-10-24T17:01:30+00:00")

    def test_no_capture_start_leaves_capture_time_empty(self):
        entry = serve_rep_record(
            rep_index=1,
            trophy_time_s=2.0,
            source_file="serves.mp4",
            angle_degrees=98.0,
            in_range=True,
            arm="right",
            requested_arm="auto",
        )
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertIsNone(entry.captured_at)


def _serve_sample(time_s, rise, angle, *, in_preparation=True, arm="right"):
    return ServeSample(
        time_s=time_s,
        frame_index=int(time_s * 30),
        arm=arm,
        angle_degrees=angle,
        wrist_rise=rise,
        in_preparation=in_preparation,
    )


class ServeWindowScoringTest(unittest.TestCase):
    """Per-window trophy scoring uses the single analysis's own rule.

    Regression coverage for the field failure where every serve in a
    clip came back Invalid: the repetitions path used to re-run the
    still-photo pipeline on each extracted frame, whose focus and
    phase guards refuse video frames the scan already measured. The
    window is now scored from the scan's samples directly.
    """

    def test_picks_the_highest_wrist_preparation_sample(self):
        window = [
            _serve_sample(1.0, 0.10, 95.0),
            _serve_sample(1.2, 0.45, 164.8),
            _serve_sample(1.4, 0.30, 120.0),
        ]
        best = best_trophy_sample(window)
        self.assertIsNotNone(best)
        assert best is not None
        self.assertEqual(best.time_s, 1.2)
        self.assertEqual(best.angle_degrees, 164.8)

    def test_non_preparation_samples_are_never_picked(self):
        # The window's highest wrist overall is a follow-through frame
        # outside the preparation position; the scored frame must be
        # the best PREPARATION sample, as in the single analysis,
        # whose trophy segments contain preparation frames only.
        window = [
            _serve_sample(1.0, 0.20, 100.0),
            _serve_sample(1.2, 0.90, 175.0, in_preparation=False),
            _serve_sample(1.4, 0.35, 110.0),
        ]
        best = best_trophy_sample(window)
        self.assertIsNotNone(best)
        assert best is not None
        self.assertEqual(best.time_s, 1.4)

    def test_sample_without_an_angle_is_not_picked(self):
        window = [
            _serve_sample(1.0, 0.50, None),
            _serve_sample(1.2, 0.30, 105.0),
        ]
        best = best_trophy_sample(window)
        self.assertIsNotNone(best)
        assert best is not None
        self.assertEqual(best.time_s, 1.2)

    def test_window_without_a_measured_trophy_sample_scores_none(self):
        window = [
            _serve_sample(1.0, 0.90, 175.0, in_preparation=False),
            _serve_sample(1.2, 0.50, None),
        ]
        self.assertIsNone(best_trophy_sample(window))
        self.assertIsNone(best_trophy_sample([]))


_OLD_SCHEMA = """
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
    target_source TEXT NOT NULL DEFAULT 'demo'
);
"""


class HistoryMigrationTest(unittest.TestCase):
    def test_old_database_gains_rep_columns(self):
        with TemporaryDirectory() as folder:
            db_path = Path(folder) / "history.db"
            legacy = sqlite3.connect(str(db_path))
            legacy.executescript(_OLD_SCHEMA)
            legacy.execute(
                "INSERT INTO analyses (recorded_at, source_file, action) "
                "VALUES ('2026-10-01T00:00:00+00:00', 'old.jpg', 'serve')"
            )
            legacy.commit()
            legacy.close()

            connection = history.open_db(db_path)
            try:
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(analyses)")
                }
                self.assertIn("rep_index", columns)
                self.assertIn("video_time_s", columns)
                history.record(
                    connection,
                    AnalysisRecord(
                        recorded_at=history.utc_now_iso(),
                        source_file="practice.mp4",
                        action="forehand",
                        angle_deg=150.0,
                        rep_index=1,
                        video_time_s=0.8,
                    ),
                )
                rows = history.list_records(connection)
            finally:
                connection.close()
        self.assertEqual(len(rows), 2)
        by_source = {row["source_file"]: row for row in rows}
        self.assertIsNone(by_source["old.jpg"]["rep_index"])
        self.assertEqual(by_source["practice.mp4"]["rep_index"], 1)
        self.assertEqual(by_source["practice.mp4"]["video_time_s"], 0.8)


def _serve_series(centers, *, length_s, peak=0.6, half_width_s=1.2, floor=0.0):
    """Synthetic wrist-rise timeline: triangular serve humps on a floor.

    Samples every 0.2 s, matching the serve scan's default 5 fps
    sampling. Each hump rises from the floor to ``peak`` at its center
    and falls back — one serve's trophy climb and completion.
    """

    count = int(length_s / 0.2) + 1
    times = [i * 0.2 for i in range(count)]
    rises = []
    for t in times:
        rise = floor
        for center in centers:
            if abs(t - center) < half_width_s:
                rise = max(rise, peak * (1.0 - abs(t - center) / half_width_s))
        rises.append(rise)
    return times, rises


def _filtered_serve_series(starts, profile, *, step_s=0.2):
    """Synthetic FILTERED timeline: only preparation samples exist.

    Models the video scan in automatic arm mode, which keeps a sample
    only while an arm passes the preparation gate: each serve
    contributes ``profile`` (one wrist rise per step) and between
    serves there are NO samples at all — the sample times jump by
    seconds, and no low between-serve samples exist for a valley rule
    to complete a serve against.
    """

    times, rises = [], []
    for start in starts:
        for offset, rise in enumerate(profile):
            times.append(round(start + offset * step_s, 2))
            rises.append(rise)
    return times, rises


class ServeActionScanTest(unittest.TestCase):
    """The sequential serve scan (tennis360.repetitions.find_serve_actions)."""

    def test_seven_serves_with_gaps_are_seven_actions(self):
        centers = [10.0, 30.0, 50.0, 70.0, 90.0, 110.0, 130.0]
        times, rises = _serve_series(centers, length_s=140.0)
        actions = find_serve_actions(times, rises)
        self.assertEqual(len(actions), 7)
        peak_times = [times[peak] for _, _, peak in actions]
        for expected, actual in zip(centers, peak_times):
            self.assertAlmostEqual(actual, expected, delta=0.21)
        # Windows are in time order, contain their peak, never overlap.
        for (start, end, peak), (next_start, _, _) in zip(
            actions, actions[1:] + [(len(times), 0, 0)]
        ):
            self.assertLessEqual(start, peak)
            self.assertLessEqual(peak, end)
            self.assertLess(end, next_start)

    def test_serves_across_a_long_quiet_gap_are_each_found(self):
        times, rises = _serve_series([10.0, 100.0], length_s=120.0)
        actions = find_serve_actions(times, rises)
        self.assertEqual(len(actions), 2)
        self.assertAlmostEqual(times[actions[0][2]], 10.0, delta=0.21)
        self.assertAlmostEqual(times[actions[1][2]], 100.0, delta=0.21)

    def test_missing_samples_in_the_gap_still_split_serves(self):
        times, rises = _serve_series([10.0, 30.0], length_s=40.0)
        # Samples with no observation between the serves (the scan's
        # frame list can skip stretches where nothing was detected).
        rises = [
            None if 14.0 < t < 26.0 else rise
            for t, rise in zip(times, rises)
        ]
        actions = find_serve_actions(times, rises)
        self.assertEqual(len(actions), 2)

    def test_shallow_saddle_between_peaks_is_one_serve(self):
        # Two wrist-rise peaks joined by a shallow dip (the wrist never
        # falls the full valley drop) are ONE serve: a genuine reset
        # valley must separate two serves, not just time.
        count = int(9.0 / 0.2) + 1
        times = [i * 0.2 for i in range(count)]
        rises = []
        for t in times:
            rise = 0.0
            if abs(t - 3.0) < 3.0:
                rise = max(rise, 0.60 * (1.0 - abs(t - 3.0) / 3.0))
            if abs(t - 5.0) < 3.0:
                rise = max(rise, 0.62 * (1.0 - abs(t - 5.0) / 3.0))
            rises.append(rise)
        actions = find_serve_actions(times, rises)
        self.assertEqual(len(actions), 1)
        # The serve is read from its highest peak.
        self.assertAlmostEqual(times[actions[0][2]], 5.0, delta=0.21)

    def test_peaks_closer_than_min_separation_count_once(self):
        # Two complete rise-and-falls with a genuine valley between
        # them, but their peaks are 1.0 s apart — closer than the
        # minimum separation guard — so they count as one serve.
        times, rises = _serve_series(
            [2.0, 3.0], length_s=6.0, half_width_s=0.5
        )
        actions = find_serve_actions(times, rises)
        self.assertEqual(len(actions), 1)
        self.assertAlmostEqual(times[actions[0][2]], 2.0, delta=0.21)

    def test_small_rise_and_fall_is_not_a_serve(self):
        times, rises = _serve_series(
            [3.0], length_s=6.0, peak=0.42, floor=0.30
        )
        self.assertEqual(find_serve_actions(times, rises), [])

    def test_flat_timeline_has_no_serves(self):
        times = [i * 0.2 for i in range(50)]
        self.assertEqual(find_serve_actions(times, [0.1] * 50), [])

    def test_single_serve(self):
        times, rises = _serve_series([5.0], length_s=10.0)
        actions = find_serve_actions(times, rises)
        self.assertEqual(len(actions), 1)
        start, end, peak = actions[0]
        self.assertAlmostEqual(times[peak], 5.0, delta=0.21)
        self.assertLessEqual(start, peak)
        self.assertLessEqual(peak, end)

    def test_prep_bumps_without_preparation_are_not_serves(self):
        # Two low bumps (raising the arm to bounce the ball, a half
        # practice motion) rise and fall enough to pass the bare
        # rise/fall rule, but the wrist never enters the preparation
        # position; between them, two genuine serves pass through it.
        # With the scan's preparation flags supplied, only the real
        # serves are counted.
        times, rises = _serve_series(
            [5.0, 25.0], length_s=40.0, peak=0.35, half_width_s=0.5,
            floor=-0.30,
        )
        serve_times, serve_rises = _serve_series(
            [15.0, 35.0], length_s=40.0, peak=0.6, half_width_s=1.2,
            floor=-0.30,
        )
        rises = [max(a, b) for a, b in zip(rises, serve_rises)]
        in_preparation = [
            13.8 <= t <= 16.2 or 33.8 <= t <= 36.2 for t in times
        ]
        # Without the flags, the bare rise/fall rule counts all four.
        self.assertEqual(len(find_serve_actions(times, rises)), 4)
        actions = find_serve_actions(
            times, rises, in_preparation=in_preparation
        )
        self.assertEqual(len(actions), 2)
        peak_times = [times[peak] for _, _, peak in actions]
        self.assertAlmostEqual(peak_times[0], 15.0, delta=0.21)
        self.assertAlmostEqual(peak_times[1], 35.0, delta=0.21)

    def test_skipped_bump_does_not_block_a_following_serve(self):
        # A non-preparation bump shortly before a real serve: the
        # bump is skipped, the cursor moves past it, and the serve is
        # still found (the bump must not consume the separation guard
        # as if it were the previous serve).
        times, rises = _serve_series(
            [3.0], length_s=12.0, peak=0.35, half_width_s=0.5, floor=-0.30
        )
        serve_times, serve_rises = _serve_series(
            [5.0], length_s=12.0, peak=0.6, half_width_s=1.2, floor=-0.30
        )
        rises = [max(a, b) for a, b in zip(rises, serve_rises)]
        # _serve_series reuses its own times; they match `times`.
        self.assertEqual(times, serve_times)
        in_preparation = [4.0 <= t <= 6.2 for t in times]
        actions = find_serve_actions(
            times, rises, in_preparation=in_preparation
        )
        self.assertEqual(len(actions), 1)
        self.assertAlmostEqual(times[actions[0][2]], 5.0, delta=0.21)

    def test_final_serve_cut_off_at_clip_end_still_counts(self):
        # The clip ends right at the trophy peak: the climb was
        # genuine, so the serve counts with its window ending at the
        # last sample.
        times, rises = _serve_series([9.0], length_s=9.0)
        actions = find_serve_actions(times, rises)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0][1], len(times) - 1)
        self.assertAlmostEqual(times[actions[0][2]], 9.0, delta=0.21)

    def test_filtered_timeline_with_sample_gaps_finds_every_serve(self):
        # Regression (field failure): in automatic arm mode the scan
        # keeps ONLY preparation samples, so between serves the
        # timeline has multi-second gaps and no low samples at all.
        # The preparation gate's elbow/forearm conditions can pass
        # only once the wrist is already well up, so each serve's
        # samples enter mid-height (0.30) rather than at the band
        # floor. All seven serves must be found, in order, each in
        # its own window — the un-split scan found exactly one, its
        # window swallowing the next serve.
        starts = [2.6, 12.0, 22.0, 32.0, 42.0, 52.0, 62.0]
        profile = [0.30, 0.42, 0.52, 0.60, 0.57, 0.50, 0.44]
        times, rises = _filtered_serve_series(starts, profile)
        actions = find_serve_actions(
            times, rises, in_preparation=[True] * len(times)
        )
        self.assertEqual(len(actions), 7)
        for (start, end, peak), serve_start in zip(actions, starts):
            # The peak is the profile's highest sample, not its start.
            self.assertAlmostEqual(times[peak], serve_start + 0.6, delta=0.01)
            self.assertLessEqual(times[start], times[peak])
            # The window ends inside this serve's own samples — it
            # never reaches the next serve's first sample.
            self.assertLessEqual(times[end], serve_start + 1.2)
        for (_, end, _), (next_start, _, _) in zip(actions, actions[1:]):
            self.assertLess(end, next_start)

    def test_filtered_timeline_starting_at_the_trophy_peak(self):
        # The clip (and therefore the first burst) starts mid-serve:
        # its first sample is already AT the trophy peak and the wrist
        # then declines by less than the full valley drop before the
        # burst ends. That serve counts — read from its first sample —
        # and the serves after the gap are found normally.
        starts = [2.6, 12.0, 22.0]
        first = [0.60, 0.58, 0.55, 0.52, 0.50, 0.48, 0.46, 0.45]
        profile = [0.30, 0.42, 0.52, 0.60, 0.57, 0.50, 0.44]
        times, rises = _filtered_serve_series([starts[0]], first)
        more_times, more_rises = _filtered_serve_series(starts[1:], profile)
        times += more_times
        rises += more_rises
        actions = find_serve_actions(
            times, rises, in_preparation=[True] * len(times)
        )
        self.assertEqual(len(actions), 3)
        start, end, peak = actions[0]
        self.assertEqual(peak, 0)
        self.assertAlmostEqual(times[peak], 2.6, delta=0.01)
        self.assertLessEqual(times[end], 2.6 + 1.4)
        self.assertAlmostEqual(times[actions[1][2]], 12.6, delta=0.01)
        self.assertAlmostEqual(times[actions[2][2]], 22.6, delta=0.01)

    def test_filtered_timeline_shallow_band_entries_are_serves(self):
        # Each serve enters the filtered timeline already high (0.40)
        # and its visible decline stays within the valley drop of its
        # peak, so no wrist-fall evidence separates anything inside a
        # burst — only the sample gaps do. Every serve still counts.
        starts = [2.6, 12.0, 22.0, 32.0]
        profile = [0.40, 0.48, 0.55, 0.62, 0.58, 0.55, 0.52]
        times, rises = _filtered_serve_series(starts, profile)
        actions = find_serve_actions(
            times, rises, in_preparation=[True] * len(times)
        )
        self.assertEqual(len(actions), 4)
        for (_, _, peak), serve_start in zip(actions, starts):
            self.assertAlmostEqual(times[peak], serve_start + 0.6, delta=0.01)

    def test_filtered_bump_burst_is_skipped_without_hiding_serves(self):
        # A burst that never passes through the preparation position
        # (a ball-bounce burst between two serves, possible when the
        # timeline has gaps) is not a serve, and skipping it must not
        # consume or hide the real serve after it.
        profile = [0.30, 0.42, 0.52, 0.60, 0.57, 0.50, 0.44]
        bump = [0.00, 0.18, 0.35, 0.18, 0.00]
        times, rises = _filtered_serve_series([2.6], profile)
        bump_times, bump_rises = _filtered_serve_series([8.0], bump)
        more_times, more_rises = _filtered_serve_series([14.0], profile)
        times += bump_times + more_times
        rises += bump_rises + more_rises
        in_preparation = (
            [True] * len(profile) + [False] * len(bump) + [True] * len(profile)
        )
        actions = find_serve_actions(
            times, rises, in_preparation=in_preparation
        )
        self.assertEqual(len(actions), 2)
        self.assertAlmostEqual(times[actions[0][2]], 3.2, delta=0.01)
        self.assertAlmostEqual(times[actions[1][2]], 14.6, delta=0.01)

    def test_filtered_window_best_sample_is_the_peak(self):
        # Within one detected serve window of a filtered timeline,
        # the scored trophy sample is the window's highest-wrist
        # preparation sample — its peak — not the climb's first
        # sample where the window starts.
        profile = [0.30, 0.42, 0.52, 0.60, 0.57, 0.50, 0.44]
        times, rises = _filtered_serve_series([2.6, 12.0], profile)
        actions = find_serve_actions(
            times, rises, in_preparation=[True] * len(times)
        )
        start, end, _ = actions[0]
        samples = [
            ServeSample(
                time_s=times[i],
                frame_index=i,
                arm="right",
                angle_degrees=100.0,
                wrist_rise=rises[i],
                in_preparation=True,
            )
            for i in range(start, end + 1)
        ]
        best = best_trophy_sample(samples)
        self.assertIsNotNone(best)
        self.assertAlmostEqual(best.time_s, 3.2, delta=0.01)
        self.assertGreater(best.time_s, times[start])


class RepTimeWindowTest(unittest.TestCase):
    """Every detected stroke carries its start–end window in the video.

    The results table's "Time in Video" column and the command-line
    per-stroke lines both display this window, for valid and invalid
    strokes alike, so the window must be present, ordered, and
    non-overlapping on every repetition result.
    """

    def assert_windows_ordered(self, windows):
        for start_s, end_s in windows:
            self.assertLess(start_s, end_s)
        for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
            # Adjacent windows may share at most a boundary sample.
            self.assertLessEqual(prev_end, next_start)

    def test_every_forehand_rep_carries_its_window(self):
        reps = analyze_repetitions(
            "forehand", _three_forehands(), _demo_targets()
        )
        self.assertEqual(len(reps), 3)
        self.assert_windows_ordered(
            [(rep.window_start_s, rep.window_end_s) for rep in reps]
        )
        for rep in reps:
            self.assertLessEqual(rep.window_start_s, rep.peak_time_s)
            self.assertLessEqual(rep.peak_time_s, rep.window_end_s)
            self.assertIsNotNone(rep.contact_time_s)
            self.assertLessEqual(rep.window_start_s, rep.contact_time_s)
            self.assertLessEqual(rep.contact_time_s, rep.window_end_s)

    def test_overhead_reps_carry_windows(self):
        samples = _timeline(_overhead(160.0), _OVERHEAD_GAP, _overhead(170.0))
        reps = analyze_repetitions("overhead", samples, _demo_targets())
        self.assertEqual(len(reps), 2)
        self.assert_windows_ordered(
            [(rep.window_start_s, rep.window_end_s) for rep in reps]
        )
        for rep in reps:
            self.assertLessEqual(rep.window_start_s, rep.peak_time_s)
            self.assertLessEqual(rep.peak_time_s, rep.window_end_s)

    def test_invalid_rep_still_carries_its_window(self):
        from tennis360 import strokes

        real_analyze = strokes.analyze_swing
        calls = {"count": 0}

        def flaky(action, samples, targets=None):
            calls["count"] += 1
            if calls["count"] == 2:
                return None, None, ["No clear swing found in this clip."]
            return real_analyze(action, samples, targets)

        with mock.patch.object(strokes, "analyze_swing", side_effect=flaky):
            reps = analyze_repetitions(
                "forehand", _three_forehands(), _demo_targets()
            )
        self.assertFalse(reps[1].analyzed)
        self.assert_windows_ordered(
            [(rep.window_start_s, rep.window_end_s) for rep in reps]
        )

    def test_serve_action_windows_in_seconds(self):
        centers = [10.0, 30.0, 50.0, 70.0, 90.0, 110.0, 130.0]
        times, rises = _serve_series(centers, length_s=140.0)
        actions = find_serve_actions(times, rises)
        self.assertEqual(len(actions), 7)
        windows = [(times[start], times[end]) for start, end, _ in actions]
        for (start_s, end_s), (_, _, peak) in zip(windows, actions):
            self.assertLess(start_s, end_s)
            self.assertLessEqual(start_s, times[peak])
            self.assertLessEqual(times[peak], end_s)
        for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
            self.assertLess(prev_end, next_start)

    def test_format_time_window(self):
        self.assertEqual(format_time_window(12.36, 15.14), "12.4 s – 15.1 s")
        self.assertEqual(format_time_window(0.0, 2.0), "0.0 s – 2.0 s")


def _diagram_candidate(rep_index, analyzed, **overrides):
    candidate = {
        "rep_index": rep_index,
        "analyzed": analyzed,
        "time_s": rep_index * 10.0,
        "arm": "right",
        "angle": 100.0 + rep_index,
        "minimum": 80.0,
        "maximum": 120.0,
        "moment": "at contact",
        "window_start_s": rep_index * 10.0 - 1.0,
        "window_end_s": rep_index * 10.0 + 1.5,
    }
    candidate.update(overrides)
    return candidate


class StrokeDiagramRenderTest(unittest.TestCase):
    """One skeleton diagram per analyzed stroke; invalid ones get none."""

    def _landmarks(self):
        return [
            SimpleNamespace(x=0.1 * (i % 5), y=0.05 * i) for i in range(33)
        ]

    def test_renders_once_per_analyzed_stroke_never_for_invalid(self):
        candidates = [
            _diagram_candidate(1, True),
            _diagram_candidate(2, False, arm=None, angle=None),
            _diagram_candidate(3, True),
        ]
        extracted_times = []
        builds = []

        def extract(time_s):
            extracted_times.append(time_s)
            return self._landmarks()

        def build(points, *, arm, angle_deg, minimum, maximum):
            builds.append((points, arm, angle_deg, minimum, maximum))
            return b"PNG"

        diagrams = render_stroke_diagrams(candidates, extract, build)
        # Exactly the two analyzed strokes, in stroke order.
        self.assertEqual([rep for rep, _ in diagrams], [1, 3])
        self.assertTrue(all(png == b"PNG" for _, png in diagrams))
        # Landmarks are extracted only for analyzed strokes' key moments.
        self.assertEqual(extracted_times, [10.0, 30.0])
        # Each build received that stroke's own arm, angle, and range.
        self.assertEqual(len(builds), 2)
        self.assertEqual(builds[0][1:], ("right", 101.0, 80.0, 120.0))
        self.assertEqual(builds[1][1:], ("right", 103.0, 80.0, 120.0))
        # Landmarks reach the renderer as plain (x, y) float pairs.
        self.assertEqual(builds[0][0][0], (0.0, 0.0))
        self.assertEqual(builds[0][0][1], (0.1, 0.05))

    def test_analyzed_stroke_without_landmarks_is_skipped(self):
        candidates = [_diagram_candidate(1, True), _diagram_candidate(2, True)]
        builds = []

        def extract(time_s):
            return None if time_s == 10.0 else self._landmarks()

        def build(points, **kwargs):
            builds.append(points)
            return b"PNG"

        diagrams = render_stroke_diagrams(candidates, extract, build)
        self.assertEqual([rep for rep, _ in diagrams], [2])
        self.assertEqual(len(builds), 1)

    def test_analyzed_stroke_without_arm_or_angle_is_not_extracted(self):
        candidates = [_diagram_candidate(1, True, arm=None)]
        extracted = []

        def extract(time_s):
            extracted.append(time_s)
            return self._landmarks()

        diagrams = render_stroke_diagrams(
            candidates, extract, lambda points, **kw: b"PNG"
        )
        self.assertEqual(diagrams, [])
        self.assertEqual(extracted, [])

    def test_extraction_failure_skips_only_that_stroke(self):
        candidates = [_diagram_candidate(1, True), _diagram_candidate(2, True)]

        def extract(time_s):
            if time_s == 10.0:
                raise RuntimeError("frame unreadable")
            return self._landmarks()

        diagrams = render_stroke_diagrams(
            candidates, extract, lambda points, **kw: b"PNG"
        )
        self.assertEqual([rep for rep, _ in diagrams], [2])


class InvalidRepDisplayTest(unittest.TestCase):
    """Invalid repetitions: listed and marked, never recorded."""

    def test_mixed_swing_run_records_only_valid_but_lists_invalid(self):
        from tennis360 import strokes

        real_analyze = strokes.analyze_swing
        calls = {"count": 0}

        def flaky(action, samples, targets=None):
            calls["count"] += 1
            if calls["count"] == 2:
                return None, None, ["No clear swing found in this clip."]
            return real_analyze(action, samples, targets)

        with mock.patch.object(strokes, "analyze_swing", side_effect=flaky):
            reps = analyze_repetitions(
                "forehand", _three_forehands(), _demo_targets()
            )
        # The result list still contains every found repetition.
        self.assertEqual(len(reps), 3)
        # Only the valid ones become records.
        records = swing_rep_records(
            reps,
            source_file="practice.mp4",
            action="forehand",
            arm="right",
        )
        self.assertEqual([r.rep_index for r in records], [1, 3])
        found, recorded = len(reps), len(records)
        self.assertEqual(found - recorded, 1)  # invalid and skipped
        # The invalid repetition carries the marking and the reason.
        self.assertIsNone(swing_rep_invalid_reason(reps[0]))
        reason = swing_rep_invalid_reason(reps[1])
        self.assertEqual(reason, "No clear swing found in this clip.")
        self.assertEqual(
            invalid_rep_result(reason),
            "Invalid — Not Recorded: No clear swing found in this clip.",
        )

    def test_serve_invalid_marking_with_reason(self):
        entry = serve_rep_record(
            rep_index=1,
            trophy_time_s=2.0,
            source_file="serves.mp4",
            angle_degrees=None,
            in_range=None,
            arm="right",
            requested_arm="auto",
        )
        self.assertIsNone(entry)  # never recorded
        reason = serve_rep_invalid_reason(
            "No clear trophy frame was measured in this serve."
        )
        self.assertEqual(
            reason, "No clear trophy frame was measured in this serve."
        )
        self.assertEqual(
            invalid_rep_result(reason),
            "Invalid — Not Recorded: "
            "No clear trophy frame was measured in this serve.",
        )

    def test_invalid_marking_without_reason(self):
        self.assertEqual(invalid_rep_result(None), "Invalid — Not Recorded")
        self.assertIsNone(serve_rep_invalid_reason(None))


if __name__ == "__main__":
    unittest.main()
