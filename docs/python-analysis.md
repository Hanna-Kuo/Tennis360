# TennisPose Desktop Deep Analysis (Python CLI)

> Runs locally, command-line interface. Analysis **results** (numbers,
> verdicts) may be stored in a local SQLite history; raw photo and video
> bytes are never written to disk by these commands. All user-visible
> output is English-only, matching the mobile Live app.

## Scope note

The features in this directory extend beyond the original `AGENTS.md`
single-photo scope. They were built 2026-10-04 / 2026-10-08 with the user's
explicit approval (batch video analysis, local cross-day history, report
export, trajectory plots, annotated video, keyframes, multi-angle fusion,
coach-adjustable target ranges, reference comparison, and groundstroke
analysis). The Streamlit single-photo MVP's behavior and privacy boundary
are unaffected.

## Two-version parity principle

TennisPose ships in two versions that must analyze the same strokes:

- **TennisPose Live** (mobile web app): real-time analysis with voice cues.
- **TennisPose Python** (this directory): deep post-session analysis.

Rule: **every stroke analysis the Live version has, the Python version must
also have.** Both versions use the same checkpoints per stroke
(backswing / contact / follow-through for swings, preparation / contact /
follow-through for the overhead, trophy pose for the serve) and the same
demo-range honesty labeling. When the Live version gains a new stroke,
the Python version gains the matching analysis in
`tennis360/strokes.py` plus a CLI `--action` value, target ranges in
`tennis360/default_targets.yaml`, and tests — in the same change.

Implemented swing actions: `forehand`, `forehand-slice`, `backhand-one`,
`backhand-two`, `backhand-slice`, `overhead`, `volley-forehand`,
`volley-backhand`, `drop-shot`, `half-volley`, `lob`. The two slice actions
share the same slice analysis and target range; the user selects which
slice the clip shows.
Serve is analyzed via the trophy-pose photo flow and the serve video
scanner. All 12 actions are now implemented; the action set is complete.

## Installation

Requires 64-bit Python 3.11 (same as the main program), then:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Added dependencies: `matplotlib` (trend/trajectory charts), `pandas` +
`openpyxl` (Excel reports), `pyyaml` (coach config file). Model download
follows the main README's `scripts/bootstrap.py` flow
(`models/pose_landmarker_heavy.task`).

## Usage

All commands start with `python -m tennis360.cli` (venv activated):

```bash
# Serve: batch-analyze videos/photos, results stored in local history
python -m tennis360.cli analyze serve1.mp4 serve2.mp4 photo1.jpg \
    --action serve --arm auto --angle side

# Groundstrokes: forehand (right hand), one-handed / two-handed backhand
python -m tennis360.cli analyze forehand1.mp4 --action forehand --arm right
python -m tennis360.cli analyze backhand1.mp4 --action backhand-one
python -m tennis360.cli analyze backhand1.mp4 --action backhand-two

# Slices, overhead, volleys
python -m tennis360.cli analyze slice1.mp4 --action backhand-slice
python -m tennis360.cli analyze slice2.mp4 --action forehand-slice
python -m tennis360.cli analyze smash1.mp4 --action overhead
python -m tennis360.cli analyze volley1.mp4 --action volley-forehand
python -m tennis360.cli analyze volley1.mp4 --action volley-backhand

# Drop shot, lob, half-volley
python -m tennis360.cli analyze drop1.mp4 --action drop-shot
python -m tennis360.cli analyze lob1.mp4 --action lob
python -m tennis360.cli analyze halfvolley1.mp4 --action half-volley

# History, trend chart, report export
python -m tennis360.cli history --action forehand --limit 20
python -m tennis360.cli trend --action forehand --out trend.png
python -m tennis360.cli report --out report.xlsx   # or report.csv

# Wrist trajectory plot (2D / 3D)
python -m tennis360.cli trajectory forehand1.mp4 --out traj.png
python -m tennis360.cli trajectory forehand1.mp4 --out traj3d.png --three-d

# Skeleton-annotated video output
python -m tennis360.cli annotate-video forehand1.mp4 --out annotated.mp4

# Automatic keyframe extraction (trophy pose + estimated contact hint)
python -m tennis360.cli keyframes serve1.mp4 --out keyframes/

# Multi-angle fusion: side view (elbow angle) + front view (toss/turn)
python -m tennis360.cli multi-angle --side side.mp4 --front front.mp4

# Coach-adjustable target ranges
python -m tennis360.cli config-show
python -m tennis360.cli config-init --out my_targets.yaml
# Edit my_targets.yaml in a text editor, set source to coach, then:
python -m tennis360.cli analyze forehand1.mp4 --action forehand \
    --config my_targets.yaml

# Reference comparison (bring your own reference data)
python -m tennis360.cli reference-template --out my_reference.json
# Fill in coach-measured values, then:
python -m tennis360.cli compare --action forehand --metric elbow_angle_deg \
    --value 152 --reference my_reference.json
```

