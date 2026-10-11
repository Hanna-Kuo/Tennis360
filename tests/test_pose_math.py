"""Unit tests for the app's dependency-free geometry and decision rules."""

from __future__ import annotations

import unittest

from tennispose.pose_math import (
    ArmGeometry,
    Point,
    Point3,
    arm_geometry,
    body_scale,
    calculate_elbow_angle,
    calculate_elbow_angle_3d,
    classify_confidence,
    has_reliable_point,
    is_in_preparation_position,
    make_angle_result,
    pool_angles,
)


class ProjectedAngleTests(unittest.TestCase):
    def test_right_angle_is_calculated(self) -> None:
        angle = calculate_elbow_angle(Point(0, 1), Point(0, 0), Point(1, 0))

        self.assertIsNotNone(angle)
        self.assertAlmostEqual(angle, 90.0)

    def test_straight_angle_is_calculated(self) -> None:
        angle = calculate_elbow_angle(Point(-1, 0), Point(0, 0), Point(1, 0))

        self.assertIsNotNone(angle)
        self.assertAlmostEqual(angle, 180.0)

    def test_degenerate_geometry_is_rejected(self) -> None:
        self.assertIsNone(calculate_elbow_angle(Point(0, 0), Point(0, 0), Point(1, 0)))

    def test_non_finite_geometry_is_rejected(self) -> None:
        self.assertIsNone(
            calculate_elbow_angle(Point(float("nan"), 0), Point(0, 0), Point(1, 0))
        )


class WorldAngleTests(unittest.TestCase):
    def test_right_angle_is_calculated_in_three_dimensions(self) -> None:
        angle = calculate_elbow_angle_3d(
            Point3(0, 1, 0), Point3(0, 0, 0), Point3(0, 0, 1)
        )

        self.assertIsNotNone(angle)
        self.assertAlmostEqual(angle, 90.0)

    def test_depth_is_not_ignored(self) -> None:
        """An arm bent purely toward the camera looks straight in 2D but is not."""

        shoulder_3d, elbow_3d, wrist_3d = (
            Point3(0.0, 0.3, 0.0),
            Point3(0.0, 0.0, 0.0),
            Point3(0.0, 0.3, 0.3),
        )
        projected = calculate_elbow_angle(Point(0.0, 0.3), Point(0.0, 0.0), Point(0.0, 0.3))
        spatial = calculate_elbow_angle_3d(shoulder_3d, elbow_3d, wrist_3d)

        self.assertAlmostEqual(projected, 0.0)
        self.assertAlmostEqual(spatial, 45.0)

    def test_degenerate_geometry_is_rejected(self) -> None:
        self.assertIsNone(
            calculate_elbow_angle_3d(Point3(0, 0, 0), Point3(0, 0, 0), Point3(1, 0, 0))
        )

    def test_non_finite_geometry_is_rejected(self) -> None:
        self.assertIsNone(
            calculate_elbow_angle_3d(
                Point3(float("inf"), 0, 0), Point3(0, 0, 0), Point3(1, 0, 0)
            )
        )


class ReliabilityTests(unittest.TestCase):
    def test_visibility_gate_is_inclusive(self) -> None:
        self.assertTrue(has_reliable_point(Point(0.5, 0.5, 0.35), 0.35))
        self.assertFalse(has_reliable_point(Point(0.5, 0.5, 0.34), 0.35))

    def test_non_finite_point_is_never_reliable(self) -> None:
        self.assertFalse(has_reliable_point(Point(float("nan"), 0.5, 1.0), 0.35))


