"""Regressions for false verdicts, malformed detections and estimated-angle limits.

Mock landmarks isolate pipeline contracts; they are not real-photo accuracy data.
"""

from __future__ import annotations

from dataclasses import replace
from math import cos, radians, sin
import unittest
from unittest.mock import patch

import numpy as np
import cv2

from tennispose.pose_detector import analyze_rgb_image, _restore_landmarks, _same_subject_arm
from tennispose.pose_math import (
    Point, Point3, calculate_elbow_angle, calculate_elbow_angle_3d,
    has_reliable_point, pool_angles, arm_geometry, torso_up_axis,
)


def pose(angle: float = 100.0, *, mirrored: bool = False):
    """Preparation cues with an analytically specified racket elbow angle."""
    points = [Point(0.5, 0.5) for _ in range(33)]
    world = [Point3(0, 0, 0) for _ in range(33)]
    for i, xy in {11: (.45, .45), 12: (.55, .45), 13: (.4, .35),
                  14: (.65, .48), 15: (.4, .25), 16: (.7, .4),
                  23: (.45, .65), 24: (.55, .65)}.items():
        points[i] = Point(*xy)
    world[12], world[14] = Point3(0, .3, 0), Point3(.3, .3, 0)
    world[16] = Point3(.3 - .3 * cos(radians(angle)), .3 - .3 * sin(radians(angle)), 0)
    world[11], world[13], world[15] = Point3(-.2, .3, 0), Point3(-.2, 0, 0), Point3(-.2, -.3, 0)
    if mirrored:
        swap = {11: 12, 12: 11, 13: 14, 14: 13, 15: 16, 16: 15, 23: 24, 24: 23}
        points = [replace(points[swap.get(i, i)], x=1-points[swap.get(i, i)].x) for i in range(33)]
        world = [replace(world[swap.get(i, i)], x=-world[swap.get(i, i)].x) for i in range(33)]
    return points, world


def run(detections, **kwargs):
    image = np.full((480, 640, 3), 210, dtype=np.uint8)
    with patch("tennispose.pose_detector.get_detector", return_value=object()), \
         patch("tennispose.pose_detector._detect", side_effect=detections) as detector:
        annotation, report = analyze_rgb_image(image, **kwargs)
    return annotation, report, detector.call_count


def five(angle=100.0):
    return [pose(angle), pose(angle), pose(angle, mirrored=True), pose(angle), pose(angle)]


