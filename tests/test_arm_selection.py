"""Tests for racket-arm selection and the trophy-position gate.

These run without the model file: they feed the selector the same measurements
the detector would produce, taken from the verified reference photos.
"""

from __future__ import annotations

import unittest

from tennispose.pose_detector import ArmObservation, _select_arm
from tennispose.pose_math import ArmGeometry, Point, is_in_preparation_position


def observation(
    arm: str,
    *,
    angle: float | None,
    wrist_rise: float,
    elbow_rise: float,
    reliable: bool = True,
) -> ArmObservation:
    """Build one arm measurement with only the fields selection depends on."""

    geometry = ArmGeometry(wrist_rise=wrist_rise, elbow_rise=elbow_rise)
    return ArmObservation(
        arm=arm,
        shoulder=Point(0.5, 0.5),
        elbow=Point(0.5, 0.5),
        wrist=Point(0.5, 0.5),
        geometry=geometry,
        angle_3d=angle,
        angle_2d=angle,
        minimum_visibility=1.0 if reliable else 0.01,
        reliable=reliable,
        in_preparation=is_in_preparation_position(geometry),
    )


class AutoSelectionTests(unittest.TestCase):
    def test_bent_racket_arm_is_chosen_over_straight_tossing_arm(self) -> None:
        """Federer: left arm extended to toss, right arm bent holding the racket."""

        selection = _select_arm(
            "auto",
            {
                "left": observation("left", angle=170.5, wrist_rise=0.80, elbow_rise=0.37),
                "right": observation("right", angle=82.6, wrist_rise=0.09, elbow_rise=-0.38),
            },
        )

        self.assertIsNone(selection.report)
        self.assertEqual(selection.arm, "right")
        self.assertTrue(selection.arm_was_detected)

    def test_left_handed_player_is_detected(self) -> None:
        """McEnroe serves left-handed; the selector must not assume right."""

        selection = _select_arm(
            "auto",
            {
                "left": observation("left", angle=99.3, wrist_rise=0.24, elbow_rise=-0.18),
                "right": observation("right", angle=143.7, wrist_rise=0.34, elbow_rise=0.04),
            },
        )

        self.assertEqual(selection.arm, "left")
        self.assertTrue(selection.arm_was_detected)

    def test_ready_stance_is_not_scored(self) -> None:
        selection = _select_arm(
            "auto",
            {
                "left": observation("left", angle=159.6, wrist_rise=-0.92, elbow_rise=-0.57),
                "right": observation("right", angle=151.1, wrist_rise=-0.77, elbow_rise=-0.50),
            },
        )

        self.assertIsNotNone(selection.report)
        self.assertEqual(selection.report.reason_code, "not_trophy_pose")

    def test_contact_frame_is_refused(self) -> None:
        """Mahut at contact: a lowered toss arm cannot support preparation."""

        selection = _select_arm(
            "auto",
            {
                "left": observation("left", angle=117.7, wrist_rise=-0.54, elbow_rise=-0.49),
                "right": observation("right", angle=170.5, wrist_rise=0.74, elbow_rise=0.44),
            },
        )

        self.assertEqual(selection.report.reason_code, "not_trophy_pose")

    def test_hidden_racket_arm_is_ambiguous_rather_than_guessed(self) -> None:
        """Ostapenko from behind: only the tossing arm is visible, so refuse."""

        selection = _select_arm(
            "auto",
            {
                "left": observation("left", angle=128.7, wrist_rise=0.55, elbow_rise=0.20),
                "right": observation(
                    "right", angle=111.3, wrist_rise=-0.44, elbow_rise=-0.44, reliable=False
                ),
            },
        )

        self.assertIsNotNone(selection.report)
        self.assertEqual(selection.report.reason_code, "ambiguous_arm")

    def test_no_visible_arm_is_refused(self) -> None:
        selection = _select_arm(
            "auto",
            {
                "left": observation(
                    "left", angle=148.3, wrist_rise=-0.60, elbow_rise=-0.23, reliable=False
                ),
                "right": observation(
                    "right", angle=145.9, wrist_rise=-0.60, elbow_rise=-0.21, reliable=False
                ),
            },
        )

        self.assertEqual(selection.report.reason_code, "no_reliable_arm")


class ManualSelectionTests(unittest.TestCase):
    def test_explicit_choice_still_requires_preparation(self) -> None:
        selection = _select_arm(
            "left",
            {
                "left": observation("left", angle=170.5, wrist_rise=0.80, elbow_rise=0.37),
                "right": observation("right", angle=82.6, wrist_rise=0.09, elbow_rise=-0.38),
            },
        )

        self.assertEqual(selection.report.reason_code, "not_trophy_pose")

    def test_explicit_choice_of_a_lowered_arm_is_refused(self) -> None:
        selection = _select_arm(
            "left",
            {
                "left": observation("left", angle=117.7, wrist_rise=-0.54, elbow_rise=-0.49),
                "right": observation("right", angle=170.5, wrist_rise=0.74, elbow_rise=0.44),
            },
        )

        self.assertEqual(selection.report.reason_code, "not_trophy_pose")

    def test_explicit_choice_of_a_hidden_arm_is_refused(self) -> None:
        selection = _select_arm(
            "right",
            {
                "left": observation("left", angle=128.7, wrist_rise=0.55, elbow_rise=0.20),
                "right": observation(
                    "right", angle=111.3, wrist_rise=-0.44, elbow_rise=-0.44, reliable=False
                ),
            },
        )

        self.assertEqual(selection.report.reason_code, "arm_not_visible")


if __name__ == "__main__":
    unittest.main()