The history database defaults to `~/.tennis360/history.db`; use `--db` to
point elsewhere.

## What each swing analysis measures

The overhead uses a vertical key-moment model — **preparation** (lowest
wrist), **contact** (highest wrist), **follow-through** (lowest wrist after
contact). All other swing actions use the same three key moments, estimated
from the wrist trajectory: **backswing** (wrist farthest back),
**contact** (peak forward wrist speed), **follow-through** (highest wrist
after contact). The exact contact frame cannot be certified from monocular
landmarks. Both searches are bounded to the single swing that contains the
chosen contact, so a clip with several swings never pairs one swing's
backswing or follow-through with another swing's contact, and the three
moments are always in time order.

| Action | Checkpoints |
|---|---|
| `forehand` (right hand) | Elbow angle at contact (demo 130–170°), contact point in front of body, follow-through height |
| `backhand-one` | Elbow angle at contact (demo 140–175°), shoulder-turn amplitude (2D image estimate), follow-through height |
| `backhand-two` | Both elbows at contact (demo 140–175°), body rotation (2D image estimate), contact point in front of body |
| `backhand-slice` | Elbow angle at contact (demo 150–175°), wrist stability (std dev of wrist height), contact in front, follow-through height |
| `forehand-slice` | Same checkpoints as `backhand-slice` (demo 150–175°); the two slice actions share one analysis |
| `overhead` | Elbow angle at contact (demo 150–180°), contact height above shoulder, lateral balance at contact (2D image estimate) |
| `volley-forehand` | Elbow angle at contact (demo 90–130°), backswing compactness, contact in front, forward push through the ball |
| `volley-backhand` | Same checkpoints as forehand volley (demo 90–130°) |
| `drop-shot` | Elbow angle at contact (demo 120–160°), follow-through length (short = soft touch; wrist tension itself is not measurable from landmarks), contact in front |
| `half-volley` | Elbow angle at contact (demo 120–165°), knee bend via shoulder drop (2D image estimate), low contact height, compact follow-through |
| `lob` | Elbow angle at contact (demo 130–170°), backswing depth (racket low to lift the ball), follow-through height (must finish high) |

Each run prints English adjustment suggestions. For two-handed backhand both
arms are measured; the second arm is reported as the support arm. All
thresholds are demonstration references (`source: demo`), not validated
coaching standards — a coach overrides them via `default_targets.yaml`.

## Honesty labels

- Every default target range is a **demonstration reference**
  (`source: demo`), not a validated coaching, medical, or biomechanical
  standard; `config-show` and reports always show the source.
- Key-moment detection is an estimate; the CLI prints "(Estimated Key Moment)".
- The shoulder-turn amplitude is estimated from the flat 2D image, not a true body-rotation angle.
- Reference comparison ships with no professional-player data; the template
  requires the user to fill in their own data.
- Charts render English-only (no CJK font needed).