class PipelineQualityTests(unittest.TestCase):
    def assert_refused(self, report, reason):
        self.assertEqual(report.status, "cannot_analyze")
        self.assertEqual(report.reason_code, reason)
        self.assertIsNone(report.angle_degrees)
        self.assertIsNone(report.in_demo_range)

    def test_valid_original_and_all_four_variants_are_measured(self):
        annotation, report, count = run(five())
        self.assertEqual(count, 5)
        self.assertEqual(annotation.shape, (480, 640, 3))
        self.assertEqual(report.sample_count, 5)
        self.assertEqual(report.angle_degrees, 100)
        self.assertTrue(report.in_demo_range)

    def test_low_visibility_repeats_cannot_replace_a_valid_red_original(self):
        bad = pose(90)
        bad[0][16] = replace(bad[0][16], visibility=.01)
        _, report, _ = run([pose(150), bad, None, bad, bad])
        self.assert_refused(report, "unstable")

    def test_only_one_or_two_valid_readings_cannot_be_high_agreement(self):
        for detections in [[pose(), None, None, None, None],
                           [pose(), pose(), None, None, None]]:
            with self.subTest(valid=sum(p is not None for p in detections)):
                _, report, _ = run(detections)
                self.assert_refused(report, "unstable")

    def test_three_surviving_readings_have_moderate_support(self):
        _, report, _ = run([pose(), pose(), pose(mirrored=True), None, None])
        self.assertEqual(report.status, "analyzed")
        self.assertEqual(report.confidence, "moderate")
        self.assertEqual(report.sample_count, 3)

    def test_low_presence_repeat_is_rejected(self):
        bad = pose()
        bad[0][16] = replace(bad[0][16], presence=.01)
        _, report, _ = run([pose(), bad, None, bad, bad])
        self.assert_refused(report, "unstable")

    def test_unreliable_world_point_is_rejected(self):
        bad = pose()
        bad[1][16] = replace(bad[1][16], visibility=.01)
        _, report, _ = run([bad])
        self.assert_refused(report, "ambiguous_arm")

    def test_degenerate_or_nonfinite_world_point_is_refused(self):
        for wrist in [Point3(.3, .3, 0), Point3(float("nan"), 0, 0)]:
            bad = pose(); bad[1][16] = wrist
            _, report, _ = run([bad])
            self.assert_refused(report, "ambiguous_arm")

    def test_phase_gate_is_independent_of_target_and_manual_selection(self):
        contact = pose(150)
        contact[0][14], contact[0][16] = Point(.6, .2), Point(.6, .1)
        for arm in ("auto", "right"):
            _, report, _ = run([contact], arm=arm, demo_minimum=40, demo_maximum=180)
            self.assert_refused(report, "not_trophy_pose")

    def test_red_preparation_is_not_excluded_by_phase_gate(self):
        _, report, _ = run(five(150))
        self.assertEqual(report.status, "analyzed")
        self.assertFalse(report.in_demo_range)
        self.assertEqual(report.angle_degrees, 150)

    def test_wrong_phase_repeats_are_not_pooled(self):
        bad = pose(90)
        bad[0][16] = Point(.6, .8)
        _, report, _ = run([pose(), bad, None, bad, bad])
        self.assert_refused(report, "unstable")

    def test_repeats_from_a_different_person_cannot_support_primary(self):
        moved = pose()
        moved[0][:] = [replace(p, x=p.x-.2) for p in moved[0]]
        mirrored = pose(mirrored=True)
        mirrored[0][:] = [replace(p, x=p.x+.2) for p in mirrored[0]]
        _, report, _ = run([pose(), moved, mirrored, moved, moved])
        self.assert_refused(report, "unstable")

    def test_selected_arm_location_drift_cannot_support_primary(self):
        moved = pose()
        for i in (14, 16):
            moved[0][i] = replace(moved[0][i], x=moved[0][i].x-.25)
        _, report, _ = run([pose(), moved, None, moved, moved])
        self.assert_refused(report, "unstable")

    def test_mirror_side_is_mapped_back_to_the_same_player_arm(self):
        _, report, _ = run(five(130))
        self.assertEqual(report.arm, "right")
        self.assertEqual(report.angle_degrees, 130)
        self.assertFalse(report.in_demo_range)

    def test_boundary_crossing_with_small_spread_is_refused(self):
        _, report, _ = run([pose(119), pose(121), pose(120, mirrored=True), pose(119), pose(121)])
        self.assert_refused(report, "borderline")

    def test_short_landmark_arrays_do_not_crash(self):
        _, report, _ = run([([Point(.5, .5)] * 10, [Point3(0, 0, 0)] * 10)])
        self.assert_refused(report, "invalid_landmarks")

    def test_nan_image_landmark_is_not_drawn_and_no_score_is_generated(self):
        bad = pose(); bad[0][16] = Point(float("nan"), .4)
        _, report, _ = run([bad])
        self.assert_refused(report, "ambiguous_arm")

    def test_nonfinite_target_is_rejected_before_inference(self):
        with self.assertRaises(ValueError):
            run([], demo_minimum=float("nan"))


