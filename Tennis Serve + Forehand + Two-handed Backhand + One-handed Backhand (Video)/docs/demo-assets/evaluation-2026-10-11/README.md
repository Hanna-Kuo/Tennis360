# Saved Teaching Evaluation — October 11, 2026

The files here are outputs of explicitly licensed public inputs, not application
uploads. All 45 photo predictions, labels and input/source-code hashes are saved
in `photos-baseline.json` and `photos-focused.json`. Missing coach/3D labels are
null; they are not perfect accuracy scores.

| Visual preparation coverage | No focus | Fixed small-player focus |
|---|---:|---:|
| Taipei source (8 clear preparation views) | 0/8 | 4/8 |
| All sources (15 preparation views, including occlusion) | 4/15 | 8/15 |
| False acceptance of 28 visually unsuitable/other-stage inputs | 0/28 | 0/28 |

Two Taipei views have uncertain stage labels and are excluded from these phase
fractions. Results concern this development sample; there are no population
accuracy, coach correctness or absolute photo-angle error estimates.

`positive-overlays/` contains four cropped, annotated derivatives of S_030,
S_120, S_200 and S_300 from [the Taipei set](../taipei/README.md), CC BY 4.0.
Credit: Chun-Yi Wang, Kalin Guanlun Lai, Hsu-Chun Huang, Wei-Ting Lin, 2024.
Cropping/landmark drawing was added by TennisPose. `browser-S030.yml`
records the local UI tree, with 4/5 valid readings and an estimated 104.0° elbow.
The crop is a display/measurement aid; no new pixels or ground truth were created.
The four overlays were visually inspected. Current full-page screenshot export
timed out in the test browser; no final screenshot is claimed or substituted
with a generated page image.

`mocap-elbow-angles.csv` and `mocap-summary.json` are derived from
[the attributed Tennis-MoCap samples](../mocap/README.md), CC BY-SA 3.0.
12,000 valid bilateral readings, zero exclusions; maximum acos/atan2 numeric
difference 1.85e-12°. This validates arithmetic on optical-motion-derived
trajectories, not MediaPipe's inferred angle on a photo. Participant tier is
retained for provenance only.

Reproduce from the repository root, using new output directories:

```bash
.venv/bin/python scripts/evaluate_photos.py --without-focus --output archive/class-baseline
.venv/bin/python scripts/evaluate_photos.py --output archive/class-focused --save-overlays
.venv/bin/python scripts/evaluate_mocap.py --report-dir archive/class-mocap
.venv/bin/python -m unittest discover -s tests -v
```
