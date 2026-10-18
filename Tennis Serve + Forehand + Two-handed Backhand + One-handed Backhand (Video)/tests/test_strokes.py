"""Tests for the stroke analysis module.

Covers forehand and backhands. Pure geometry and trajectory heuristics —
no MediaPipe model needed.
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
)


def _demo_targets() -> Targets:
    return Targets(
        ranges={
            "forehand": TargetRange("forehand", 130.0, 170.0, "demo"),
            "backhand-one": TargetRange("backhand-one", 140.0, 175.0, "demo"),
            "backhand-two": TargetRange("backhand-two", 140.0, 175.0, "demo"),
        },
        extras={
            "groundstroke_extras": {
                "followthrough_min_rise": 0.2,
                "shoulder_turn_min_deg": 20.0,
                "contact_in_front_min": 0.15,
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
        for action in ("forehand", "backhand-one", "backhand-two"):
            _, _, suggestions = analyze_swing(action, samples, _demo_targets())
            for text in suggestions:
                self.assertFalse(
                    any("\u4e00" <= ch <= "\u9fff" for ch in text),
                    f"non-English suggestion: {text}",
                )

    def test_suggest_functions_directly(self):
        from tennis360.strokes import StrokeMetrics

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


if __name__ == "__main__":
    unittest.main()