class GeometryEvidenceTests(unittest.TestCase):
    def test_real_affine_transforms_restore_the_original_arm(self):
        original, _ = pose()
        width, height = 640, 480
        transforms = [
            (np.array([[.75, 0, 0], [0, .75, 0]]), (480, 360), False),
            (np.array([[-1., 0, width-1], [0, 1, 0]]), (width, height), True),
            (cv2.getRotationMatrix2D((width/2, height/2), -8, 1), (width, height), False),
            (cv2.getRotationMatrix2D((width/2, height/2), 8, 1), (width, height), False),
        ]
        swap = {11: 12, 12: 11, 13: 14, 14: 13, 15: 16, 16: 15, 23: 24, 24: 23}
        for transform, size, mirrored in transforms:
            transformed = []
            for i in range(33):
                p = original[swap.get(i, i) if mirrored else i]
                x, y = transform @ np.array([p.x*width, p.y*height, 1])
                transformed.append(replace(p, x=float(x/size[0]), y=float(y/size[1])))
            restored = _restore_landmarks(transformed, transform, size, (width, height), mirrored)
            self.assertTrue(_same_subject_arm(original, restored, "right", width, height))
            for a, b in zip(original, restored):
                self.assertAlmostEqual(a.x, b.x)
                self.assertAlmostEqual(a.y, b.y)

    def test_known_3d_angles_across_rotations_and_scales(self):
        # Analytical 3D inputs test geometry, not MediaPipe's photo accuracy.
        for angle in (45, 79.9, 80, 90, 120, 120.1, 150, 179):
            for rotation in (0, 37, 90):
                for scale in (.1, 1, 3):
                    r = radians(rotation)
                    matrix = np.array([[cos(r), 0, sin(r)], [0, 1, 0], [-sin(r), 0, cos(r)]])
                    points = [np.array([1, 0, 0]), np.zeros(3),
                              np.array([cos(radians(angle)), sin(radians(angle)), 0])]
                    transformed = [Point3(*(matrix @ p * scale + np.array([.1, .2, .3]))) for p in points]
                    with self.subTest(angle=angle, rotation=rotation, scale=scale):
                        self.assertAlmostEqual(calculate_elbow_angle_3d(*transformed), angle, places=8)

    def test_projected_comparison_uses_pixel_aspect_ratio(self):
        angle = calculate_elbow_angle(Point(.1, .3), Point(.2, .2), Point(.3, .3), width=200, height=100)
        self.assertAlmostEqual(angle, 126.869897645844, places=8)

    def test_out_of_frame_or_absent_points_are_not_reliable(self):
        self.assertFalse(has_reliable_point(Point(1.01, .5), .35))
        self.assertFalse(has_reliable_point(Point(.5, .5, presence=.49), .35))

    def test_camera_roll_does_not_change_torso_relative_cues(self):
        points, _ = pose(); width = height = 640
        original = arm_geometry(points[12], points[14], points[16], 128, height,
                                width=width, up=torso_up_axis(points, width, height))
        r = radians(30)
        rotated = [replace(p, x=.5 + (p.x-.5)*cos(r)-(p.y-.5)*sin(r),
                            y=.5 + (p.x-.5)*sin(r)+(p.y-.5)*cos(r)) for p in points]
        geometry = arm_geometry(rotated[12], rotated[14], rotated[16], 128, height,
                                width=width, up=torso_up_axis(rotated, width, height))
        self.assertAlmostEqual(geometry.wrist_rise, original.wrist_rise)
        self.assertAlmostEqual(geometry.elbow_rise, original.elbow_rise)

    def test_observed_bounds_are_not_symmetric_about_the_median(self):
        result = pool_angles([90, 91, 96], 80, 120)
        self.assertEqual((result.minimum_degrees, result.degrees, result.maximum_degrees), (90, 91, 96))

    def test_a_reliable_outlier_cannot_be_hidden_by_the_median(self):
        result = pool_angles([100, 101, 102, 102, 72], 80, 120)
        self.assertEqual(result.confidence, "low")
        self.assertFalse(result.verdict_consistent)


if __name__ == "__main__":
    unittest.main()
