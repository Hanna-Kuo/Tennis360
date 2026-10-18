"""Offline BVH transform, validation, real-frame geometry, and CLI contracts."""

from __future__ import annotations

import csv
import hashlib
import json
from math import cos, radians, sin
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from tennis360.mocap import (
    BVHError, evaluate_angles, independent_angle, joint_positions, load_bvh, parse_bvh,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_NAMES = ("adorozco_Servicio.bvh", "jarua_Servicio.bvh")
SAMPLE_FOLDERS = (
    ROOT / "docs/demo-assets/mocap",
    ROOT / "archive/dataset-research-2026-10-11/tennis-mocap/data",
)
SAMPLE_FOLDER = next((folder for folder in SAMPLE_FOLDERS if all((folder / name).is_file() for name in SAMPLE_NAMES)), None)


def bvh(hierarchy: str, rows: str, frame_count: int = 1, frame_time: str = "0.01") -> str:
    return f"HIERARCHY\n{hierarchy}\nMOTION\nFrames: {frame_count}\nFrame Time: {frame_time}\n{rows}\n"


SIMPLE = """ROOT Root {
 OFFSET 0 0 0
 CHANNELS 3 Zrotation Xrotation Yrotation
 JOINT Child {
  OFFSET 1 0 0
  CHANNELS 0
  End Site { OFFSET 0 1 0 }
 }
}"""

ARM = """ROOT Root {
 OFFSET 0 0 0
 CHANNELS 3 Zrotation Xrotation Yrotation
 JOINT LeftCollar {
  OFFSET 3 0 0
  CHANNELS 0
  JOINT LeftShoulder {
   OFFSET 0 2 0
   CHANNELS 0
   JOINT LeftElbow {
    OFFSET 1 0 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    JOINT LeftWrist { OFFSET 1 0 0 CHANNELS 0 }
   }
  }
 }
}"""


class TransformTests(unittest.TestCase):
    def test_noncommuting_declared_intrinsic_order(self) -> None:
        coordinates = joint_positions(parse_bvh(bvh(SIMPLE, "30 40 50")))
        z, x, y = map(radians, (30, 40, 50))
        # Independently expanded Rz(Rx(Ry([1, 0, 0]))), not parser matrix code.
        expected = (
            cos(z) * cos(y) - sin(z) * sin(x) * sin(y),
            sin(z) * cos(y) + cos(z) * sin(x) * sin(y),
            -cos(x) * sin(y),
        )
        np.testing.assert_allclose(coordinates["Child"][0], expected, atol=1e-12)
        wrong_order = (cos(y) * cos(z), sin(z), -sin(y) * cos(z))
        self.assertGreater(np.linalg.norm(coordinates["Child"][0] - wrong_order), 0.1)

    def test_arbitrary_declared_rotation_order_is_used(self) -> None:
        hierarchy = SIMPLE.replace("Zrotation Xrotation Yrotation", "Yrotation Xrotation Zrotation")
        coordinates = joint_positions(parse_bvh(bvh(hierarchy, "90 90 0")))
        np.testing.assert_allclose(coordinates["Child"][0], (0, 0, -1), atol=1e-12)

    def test_root_translation_and_offset_precede_rotation(self) -> None:
        hierarchy = """ROOT Root {
 OFFSET 10 20 30
 CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
 JOINT Child {
  OFFSET 2 0 0
  CHANNELS 3 Xrotation Yrotation Zrotation
  End Site { OFFSET 0 1 0 }
 }
}"""
        positions = joint_positions(parse_bvh(bvh(hierarchy, "3 4 5 90 0 0 90 0 0")))
        np.testing.assert_allclose(positions["Root"][0], (13, 24, 35), atol=1e-12)
        # Own X rotation does not rotate Child's own offset.
        np.testing.assert_allclose(positions["Child"][0], (13, 26, 35), atol=1e-12)
        np.testing.assert_allclose(positions["Child:EndSite"][0], (13, 26, 36), atol=1e-12)

    def test_interleaved_translation_honors_declared_order(self) -> None:
        hierarchy = "ROOT Root { OFFSET 0 0 0 CHANNELS 2 Zrotation Xposition }"
        position = joint_positions(parse_bvh(bvh(hierarchy, "90 2")))["Root"][0]
        np.testing.assert_allclose(position, (0, 2, 0), atol=1e-12)

    def test_source_units_are_not_rescaled(self) -> None:
        hierarchy = SIMPLE.replace("OFFSET 1 0 0", "OFFSET 1234 0 0")
        positions = joint_positions(parse_bvh(bvh(hierarchy, "0 0 0")))
        self.assertEqual(positions["Child"][0, 0], 1234)

    def test_each_frame_uses_its_own_channels(self) -> None:
        motion = parse_bvh(bvh(SIMPLE, "0 0 0\n90 0 0", frame_count=2))
        np.testing.assert_allclose(joint_positions(motion)["Child"], [(1, 0, 0), (0, 1, 0)], atol=1e-12)
        self.assertFalse(motion.frames.flags.writeable)

    def test_finite_input_overflow_is_rejected(self) -> None:
        hierarchy = """ROOT Root { OFFSET 1e308 0 0 CHANNELS 1 Xposition
 JOINT Child { OFFSET 1e308 0 0 CHANNELS 0 } }"""
        with self.assertRaises(BVHError):
            joint_positions(parse_bvh(bvh(hierarchy, "1e308")))


class ParserValidationTests(unittest.TestCase):
    def test_malformed_inputs_are_rejected(self) -> None:
        valid = bvh(SIMPLE, "0 0 0")
        invalid = {
            "frame count mismatch": valid.replace("Frames: 1", "Frames: 2"),
            "extra frame": valid + "0 0 0\n",
            "channel width short": valid.replace("\n0 0 0\n", "\n0 0\n"),
            "channel width long": valid.replace("\n0 0 0\n", "\n0 0 0 0\n"),
            "wrong numeric value": valid.replace("\n0 0 0\n", "\noops 0 0\n"),
            "nan motion": valid.replace("\n0 0 0\n", "\nnan 0 0\n"),
            "infinite motion": valid.replace("\n0 0 0\n", "\ninf 0 0\n"),
            "infinite offset": valid.replace("OFFSET 1 0 0", "OFFSET inf 0 0"),
            "zero time": valid.replace("Frame Time: 0.01", "Frame Time: 0"),
            "nan time": valid.replace("Frame Time: 0.01", "Frame Time: nan"),
            "negative time": valid.replace("Frame Time: 0.01", "Frame Time: -1"),
            "zero frames": valid.replace("Frames: 1", "Frames: 0"),
            "overflowing timestamps": bvh(SIMPLE, "0 0 0\n0 0 0\n0 0 0", frame_count=3, frame_time="1e308"),
            "fractional channel count": valid.replace("CHANNELS 3", "CHANNELS 3.0"),
            "unknown channel": valid.replace("Zrotation", "Qrotation"),
            "duplicate channel": valid.replace("Xrotation", "Zrotation"),
            "duplicate joint": valid.replace("JOINT Child", "JOINT Root"),
            "missing closing brace": valid.replace("}\nMOTION", "\nMOTION"),
            "extra root": valid.replace("MOTION", "ROOT Extra { OFFSET 0 0 0 CHANNELS 0 }\nMOTION"),
            "multiple motion sections": valid + "MOTION\n",
            "missing hierarchy": valid.replace("HIERARCHY", ""),
            "end site with channels": valid.replace("End Site { OFFSET 0 1 0 }", "End Site { OFFSET 0 1 0 CHANNELS 0 }"),
            "duplicate end site": valid.replace("End Site { OFFSET 0 1 0 }", "End Site { OFFSET 0 1 0 } End Site { OFFSET 1 0 0 }"),
        }
        for label, text in invalid.items():
            with self.subTest(label=label), self.assertRaises(BVHError):
                parse_bvh(text)


class GeometryTests(unittest.TestCase):
    def test_shoulder_is_used_instead_of_collar(self) -> None:
        motion = parse_bvh(bvh(ARM, "0 0 0 90 0 0"))
        readings, excluded = evaluate_angles(motion)
        self.assertEqual(len(readings), 1)
        self.assertAlmostEqual(readings[0].angle_degrees, 90)
        self.assertAlmostEqual(readings[0].independent_degrees, 90)
        self.assertEqual(excluded, {"left": 0, "right": 1})
        positions = joint_positions(motion)
        wrong = independent_angle(*(positions[name][0] for name in ("LeftCollar", "LeftElbow", "LeftWrist")))
        self.assertGreater(abs(wrong - readings[0].angle_degrees), 60)

    def test_degenerate_geometry_is_excluded(self) -> None:
        hierarchy = ARM.replace("OFFSET 1 0 0", "OFFSET 0 0 0", 1)
        readings, excluded = evaluate_angles(parse_bvh(bvh(hierarchy, "0 0 0 90 0 0")))
        self.assertEqual(readings, [])
        self.assertEqual(excluded, {"left": 1, "right": 1})

    def test_missing_joints_are_excluded_without_fabricated_angles(self) -> None:
        readings, excluded = evaluate_angles(parse_bvh(bvh(SIMPLE, "0 0 0")))
        self.assertEqual(readings, [])
        self.assertEqual(excluded, {"left": 1, "right": 1})

    def test_independent_oracle_rejects_degenerate_and_nonfinite_geometry(self) -> None:
        zero = np.zeros(3)
        self.assertIsNone(independent_angle(zero, zero, np.ones(3)))
        self.assertIsNone(independent_angle(np.array([float("nan"), 0, 0]), zero, np.ones(3)))

    def test_frame_timestamps_are_zero_based(self) -> None:
        readings, _ = evaluate_angles(parse_bvh(bvh(ARM, "0 0 0 90 0 0\n0 0 0 45 0 0", frame_count=2)))
        self.assertEqual([(reading.frame, reading.time_seconds) for reading in readings], [(0, 0), (1, 0.01)])


class CLIContractTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_mocap.py"), *arguments], capture_output=True, text=True, check=False)

    def test_licensed_manifest_and_csv_provenance_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            input_dir = Path(temporary) / "licensed"
            input_dir.mkdir()
            sample = input_dir / "sample.bvh"
            sample.write_text(bvh(ARM, "0 0 0 90 0 0"), encoding="utf-8")
            manifest = {"license": "CC BY-SA 3.0", "sources": [{"file": sample.name, "player_group": "RP", "source_url": "https://example.org/authorized-source", "sha256": hashlib.sha256(sample.read_bytes()).hexdigest()}]}
            (input_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            output_dir = Path(temporary) / "reports"
            arguments = ("--input-dir", str(input_dir), "--report-dir", str(output_dir))
            result = self.run_cli(*arguments)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((output_dir / "summary.json").read_text())
            self.assertEqual(summary["derived_data_license"], "CC BY-SA 3.0")
            self.assertEqual(summary["sources"][0]["descriptive_tier"], "RP")
            self.assertEqual(summary["sources"][0]["arms"]["right"]["valid_count"], 0)
            self.assertIsNone(summary["sources"][0]["arms"]["right"]["mean_degrees"])
            with (output_dir / "elbow_angles.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source_filename"], sample.name)
            self.assertEqual(rows[0]["arm"], "left")
            self.assertEqual(rows[0]["descriptive_tier"], "RP")
            before = (output_dir / "summary.json").read_bytes()
            rerun = self.run_cli(*arguments)
            self.assertNotEqual(rerun.returncode, 0)
            self.assertEqual((output_dir / "summary.json").read_bytes(), before)

    def test_checksum_mismatch_and_tier_conflict_write_no_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            input_dir = Path(temporary) / "licensed"
            input_dir.mkdir()
            sample = input_dir / "sample.bvh"
            sample.write_text(bvh(ARM, "0 0 0 90 0 0"), encoding="utf-8")
            manifest = {"license": "CC BY-SA 3.0", "sources": [{"file": sample.name, "player_group": "HP", "sha256": "incorrect"}]}
            (input_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            output_dir = Path(temporary) / "reports"
            arguments = ("--input-dir", str(input_dir), "--report-dir", str(output_dir))
            for extra in ((), ("--tier", "sample.bvh=RP")):
                with self.subTest(extra=extra):
                    result = self.run_cli(*arguments, *extra)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output_dir.exists())

    def test_no_manifest_keeps_unknown_tier_and_license_null(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            input_dir = Path(temporary) / "licensed"
            input_dir.mkdir()
            (input_dir / "sample.bvh").write_text(bvh(SIMPLE, "0 0 0"), encoding="utf-8")
            output_dir = Path(temporary) / "reports"
            result = self.run_cli("--input-dir", str(input_dir), "--report-dir", str(output_dir))
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((output_dir / "summary.json").read_text())
            self.assertIsNone(summary["source_license"])
            self.assertIsNone(summary["sources"][0]["descriptive_tier"])


@unittest.skipUnless(SAMPLE_FOLDER is not None, "Licensed real BVH samples are unavailable")
class LicensedSampleTests(unittest.TestCase):
    def test_both_actual_sequences_all_frames_and_bone_lengths(self) -> None:
        for name in SAMPLE_NAMES:
            with self.subTest(source=name):
                motion = load_bvh(SAMPLE_FOLDER / name)
                self.assertEqual(motion.frame_count, 3000)
                self.assertEqual(motion.frame_time, 0.01)
                readings, excluded = evaluate_angles(motion)
                self.assertEqual(len(readings), 6000)
                self.assertEqual(excluded, {"left": 0, "right": 0})
                self.assertLess(max(reading.difference_degrees for reading in readings), 1e-8)
                self.assertTrue(all(0 <= reading.angle_degrees <= 180 for reading in readings))
                positions = joint_positions(motion)
                joints = {joint.name: joint for joint in motion.joints}
                for side in ("Left", "Right"):
                    for proximal, distal in (("Shoulder", "Elbow"), ("Elbow", "Wrist")):
                        distances = np.linalg.norm(positions[side + distal] - positions[side + proximal], axis=1)
                        expected = np.linalg.norm(joints[side + distal].offset)
                        np.testing.assert_allclose(distances, expected, atol=1e-10)


if __name__ == "__main__":
    unittest.main()
