"""Tests for the stroke analysis module.

Covers forehand, backhands, slice, overhead, volleys, drop shot,
half-volley, and lob. Pure geometry and trajectory heuristics — no MediaPipe model
needed.
"""

import unittest

from tennis360.config import TargetRange, Targets
from tennis360.strokes import (
    SwingSample,
    analyze_swing,
    compute_metrics,
    find_key_moments,
    suggest_backhand_one,
    suggest_backhand_two,
    suggest_forehand,
    suggest_lob,
)


def _demo_targets() -> Targets:
    return Targets(
        ranges={
            "forehand": TargetRange("forehand", 130.0, 170.0, "demo"),
            "backhand-one": TargetRange("backhand-one", 140.0, 175.0, "demo"),
            "backhand-two": TargetRange("backhand-two", 140.0, 175.0, "demo"),
            "slice": TargetRange("slice", 150.0, 175.0, "demo"),
            "overhead": TargetRange("overhead", 150.0, 180.0, "demo"),
            "volley-forehand": TargetRange("volley-forehand", 90.0, 130.0, "demo"),
            "volley-backhand": TargetRange("volley-backhand", 90.0, 130.0, "demo"),
            "drop-shot": TargetRange("drop-shot", 120.0, 160.0, "demo"),
            "half-volley": TargetRange("half-volley", 120.0, 165.0, "demo"),
            "lob": TargetRange("lob", 130.0, 170.0, "demo"),
        },
        extras={
            "groundstroke_extras": {
                "followthrough_min_rise": 0.2,
                "shoulder_turn_min_deg": 20.0,
                "contact_in_front_min": 0.15,
                "source": "demo",
            },
            "stroke_extras": {
                "overhead_contact_height_min": 1.2,
                "overhead_lateral_offset_max": 0.5,
                "volley_backswing_max": 0.4,
                "drop_followthrough_max": 0.6,
                "halfvolley_followthrough_max": 0.6,
                "halfvolley_knee_bend_min": 0.05,
                "halfvolley_contact_height_max": 0.3,
                "slice_wrist_stability_max": 0.15,
                "lob_backswing_depth_max": 0.1,
                "lob_followthrough_min_rise": 0.5,
                "source": "demo",
            },
        },
    )


def _forehand_samples(elbow_at_contact: float = 150.0) -> list[SwingSample]:
    """Synthetic right-hand forehand: wrist goes back, whips forward, finishes high."""

    wrist_x = [0.55, 0.50, 0.40, 0.30, 0.45, 0.75, 0.85, 0.88, 0.90]
    wrist_rise = [0.10, 0.05, 0.00, -0.10, 0.00, 0.20, 0.50, 0.70, 0.80]
    shoulder_angle = [10.0, 15.0, 25.0, 35.0, 30.0, 20.0, 10.0, 5.0, 0.0]
    samples = []
    for i in range(len(wrist_x)):
        samples.append(
            SwingSample(
                index=i * 6,
                time_s=i * 0.2,
                wrist_x=wrist_x[i],
                wrist_rise=wrist_rise[i],
                elbow_angle=elbow_at_contact if i == 5 else 110.0,
                second_elbow_angle=None,
                shoulder_mid_x=0.50,
                shoulder_angle_deg=shoulder_angle[i],
                width_px=640.0,
                scale_px=200.0,
            )
        )
    return samples


