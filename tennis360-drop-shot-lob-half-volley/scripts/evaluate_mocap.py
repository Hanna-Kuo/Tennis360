#!/usr/bin/env python3
"""Evaluate licensed BVH files offline; writes only an explicit report directory.

Example: python scripts/evaluate_mocap.py --report-dir archive/mocap-report
Optional --tier filename.bvh=RP or =HP preserves a confirmed descriptive tier;
neither tier is a pose-correctness label. Inputs must be licensed/authorized.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tennis360.mocap import ARM_JOINTS, BVHError, evaluate_angles, load_bvh


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "docs/demo-assets/mocap")
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--tier", action="append", default=[], metavar="FILENAME=RP|HP")
    args = parser.parse_args(argv)
    tiers: dict[str, str] = {}
    for entry in args.tier:
        filename, separator, tier = entry.partition("=")
        if not separator or Path(filename).name != filename or tier not in ("RP", "HP") or filename in tiers:
            parser.error("Each --tier must uniquely identify a filename as RP or HP")
        tiers[filename] = tier
    sources = sorted(args.input_dir.glob("*.bvh")) if args.input_dir.is_dir() else []
    if not sources:
        parser.error("No BVH files found in the selected licensed input directory")
    if set(tiers) - {source.name for source in sources}:
        parser.error("A --tier filename is absent from the input directory")
    manifest_path = args.input_dir / "manifest.json"
    metadata: dict[str, dict] = {}
    license_name = None
    provenance = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            license_name = manifest["license"]
            if not isinstance(license_name, str) or not license_name.strip():
                raise ValueError("Manifest license must be a nonempty string")
            provenance = {
                key: manifest.get(key)
                for key in ("license_url", "source_repository", "upstream_commit")
            }
            for entry in manifest["sources"]:
                filename = entry["file"]
                if not isinstance(filename, str) or Path(filename).name != filename or filename in metadata:
                    raise ValueError("Manifest source filenames must be unique basenames")
                tier = entry.get("player_group")
                if tier not in (None, "RP", "HP"):
                    raise ValueError("Manifest player_group must be RP, HP, or null")
                if filename in tiers and tier is not None and tiers[filename] != tier:
                    raise ValueError("Explicit tier conflicts with source manifest")
                metadata[filename] = entry
            if not all(source.name in metadata for source in sources):
                raise ValueError("Every input source must have a manifest record")
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
            parser.error(f"Invalid source manifest: {error}")
    csv_path, summary_path = args.report_dir / "elbow_angles.csv", args.report_dir / "summary.json"
    if csv_path.exists() or summary_path.exists():
        parser.error("Report files already exist; select a new report directory")

    report_rows = []
    summaries = []
    try:
        for source in sources:
            source_metadata = metadata.get(source.name, {})
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            if "sha256" in source_metadata and source_metadata["sha256"] != digest:
                raise BVHError(f"Source checksum differs from manifest: {source.name}")
            motion = load_bvh(source)
            readings, excluded = evaluate_angles(motion)
            per_arm = {}
            for arm, names in ARM_JOINTS.items():
                subset = [reading for reading in readings if reading.arm == arm]
                angles = [reading.angle_degrees for reading in subset]
                per_arm[arm] = {
                    "joints": list(names),
                    "missing_joints": [name for name in names if name not in {joint.name for joint in motion.joints}],
                    "valid_count": len(angles), "excluded_count": excluded[arm],
                    "minimum_degrees": min(angles) if angles else None,
                    "maximum_degrees": max(angles) if angles else None,
                    "mean_degrees": statistics.fmean(angles) if angles else None,
                    "max_numeric_difference_degrees": max((reading.difference_degrees for reading in subset), default=None),
                }
            tier = tiers.get(source.name, source_metadata.get("player_group"))
            summaries.append({
                "source_filename": source.name,
                "sha256": digest,
                "source_url": source_metadata.get("source_url"),
                "descriptive_tier": tier,
                "frame_count": motion.frame_count, "frame_time_seconds": motion.frame_time,
                "last_frame_time_seconds": (motion.frame_count - 1) * motion.frame_time,
                "arms": per_arm,
            })
            for reading in sorted(readings, key=lambda value: (value.frame, value.arm)):
                report_rows.append({"source_filename": source.name, "descriptive_tier": tier, **asdict(reading)})
    except (BVHError, OSError, UnicodeError) as error:
        parser.error(str(error))

    summary = {
        "schema_version": 1,
        "source_license": license_name,
        "derived_data_license": license_name,
        "provenance": provenance,
        "valid_reading_count": len(report_rows),
        "excluded_reading_count": sum(details["excluded_count"] for source in summaries for details in source["arms"].values()),
        "max_numeric_difference_degrees": max((row["difference_degrees"] for row in report_rows), default=None),
        "scope": "Offline framewise shoulder-elbow-wrist 3D geometry comparison",
        "limitations": [
            "Source coordinates retain their original unspecified units and axes.",
            "RP and HP are descriptive participant tiers, never correct/incorrect pose labels.",
            "No RGB photos, Trophy Pose timestamps, coaching labels, MediaPipe detection validation, or app verdicts are provided.",
            "Agreement of acos and atan2 checks numerical geometry, not calibrated pose-estimation accuracy.",
            "Invalid geometry and missing arm joints are excluded from the trajectory CSV and counted in the summary.",
        ],
        "sources": summaries,
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    fields = ["source_filename", "descriptive_tier", "frame", "time_seconds", "arm", "angle_degrees", "independent_degrees", "difference_degrees"]
    with csv_path.open("x", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report_rows)
    with summary_path.open("x", encoding="utf-8") as output:
        json.dump(summary, output, indent=2, allow_nan=False)
        output.write("\n")
    print(f"Evaluated {len(sources)} sources; {len(report_rows)} valid arm readings.")
    print(f"Reports: {csv_path} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
