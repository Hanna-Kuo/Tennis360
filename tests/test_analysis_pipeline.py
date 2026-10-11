"""End-to-end guards for the analysis entry point.

These use synthetic images so they run anywhere the model file is present, and
skip cleanly when it is not.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from tennispose.pose_detector import (
    DEFAULT_MODEL_PATH,
    ModelFileMissingError,
    analyze_rgb_image,
)


def blank_photo(width: int = 640, height: int = 480) -> np.ndarray:
    return np.full((height, width, 3), 210, dtype=np.uint8)


class InputValidationTests(unittest.TestCase):
    """Argument checks run before the model is touched, so they need no model."""

    def test_grayscale_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            analyze_rgb_image(np.zeros((10, 10), dtype=np.uint8))

    def test_unknown_arm_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            analyze_rgb_image(blank_photo(), "both")  # type: ignore[arg-type]

    def test_inverted_range_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            analyze_rgb_image(blank_photo(), demo_minimum=120.0, demo_maximum=80.0)

    def test_out_of_bounds_visibility_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            analyze_rgb_image(blank_photo(), minimum_visibility=1.5)

    def test_missing_model_is_reported_clearly(self) -> None:
        with self.assertRaises(ModelFileMissingError):
            analyze_rgb_image(blank_photo(), model_path=Path("/nonexistent/model.task"))


@unittest.skipUnless(
    DEFAULT_MODEL_PATH.is_file(), f"pose model not downloaded at {DEFAULT_MODEL_PATH}"
)
class EmptyPhotoTests(unittest.TestCase):
    def test_photo_without_a_person_is_refused(self) -> None:
        annotated, report = analyze_rgb_image(blank_photo())

        self.assertEqual(report.status, "cannot_analyze")
        self.assertEqual(report.reason_code, "no_pose")
        self.assertIsNone(report.angle_degrees)
        self.assertEqual(annotated.shape, (480, 640, 3))

    def test_refusal_never_reports_a_score(self) -> None:
        _, report = analyze_rgb_image(blank_photo())

        self.assertIsNone(report.in_demo_range)
        self.assertIsNone(report.angle_degrees)
        self.assertNotEqual(report.message, "")


if __name__ == "__main__":
    unittest.main()