class BodyScaleTests(unittest.TestCase):
    def test_torso_length_is_preferred(self) -> None:
        scale = body_scale(
            Point(0.4, 0.3, 1.0),
            Point(0.6, 0.3, 1.0),
            Point(0.42, 0.6, 1.0),
            Point(0.58, 0.6, 1.0),
            width=1000,
            height=1000,
        )

        self.assertIsNotNone(scale)
        self.assertAlmostEqual(scale, 300.0, places=0)

    def test_shoulder_width_is_used_when_hips_are_hidden(self) -> None:
        scale = body_scale(
            Point(0.3, 0.3, 1.0),
            Point(0.7, 0.3, 1.0),
            Point(0.42, 0.9, 0.01),
            Point(0.58, 0.9, 0.01),
            width=1000,
            height=1000,
        )

        self.assertAlmostEqual(scale, 400.0, places=0)

    def test_tiny_subject_has_no_usable_scale(self) -> None:
        self.assertIsNone(
            body_scale(
                Point(0.50, 0.50, 1.0),
                Point(0.51, 0.50, 1.0),
                Point(0.50, 0.51, 1.0),
                Point(0.51, 0.51, 1.0),
                width=100,
                height=100,
            )
        )


class PreparationGateTests(unittest.TestCase):
    def test_raised_racket_arm_passes(self) -> None:
        """Federer's measured trophy geometry: wrist just above, elbow just below."""

        self.assertTrue(is_in_preparation_position(ArmGeometry(0.09, -0.38)))

    def test_hand_resting_at_the_waist_is_rejected(self) -> None:
        self.assertFalse(is_in_preparation_position(ArmGeometry(-0.77, -0.50)))

    def test_arm_swung_down_after_contact_is_rejected(self) -> None:
        self.assertFalse(is_in_preparation_position(ArmGeometry(-0.54, -0.49)))

    def test_elbow_hanging_at_the_side_is_rejected(self) -> None:
        self.assertFalse(is_in_preparation_position(ArmGeometry(-0.18, -0.71)))

    def test_non_finite_geometry_is_rejected(self) -> None:
        self.assertFalse(is_in_preparation_position(ArmGeometry(float("nan"), 0.0)))


class ArmGeometryTests(unittest.TestCase):
    def test_wrist_above_shoulder_is_positive(self) -> None:
        geometry = arm_geometry(
            Point(0.5, 0.5), Point(0.5, 0.45), Point(0.5, 0.3), scale=100.0, height=1000
        )

        self.assertAlmostEqual(geometry.wrist_rise, 2.0)
        self.assertAlmostEqual(geometry.elbow_rise, 0.5)


class PoolingTests(unittest.TestCase):
    def test_median_resists_one_bad_pass(self) -> None:
        result = pool_angles([137.2, 92.1, 85.3], 80.0, 120.0)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.degrees, 92.1)
        self.assertTrue(result.in_demo_range)

    def test_agreeing_majority_cannot_hide_a_conflicting_pass(self) -> None:
        result = pool_angles([170.5, 168.3, 130.6], 80.0, 120.0)

        self.assertEqual(result.confidence, "low")
        self.assertAlmostEqual(result.degrees, 168.3)
        self.assertFalse(result.in_demo_range)

    def test_full_disagreement_is_low_confidence(self) -> None:
        result = pool_angles([40.0, 100.0, 175.0], 80.0, 120.0)

        self.assertEqual(result.confidence, "low")

    def test_full_spread_drives_agreement(self) -> None:
        result = pool_angles([102.9, 100.9, 72.1], 80.0, 120.0)

        self.assertEqual(result.confidence, "low")
        self.assertAlmostEqual(result.spread_degrees, 30.8, places=1)

    def test_no_usable_measurement_returns_none(self) -> None:
        self.assertIsNone(pool_angles([], 80.0, 120.0))
        self.assertIsNone(pool_angles([float("nan")], 80.0, 120.0))

    def test_confidence_bands_are_inclusive(self) -> None:
        self.assertEqual(classify_confidence(8.0), "high")
        self.assertEqual(classify_confidence(8.1), "moderate")
        self.assertEqual(classify_confidence(20.0), "moderate")
        self.assertEqual(classify_confidence(20.1), "low")


class DemoRangeTests(unittest.TestCase):
    def test_demo_range_is_inclusive(self) -> None:
        self.assertTrue(make_angle_result(80.0, 80.0, 120.0).in_demo_range)
        self.assertTrue(make_angle_result(120.0, 80.0, 120.0).in_demo_range)
        self.assertFalse(make_angle_result(120.1, 80.0, 120.0).in_demo_range)


if __name__ == "__main__":
    unittest.main()