class KeyMomentsTest(unittest.TestCase):
    def test_detects_backswing_contact_followthrough(self):
        moments = find_key_moments(_forehand_samples())
        self.assertIsNotNone(moments)
        assert moments is not None
        self.assertEqual(moments.backswing, 3)
        self.assertEqual(moments.contact, 5)
        self.assertEqual(moments.followthrough, 8)
        self.assertEqual(moments.forward_sign, 1.0)
        self.assertTrue(moments.heuristic)

    def test_too_short_returns_none(self):
        self.assertIsNone(find_key_moments(_forehand_samples()[:2]))

    def test_no_motion_returns_none(self):
        flat = [
            SwingSample(
                index=i, time_s=i * 0.2, wrist_x=0.5, wrist_rise=0.1,
                elbow_angle=150.0, second_elbow_angle=None,
                shoulder_mid_x=0.5, shoulder_angle_deg=10.0,
                width_px=640.0, scale_px=200.0,
            )
            for i in range(5)
        ]
        self.assertIsNone(find_key_moments(flat))

    def test_reversed_camera_direction(self):
        samples = _forehand_samples()
        mirrored = [
            SwingSample(
                index=s.index, time_s=s.time_s, wrist_x=1.0 - s.wrist_x,
                wrist_rise=s.wrist_rise, elbow_angle=s.elbow_angle,
                second_elbow_angle=s.second_elbow_angle,
                shoulder_mid_x=1.0 - s.shoulder_mid_x,
                shoulder_angle_deg=s.shoulder_angle_deg,
                width_px=s.width_px, scale_px=s.scale_px,
            )
            for s in samples
        ]
        moments = find_key_moments(mirrored)
        self.assertIsNotNone(moments)
        assert moments is not None
        self.assertEqual(moments.forward_sign, -1.0)
        self.assertEqual(moments.backswing, 3)
        self.assertEqual(moments.contact, 5)


class MetricsTest(unittest.TestCase):
    def test_contact_in_front_positive(self):
        samples = _forehand_samples()
        moments = find_key_moments(samples)
        assert moments is not None
        metrics = compute_metrics(samples, moments)
        # (0.75 - 0.50) * 640 / 200 * +1 = 0.80 body scales
        self.assertAlmostEqual(metrics.contact_in_front or 0.0, 0.80, places=2)
        self.assertAlmostEqual(metrics.followthrough_rise or 0.0, 0.80, places=2)
        self.assertAlmostEqual(metrics.shoulder_turn_deg or 0.0, 35.0, places=2)
        self.assertAlmostEqual(metrics.contact_elbow_deg or 0.0, 150.0, places=2)


