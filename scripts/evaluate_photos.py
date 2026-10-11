"""Replay the licensed repository photo set, never arbitrary app uploads.

Run: .venv/bin/python scripts/evaluate_photos.py --output archive/photo-replay
Saved outputs are permitted only for the explicit licensed teaching set.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tennispose.evaluation import summarize_photo_results
from tennispose.pose_detector import analyze_rgb_image, DEFAULT_MODEL_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--without-focus", action="store_true", help="Replay the baseline without small-player focusing")
    parser.add_argument("--save-overlays", action="store_true", help="Save attributed derivatives of these licensed inputs only")
    args = parser.parse_args()
    assets = ROOT / "docs/demo-assets"
    manifest = json.loads((assets / "photo-benchmark.json").read_text())
    rows = []
    for label in manifest["cases"]:
        path = (assets / label["file"]).resolve()
        if not path.is_relative_to(assets.resolve()) or path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise ValueError("Only manifest-listed licensed documentation photos are allowed")
        if not label.get("license_source"):
            raise ValueError(f"Missing attribution review for {path.name}")
        with Image.open(path) as image:
            rgb = np.array(image.convert("RGB"))
        overlay, report = analyze_rgb_image(rgb, focus_player=not args.without_focus)
        if args.save_overlays:
            target = args.output / "overlays" / label["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(overlay).save(target)
        rows.append({"label": label, "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "report": asdict(report)})
        print(label["file"], report.status, report.angle_degrees, report.reason_code)
    result = {
        "schema_version": 1,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                          for name in ("tennispose/pose_detector.py", "tennispose/pose_math.py",
                                       "tennispose/annotate.py", "tennispose/evaluation.py", "scripts/evaluate_photos.py")},
        "model_sha256": hashlib.sha256(DEFAULT_MODEL_PATH.read_bytes()).hexdigest(),
        "range": [80, 120],
        "player_focus": not args.without_focus,
        "summary": summarize_photo_results(rows),
        "groups": {group: summarize_photo_results([r for r in rows if r["label"]["group"] == group])
                   for group in sorted({r["label"]["group"] for r in rows})},
        "cases": rows,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "photo-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
