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
(backswing / contact / follow-through for swings, trophy pose for the serve)
and the same demo-range honesty labeling. When the Live version gains a new
stroke, the Python version gains the matching analysis in
`tennis360/strokes.py` plus a CLI `--action` value, target ranges in
`tennis360/default_targets.yaml`, and tests — in the same change.

Implemented swing actions (2026-10-13): `forehand`, `backhand-one`,
`backhand-two`. Serve is analyzed via the trophy-pose photo flow and the
serve video scanner. Other strokes (slice, overhead, volleys, drop-shot,
half-volley, lob) are planned for later packages.

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

# History, trend chart, report export
python -m tennis360.cli history --action forehand --limit 20
python -m tennis360.cli trend --action forehand --out trend.png
python -m tennis360.cli report --out report.xlsx   # or report.csv

# Wrist trajectory plot (2D / 3D)
python -m tennis360.cli trajectory forehand1.mp4 --out traj.png
python -m tennis360.cli trajectory forehand1.mp4 --out traj3d.png --three-d

# Skeleton-annotated video output
python -m tennis360.cli annotate-video forehand1.mp4 --out annotated.mp4

# Automatic keyframe extraction (trophy pose + heuristic contact hint)
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

All swing actions use the same three key moments, detected
heuristically from the wrist trajectory: **backswing** (wrist farthest back),
**contact** (peak forward wrist speed), **follow-through** (highest wrist
after contact). The exact contact frame cannot be certified from monocular
landmarks.

| Action | Checkpoints |
|---|---|
| `forehand` (right hand) | Elbow angle at contact (demo 130–170°), contact point in front of body, follow-through height |
| `backhand-one` | Elbow angle at contact (demo 140–175°), shoulder-turn amplitude (2D proxy), follow-through height |
| `backhand-two` | Both elbows at contact (demo 140–175°), body rotation (2D proxy), contact point in front of body |

Each run prints English adjustment suggestions. For two-handed backhand both
arms are measured; the second arm is reported as the support arm. All
thresholds are demonstration references (`source: demo`), not validated
coaching standards — a coach overrides them via `default_targets.yaml`.

## Honesty labels

- Every default target range is a **demonstration reference**
  (`source: demo`), not a validated coaching, medical, or biomechanical
  standard; `config-show` and reports always show the source.
- Key-moment detection is heuristic; the CLI prints "(heuristic key frame)".
- The shoulder-turn amplitude is a 2D proxy, not a true body-rotation angle.
- Reference comparison ships with no professional-player data; the template
  requires the user to fill in their own data.
- Charts render English-only (no CJK font needed).