class SuggestTest(unittest.TestCase):
    def test_forehand_in_range(self):
        samples = _forehand_samples(elbow_at_contact=150.0)
        moments, metrics, suggestions = analyze_swing("forehand", samples, _demo_targets())
        self.assertIsNotNone(moments)
        assert metrics is not None
        self.assertTrue(metrics.contact_elbow_in_range)
        self.assertTrue(any("inside the demo range" in s for s in suggestions))

    def test_forehand_over_bent(self):
        samples = _forehand_samples(elbow_at_contact=100.0)
        _, metrics, suggestions = analyze_swing("forehand", samples, _demo_targets())
        assert metrics is not None
        self.assertFalse(metrics.contact_elbow_in_range)
        self.assertTrue(any("over-bent" in s for s in suggestions))

    def test_forehand_over_extended(self):
        samples = _forehand_samples(elbow_at_contact=180.0)
        _, _, suggestions = analyze_swing("forehand", samples, _demo_targets())
        self.assertTrue(any("over-extended" in s for s in suggestions))

    def test_forehand_late_contact(self):
        samples = _forehand_samples()
        # Shoulder line ahead of the contact wrist: contact is "late".
        behind = [
            SwingSample(
                index=s.index, time_s=s.time_s, wrist_x=s.wrist_x,
                wrist_rise=s.wrist_rise, elbow_angle=s.elbow_angle,
                second_elbow_angle=s.second_elbow_angle,
                shoulder_mid_x=0.95,
                shoulder_angle_deg=s.shoulder_angle_deg,
                width_px=s.width_px, scale_px=s.scale_px,
            )
            for s in samples
        ]
        moments, metrics, suggestions = analyze_swing("forehand", behind, _demo_targets())
        self.assertIsNotNone(moments)
        assert metrics is not None
        self.assertLess(metrics.contact_in_front or 0.0, 0.15)
        self.assertTrue(any("late" in s for s in suggestions))

    def test_backhand_one_small_turn(self):
        samples = _forehand_samples(elbow_at_contact=155.0)
        flat_turn = [
            SwingSample(
                index=s.index, time_s=s.time_s, wrist_x=s.wrist_x,
                wrist_rise=s.wrist_rise, elbow_angle=s.elbow_angle,
                second_elbow_angle=s.second_elbow_angle,
                shoulder_mid_x=s.shoulder_mid_x,
                shoulder_angle_deg=10.0,
                width_px=s.width_px, scale_px=s.scale_px,
            )
            for s in samples
        ]
        moments, metrics, suggestions = analyze_swing(
            "backhand-one", flat_turn, _demo_targets()
        )
        self.assertIsNotNone(moments)
        self.assertTrue(any("shoulder turn" in s for s in suggestions))

    def test_backhand_two_grades_both_arms(self):
        samples = _forehand_samples(elbow_at_contact=150.0)
        two_handed = [
            SwingSample(
                index=s.index, time_s=s.time_s, wrist_x=s.wrist_x,
                wrist_rise=s.wrist_rise, elbow_angle=s.elbow_angle,
                second_elbow_angle=100.0 if i == 5 else 120.0,
                shoulder_mid_x=s.shoulder_mid_x,
                shoulder_angle_deg=s.shoulder_angle_deg,
                width_px=s.width_px, scale_px=s.scale_px,
            )
            for i, s in enumerate(samples)
        ]
        moments, metrics, suggestions = analyze_swing(
            "backhand-two", two_handed, _demo_targets()
        )
        self.assertIsNotNone(moments)
        assert metrics is not None
        self.assertAlmostEqual(metrics.second_elbow_deg or 0.0, 100.0)
        self.assertTrue(any("support arm" in s for s in suggestions))

    def test_no_swing_explains_itself(self):
        flat = _forehand_samples()[:2]
        moments, metrics, suggestions = analyze_swing("forehand", flat, _demo_targets())
        self.assertIsNone(moments)
        self.assertIsNone(metrics)
        self.assertTrue(any("No clear swing" in s for s in suggestions))

    def test_unknown_action_rejected(self):
        with self.assertRaises(ValueError):
            analyze_swing("not-a-stroke", _forehand_samples(), _demo_targets())

    def test_all_output_is_english(self):
        samples = _forehand_samples(elbow_at_contact=100.0)
        for action in (
            "forehand", "backhand-one", "backhand-two", "slice", "overhead",
            "volley-forehand", "volley-backhand", "drop-shot", "half-volley",
            "lob",
        ):
            _, _, suggestions = analyze_swing(action, samples, _demo_targets())
            for text in suggestions:
                self.assertFalse(
                    any("\u4e00" <= ch <= "\u9fff" for ch in text),
                    f"non-English suggestion: {text}",
                )

    def test_suggest_functions_directly(self):
        from tennis360.strokes import (
            StrokeMetrics,
            suggest_drop_shot,
            suggest_half_volley,
            suggest_overhead,
            suggest_slice,
            suggest_volley_backhand,
            suggest_volley_forehand,
        )

        metrics = StrokeMetrics(
            contact_elbow_deg=150.0,
            contact_elbow_in_range=True,
            contact_in_front=1.0,
            followthrough_rise=0.8,
            shoulder_turn_deg=30.0,
            second_elbow_deg=None,
        )
        targets = _demo_targets()
        self.assertTrue(suggest_forehand(metrics, targets))
        self.assertTrue(suggest_backhand_one(metrics, targets))
        self.assertTrue(suggest_backhand_two(metrics, targets))
        self.assertTrue(suggest_slice(metrics, targets))
        self.assertTrue(suggest_overhead(metrics, targets))
        self.assertTrue(suggest_volley_forehand(metrics, targets))
        self.assertTrue(suggest_volley_backhand(metrics, targets))
        self.assertTrue(suggest_drop_shot(metrics, targets))
        self.assertTrue(suggest_half_volley(metrics, targets))


def _swing_samples(
    wrist_x,
    wrist_rise,
    elbow_at_contact=150.0,
    shoulder_mid_y=None,
    contact_index=None,
):
    """Generic synthetic swing builder for the newer stroke tests."""

    samples = []
    for i in range(len(wrist_x)):
        samples.append(
            SwingSample(
                index=i * 6,
                time_s=i * 0.2,
                wrist_x=wrist_x[i],
                wrist_rise=wrist_rise[i],
                elbow_angle=(
                    elbow_at_contact
                    if contact_index is not None and i == contact_index
                    else 110.0
                ),
                second_elbow_angle=None,
                shoulder_mid_x=0.50,
                shoulder_angle_deg=10.0,
                width_px=640.0,
                scale_px=200.0,
                shoulder_mid_y=(
                    shoulder_mid_y[i] if shoulder_mid_y is not None else 0.5
                ),
            )
        )
    return samples


