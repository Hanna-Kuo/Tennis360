"""Regression suite over the authorized reference serve photos.

The phase/arm labels come from visual inspection. Numeric expectations are
model-output regression snapshots, not measured 3D ground truth.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from tennispose.pose_detector import DEFAULT_MODEL_PATH, analyze_rgb_image


EXPECTATIONS = json.loads(
    (Path(__file__).parent / "reference_expectations.json").read_text(encoding="utf-8")
)
SAMPLE_DIR = Path(
    os.environ.get(
        "TENNISPOSE_SAMPLE_DIR",
        Path(__file__).resolve().parent.parent / "docs" / "demo-assets" / "reference-photos",
    )
)


def load_photo(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert("RGB"))


@unittest.skipUnless(DEFAULT_MODEL_PATH.is_file(), "pose model not downloaded")
@unittest.skipUnless(SAMPLE_DIR.is_dir(), f"reference photos not found at {SAMPLE_DIR}")
class ReferencePhotoTests(unittest.TestCase):
    def test_every_reference_photo_matches_its_verified_expectation(self) -> None:
        tolerance = EXPECTATIONS["tolerance"]
        for case in EXPECTATIONS["cases"]:
            path = SAMPLE_DIR / case["file"]
            with self.subTest(photo=case["file"], shows=case["pose"]):
                if not path.is_file():
                    self.skipTest(f"{path} is not available")

                _, report = analyze_rgb_image(
                    load_photo(path),
                    EXPECTATIONS["arm"],
                    demo_minimum=EXPECTATIONS["trophy_minimum"],
                    demo_maximum=EXPECTATIONS["trophy_maximum"],
                )

                self.assertEqual(report.status, case["status"])
                if case["status"] == "cannot_analyze":
                    self.assertEqual(report.reason_code, case["reason_code"])
                    self.assertIsNone(report.angle_degrees)
                    continue

                self.assertEqual(report.arm, case["arm"])
                self.assertEqual(report.in_demo_range, case["in_demo_range"])
                self.assertAlmostEqual(
                    report.angle_degrees,
                    case["angle_degrees"],
                    delta=tolerance,
                    msg=f"{case['file']} elbow angle drifted beyond {tolerance} degrees",
                )

    def test_supported_trophy_photos_pass_and_uncertain_one_is_refused(self) -> None:
        """A genuine trophy photo is refused when its 3D estimates conflict."""

        green = [case for case in EXPECTATIONS["cases"] if case.get("in_demo_range")]
        self.assertEqual(len(green), 3)
        for case in green:
            path = SAMPLE_DIR / case["file"]
            with self.subTest(photo=case["file"]):
                if not path.is_file():
                    self.skipTest(f"{path} is not available")
                _, report = analyze_rgb_image(load_photo(path), "auto")
                self.assertTrue(report.in_demo_range)

    def test_wrong_phase_frames_refuse_with_wide_target_and_manual_arms(self) -> None:
        for filename in ("01_dominic_pagon.jpg", "05_gokberk_ergeneman.jpg",
                         "06_nicolas_mahut.jpg", "10_sharapova_serve.jpg"):
            path = SAMPLE_DIR / filename
            if not path.is_file():
                self.skipTest(f"{path} is not available")
            for arm in ("auto", "left", "right"):
                with self.subTest(photo=filename, arm=arm):
                    _, report = analyze_rgb_image(load_photo(path), arm,
                                                  demo_minimum=40, demo_maximum=180)
                    self.assertEqual(report.status, "cannot_analyze")
                    self.assertIsNone(report.angle_degrees)
                    self.assertIsNone(report.in_demo_range)


if __name__ == "__main__":
    unittest.main()