def _overhead_samples(peak_rise=1.6, elbow=165.0):
    """Wrist rises to a peak (contact) then falls — an overhead smash."""

    return _swing_samples(
        wrist_x=[0.5] * 7,
        wrist_rise=[0.0, 0.2, 0.6, peak_rise, 1.0, 0.3, -0.1],
        elbow_at_contact=elbow,
        contact_index=3,
    )


def _volley_samples(big_backswing=False):
    """Short punching motion; big_backswing=True exaggerates the takeback."""

    if big_backswing:
        wrist_x = [0.50, 0.25, 0.20, 0.45, 0.60, 0.66]
    else:
        wrist_x = [0.50, 0.48, 0.46, 0.55, 0.62, 0.66]
    return _swing_samples(
        wrist_x=wrist_x,
        wrist_rise=[0.0, 0.0, 0.05, 0.10, 0.15, 0.20],
        elbow_at_contact=110.0,
        contact_index=4,
    )


def _drop_shot_samples(long_followthrough=False):
    """Soft swing; long_followthrough=True keeps the wrist traveling."""

    if long_followthrough:
        wrist_x = [0.55, 0.50, 0.40, 0.30, 0.45, 0.75, 0.85, 0.95, 1.05]
    else:
        wrist_x = [0.55, 0.50, 0.40, 0.30, 0.45, 0.75, 0.85, 0.87, 0.88]
    return _swing_samples(
        wrist_x=wrist_x,
        wrist_rise=[0.10, 0.05, 0.00, -0.10, 0.00, 0.20, 0.50, 0.70, 0.80],
        elbow_at_contact=140.0,
        contact_index=6,
    )


def _half_volley_samples(knee_drop=True, contact_rise=0.10):
    """Low swing with optional shoulder drop (knee bend, 2D proxy)."""

    if knee_drop:
        shoulder_mid_y = [0.45, 0.46, 0.48, 0.50, 0.52, 0.55, 0.58, 0.60, 0.60]
    else:
        shoulder_mid_y = [0.45] * 9
    wrist_rise = [0.05, 0.02, 0.00, -0.05, 0.00, contact_rise, 0.15, 0.25, 0.30]
    return _swing_samples(
        wrist_x=[0.55, 0.50, 0.42, 0.35, 0.48, 0.70, 0.80, 0.84, 0.86],
        wrist_rise=wrist_rise,
        elbow_at_contact=140.0,
        contact_index=5,
        shoulder_mid_y=shoulder_mid_y,
    )


class SliceTest(unittest.TestCase):
    def test_slice_end_to_end_in_range(self):
        samples = _forehand_samples(elbow_at_contact=160.0)
        moments, metrics, suggestions = analyze_swing(
            "slice", samples, _demo_targets()
        )
        self.assertIsNotNone(moments)
        assert metrics is not None
        self.assertTrue(metrics.contact_elbow_in_range)
        self.assertTrue(any("inside the demo range" in s for s in suggestions))

    def test_slice_over_bent(self):
        samples = _forehand_samples(elbow_at_contact=120.0)
        _, _, suggestions = analyze_swing("slice", samples, _demo_targets())
        self.assertTrue(any("over-bent" in s for s in suggestions))

    def test_slice_wobbly_wrist_advice(self):
        from tennis360.strokes import StrokeMetrics, suggest_slice

        metrics = StrokeMetrics(
            contact_elbow_deg=160.0,
            contact_elbow_in_range=True,
            contact_in_front=1.0,
            followthrough_rise=0.8,
            shoulder_turn_deg=30.0,
            second_elbow_deg=None,
            wrist_stability=0.50,
        )
        suggestions = suggest_slice(metrics, _demo_targets())
        self.assertTrue(any("firm and stable" in s for s in suggestions))

    def test_slice_steady_wrist_no_advice(self):
        from tennis360.strokes import StrokeMetrics, suggest_slice

        metrics = StrokeMetrics(
            contact_elbow_deg=160.0,
            contact_elbow_in_range=True,
            contact_in_front=1.0,
            followthrough_rise=0.8,
            shoulder_turn_deg=30.0,
            second_elbow_deg=None,
            wrist_stability=0.05,
        )
        suggestions = suggest_slice(metrics, _demo_targets())
        self.assertFalse(any("firm and stable" in s for s in suggestions))


class OverheadTest(unittest.TestCase):
    def test_find_overhead_moments(self):
        from tennis360.strokes import find_overhead_moments

        moments = find_overhead_moments(_overhead_samples())
        self.assertIsNotNone(moments)
        assert moments is not None
        self.assertEqual(moments.backswing, 0)  # preparation: lowest wrist
        self.assertEqual(moments.contact, 3)  # highest wrist
        self.assertEqual(moments.followthrough, 6)
        self.assertTrue(moments.heuristic)

    def test_overhead_too_short_returns_none(self):
        from tennis360.strokes import find_overhead_moments

        self.assertIsNone(find_overhead_moments(_overhead_samples()[:2]))

    def test_overhead_flat_returns_none(self):
        from tennis360.strokes import find_overhead_moments

        flat = _swing_samples([0.5] * 5, [0.5] * 5)
        self.assertIsNone(find_overhead_moments(flat))

    def test_overhead_high_contact_ok(self):
        moments, metrics, suggestions = analyze_swing(
            "overhead", _overhead_samples(peak_rise=1.6), _demo_targets()
        )
        self.assertIsNotNone(moments)
        assert metrics is not None
        self.assertAlmostEqual(metrics.contact_height or 0.0, 1.6, places=2)
        self.assertFalse(any("highest point" in s for s in suggestions))

    def test_overhead_low_contact_advice(self):
        _, _, suggestions = analyze_swing(
            "overhead", _overhead_samples(peak_rise=0.8), _demo_targets()
        )
        self.assertTrue(any("highest point" in s for s in suggestions))

    def test_overhead_uses_vertical_model(self):
        # A flat horizontal swing has no overhead peak: preparation must fail.
        from tennis360.strokes import find_overhead_moments

        self.assertIsNone(find_overhead_moments(_forehand_samples()))


class VolleyTest(unittest.TestCase):
    def test_volley_forehand_compact_ok(self):
        moments, metrics, suggestions = analyze_swing(
            "volley-forehand", _volley_samples(), _demo_targets()
        )
        self.assertIsNotNone(moments)
        assert metrics is not None
        self.assertTrue(metrics.contact_elbow_in_range)
        self.assertFalse(any("compact" in s for s in suggestions))

    def test_volley_forehand_big_backswing(self):
        _, _, suggestions = analyze_swing(
            "volley-forehand", _volley_samples(big_backswing=True), _demo_targets()
        )
        self.assertTrue(any("compact" in s for s in suggestions))

    def test_volley_backhand_runs(self):
        moments, metrics, suggestions = analyze_swing(
            "volley-backhand", _volley_samples(), _demo_targets()
        )
        self.assertIsNotNone(moments)
        self.assertTrue(suggestions)

    def test_volley_no_forward_push_advice(self):
        from tennis360.strokes import (
            StrokeMetrics,
            suggest_volley_forehand,
        )

        metrics = StrokeMetrics(
            contact_elbow_deg=110.0,
            contact_elbow_in_range=True,
            contact_in_front=1.0,
            followthrough_rise=0.2,
            shoulder_turn_deg=None,
            second_elbow_deg=None,
            backswing_compactness=0.1,
            push_forward=False,
        )
        suggestions = suggest_volley_forehand(metrics, _demo_targets())
        self.assertTrue(any("punch through" in s for s in suggestions))

    def test_volley_elbow_out_of_range(self):
        samples = _volley_samples()
        wobbly = [
            sample
            for sample in samples
        ]
        # Elbow 60 deg at the detected contact -> below the 90-130 demo range.
        _, _, suggestions = analyze_swing(
            "volley-forehand",
            _swing_samples(
                wrist_x=[s.wrist_x for s in wobbly],
                wrist_rise=[s.wrist_rise for s in wobbly],
                elbow_at_contact=60.0,
                contact_index=4,
            ),
            _demo_targets(),
        )
        self.assertTrue(any("over-bent" in s for s in suggestions))


class DropShotTest(unittest.TestCase):
    def test_drop_shot_short_followthrough_ok(self):
        moments, metrics, suggestions = analyze_swing(
            "drop-shot", _drop_shot_samples(), _demo_targets()
        )
        self.assertIsNotNone(moments)
        self.assertFalse(any("deaden" in s for s in suggestions))

    def test_drop_shot_long_followthrough(self):
        _, _, suggestions = analyze_swing(
            "drop-shot", _drop_shot_samples(long_followthrough=True), _demo_targets()
        )
        self.assertTrue(any("deaden" in s for s in suggestions))


class HalfVolleyTest(unittest.TestCase):
    def test_half_volley_knee_bend_ok(self):
        moments, metrics, suggestions = analyze_swing(
            "half-volley", _half_volley_samples(knee_drop=True), _demo_targets()
        )
        self.assertIsNotNone(moments)
        assert metrics is not None
        self.assertGreaterEqual(metrics.knee_bend or 0.0, 0.05)
        self.assertFalse(any("knees" in s for s in suggestions))

    def test_half_volley_no_knee_bend(self):
        _, _, suggestions = analyze_swing(
            "half-volley", _half_volley_samples(knee_drop=False), _demo_targets()
        )
        self.assertTrue(any("knees" in s for s in suggestions))

    def test_half_volley_high_contact(self):
        _, _, suggestions = analyze_swing(
            "half-volley",
            _half_volley_samples(knee_drop=True, contact_rise=0.80),
            _demo_targets(),
        )
        self.assertTrue(any("right after the bounce" in s for s in suggestions))


def _lob_samples(deep=True, high_finish=True):
    """Lob: racket dips low on the backswing, whips upward, finishes high."""

    wrist_x = [0.55, 0.52, 0.45, 0.38, 0.42, 0.58, 0.72, 0.80]
    if deep and high_finish:
        wrist_rise = [0.05, -0.10, -0.20, -0.15, 0.05, 0.40, 0.65, 0.75]
    elif not deep:
        wrist_rise = [0.20, 0.30, 0.35, 0.30, 0.35, 0.50, 0.65, 0.75]
    else:  # shallow finish
        wrist_rise = [0.05, -0.10, -0.20, -0.15, 0.05, 0.15, 0.25, 0.30]
    return _swing_samples(
        wrist_x=wrist_x,
        wrist_rise=wrist_rise,
        elbow_at_contact=150.0,
        contact_index=4,
    )


class LobTest(unittest.TestCase):
    def test_lob_good_form_ok(self):
        moments, metrics, suggestions = analyze_swing(
            "lob", _lob_samples(), _demo_targets()
        )
        self.assertIsNotNone(moments)
        assert metrics is not None
        self.assertLessEqual(metrics.backswing_depth or 1.0, 0.1)
        self.assertFalse(any("get under the ball" in s for s in suggestions))
        self.assertFalse(any("finish high" in s for s in suggestions))

    def test_lob_shallow_backswing(self):
        _, _, suggestions = analyze_swing(
            "lob", _lob_samples(deep=False), _demo_targets()
        )
        self.assertTrue(any("get under the ball" in s for s in suggestions))

    def test_lob_low_followthrough(self):
        _, _, suggestions = analyze_swing(
            "lob", _lob_samples(high_finish=False), _demo_targets()
        )
        self.assertTrue(any("finish high" in s for s in suggestions))

    def test_lob_elbow_out_of_range(self):
        samples = _lob_samples()
        wobbly = [
            SwingSample(
                index=s.index,
                time_s=s.time_s,
                wrist_x=s.wrist_x,
                wrist_rise=s.wrist_rise,
                elbow_angle=100.0,
                second_elbow_angle=None,
                shoulder_mid_x=s.shoulder_mid_x,
                shoulder_angle_deg=s.shoulder_angle_deg,
                width_px=s.width_px,
                scale_px=s.scale_px,
                shoulder_mid_y=s.shoulder_mid_y,
            )
            for s in samples
        ]
        _, _, suggestions = analyze_swing("lob", wobbly, _demo_targets())
        self.assertTrue(any("over-bent" in s for s in suggestions))


if __name__ == "__main__":
    unittest.main()
