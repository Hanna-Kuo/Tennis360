
# Tennis360 - Tennis Pose and Technique Analysis

> Stage: competition MVP | Product: local Streamlit web application | Deployment: none

Tennis360 is a computer vision-based tennis training application designed to help players analyze and improve their technique through body pose detection, joint-angle measurements, and visual feedback.

The application aims to support all major tennis strokes and positions, including serves, forehands, backhands, volleys, overheads, slices, ready positions, footwork, and recovery movements.

Tennis360 uses MediaPipe pose estimation to identify body landmarks, measure joint angles, and examine body alignment. Players can upload tennis photographs and receive annotated results that help them better understand their positioning and technique.

The goal is to make tennis technique analysis more accessible, allowing players to review their form, identify potential areas for improvement, and develop a better understanding of their movements without requiring specialized motion-capture equipment.

The current MVP analyzes one authorized tennis serve Trophy Pose photograph in a local browser session. The user uploads a JPEG or PNG; the application locates the racket arm, measures the shoulder-elbow-wrist angle using MediaPipe's estimated 3D world landmarks, and returns an annotated green, red, or cannot-analyze result.

Future development will expand the application to additional tennis movements, full-body joint measurements, and movement-specific feedback.

Tennis360 is an educational training aid. It is not a medical product, injury-prevention system, or replacement for professional coaching. Technique evaluation criteria require appropriate research and validation.

## How the Measurement Works

Tennis360 analyzes tennis positioning using anatomical landmarks detected through MediaPipe PoseLandmarker.

The system estimates the locations of key body landmarks, including the shoulders, elbows, wrists, hips, knees, ankles, and feet. These landmarks provide the foundation for measuring joint angles and examining body positioning.

The intended analysis process includes five main stages:

1. **Tennis position identification:** Identify the stroke or body position being analyzed, such as a serve, forehand, backhand, volley, overhead, or ready position. Future versions may support automatic position recognition and manual movement selection.

2. **Body landmark detection:** Locate the player's anatomical landmarks and determine which joints are relevant to the selected tennis movement.

3. **Joint-angle measurement:** Calculate angles between connected body segments using estimated 3D world landmarks. Measurements may include elbow flexion, knee flexion, shoulder-related angles, hip angles, and ankle angles.

4. **Measurement reliability checks:** Evaluate landmark visibility, coordinate validity, body-segment geometry, and measurement consistency before accepting results.

5. **Technique feedback:** Display annotated measurements and compare them with movement-specific reference criteria to help users understand their positioning.

Different tennis strokes require different analysis criteria. Appropriate body alignment during a forehand may differ from that of a serve, volley, or backhand.

### Tennis Positions and Movements

Tennis360 aims to analyze the following tennis movements:

| Category | Positions and Movements | Potential Measurements |
|---|---|---|
| Serves | Starting stance, ball toss, Trophy Pose, racket drop, contact, follow-through, landing | Shoulder alignment, elbow angle, knee bend, trunk positioning |
| Forehands | Preparation, unit turn, backswing, contact, follow-through, recovery | Shoulder rotation, hip alignment, elbow positioning, knee flexion |
| Backhands | One-handed and two-handed preparation, backswing, contact, follow-through | Arm extension, elbow angles, shoulder alignment, trunk rotation |
| Volleys | Forehand volley, backhand volley, preparation, contact, recovery | Elbow positioning, upper-body posture, knee flexion |
| Overheads | Preparation, positioning, contact, follow-through | Shoulder positioning, elbow alignment, trunk extension |
| Slices | Forehand slice, backhand slice, contact, follow-through | Arm positioning, shoulder alignment, body posture |
| Specialty Shots | Drop shots, lobs, approach shots, half-volleys | Joint positioning, stroke preparation, balance |
| Ready Position | Athletic stance, racket preparation, split step | Knee flexion, stance width, hip alignment |
| Footwork | Lateral movement, forward and backward movement, recovery steps | Lower-body alignment, balance, body positioning |

These categories represent the intended Tennis360 scope. The current prototype supports serve Trophy Pose elbow-angle analysis, while additional movement types are planned.

### Current Measurement Implementation

The existing MVP focuses on measuring the racket-arm elbow angle during the serve Trophy Pose.

When the detected player occupies a small part of the photo, a fixed, target-independent crop improves the model's view before measurement. The crop is kept in memory, checked against the original shoulders, and displayed as the annotated result. Localization readings never enter the angle pool.

The pipeline checks three separate questions before displaying a verdict:

1. **Is this a supported preparation view?** Torso-normalized racket-wrist and elbow positions, together with an elevated opposite hand, support a preparation-like pose. The gate is independent of the target elbow range. Both automatic and manual arm selection must pass it.

2. **Can the same arm be measured reliably?** Each of five passes (original, downscaled, mirrored, and rotations of -8/+8 degrees) rechecks image/world landmark visibility, presence, finite coordinates, segment geometry, and preparation cues. Inverse image transforms verify that repeats still refer to the original person's arm. Missing or invalid readings never enter the pool.

3. **Do the valid estimates support one verdict?** At least three valid passes, a full spread of at most 20 degrees, and no target-boundary crossing are required. The median is reported alongside the actual observed minimum and maximum. A single reading or an agreeing majority cannot hide a reliable conflicting reading.

The angle uses **estimated** MediaPipe 3D world landmarks. These account for inferred depth but are not motion-capture ground truth.

The pixel-aspect-correct 2D angle is a comparison only. Repeat agreement is not an accuracy probability or a calibrated confidence interval.

The current 80–120 degree inclusive elbow-angle interval is configurable demonstration logic, not a validated coaching or clinical standard.

Future versions will use movement-specific measurements and evaluation criteria instead of applying one demonstration interval across different tennis positions.

See [research and current validation](docs/validation.md) for evidence, thresholds, and limitations.

## MVP Scope

### Current Features

- A local Streamlit interface served from `streamlit_app.py`.
- JPEG and PNG content validation for one still image, with a 10 MB upload and 20 megapixel decode limit.
- Automatic racket-arm detection, with a manual left/right override.
- Local CPU inference with MediaPipe PoseLandmarker, loaded once per process.
- Shoulder, elbow, and wrist reliability checks before any angle is shown.
- A preparation gate for both automatic and manual selection; insufficient stage cues produce a refusal.
- Three-point elbow-angle geometry from estimated 3D world landmarks, pooled over five validated passes.
- Inclusive, adjustable 80–120 degree demonstration feedback with observed bounds and repeat agreement.
- Annotated in-range (green), adjustment (red), or cannot-analyze result.
- No account, backend, database, cloud upload, remote processing service, API key, saved history, camera, or video.

### Planned Features

- Support for all major tennis strokes and body positions.
- Forehand and backhand technique analysis.
- One-handed and two-handed backhand differentiation.
- Serve analysis across multiple movement phases.
- Forehand and backhand volley analysis.
- Overhead, slice, and specialty-shot analysis.
- Athletic ready-position and split-step analysis.
- Footwork and recovery-position analysis.
- Full-body measurements involving shoulders, elbows, wrists, hips, knees, and ankles.
- Automatic tennis movement identification.
- Manual selection of tennis stroke or position.
- Movement-specific joint-angle reference criteria.
- Full-body skeletal overlays and annotated measurements.
- Detailed positioning feedback for different stroke phases.
- Side-by-side pose comparisons.
- Potential video-based movement analysis.
- Practice progress tracking and comparison features.

The planned features will be introduced as the measurement pipeline, evaluation criteria, and supporting tests are developed.

## Technology

| Responsibility | Implementation |
|---|---|
| Local web UI | Streamlit |
| Runtime | 64-bit Python 3.11 |
| Pose landmarks | MediaPipe Tasks PoseLandmarker, local CPU delegate |
| Geometry, gating, and feedback | `tennis360.pose_math` |
| Landmark extraction and arm selection | `tennis360.pose_detector` |
| Result drawing | `tennis360.annotate` |
| Image validation | `tennis360.image_input` |
| Evaluation | `tennis360.evaluation` |
| Motion-capture geometry | `tennis360.mocap` |
| Tests | Python `unittest` |
| Dependencies | Pinned in `requirements.txt` |

The browser is a local interface to the Python process, and photo inference runs locally.

The application code contains no photo-upload service. However, the installed MediaPipe 0.10.35 binary emitted background Clearcut uploader failure messages during verification; local inference is not a guarantee that every dependency makes zero network attempts.

See [the dependency privacy caveat](docs/security-and-privacy.md#dependency-network-caveat).

The internal Python package is `tennis360`. The public-facing application name is Tennis360.

Future development may introduce additional modules for movement classification, full-body measurements, and stroke-specific feedback.

## Run Locally

Install **64-bit Python 3.11** first, then extract the complete project to a writable local folder.

The launchers do not install Python, change system settings, or require administrator privileges.

Do not copy another computer's `.venv` folder.

See [the Traditional Chinese teaching guide](docs/teaching-guide.zh-TW.md) for the classroom lesson and exercises.

- **Windows:** Double-click `start.bat`. The launcher checks the existing project environment, `py -3.11`, then `python`. When installing Python, include the Python launcher and enable the PATH option.

- **macOS:** Double-click `start.command`. If the extracted ZIP lost executable permission, open Terminal in the project folder and run `bash start.command`. If macOS blocks a downloaded file, follow your school's software policy; do not disable system security. The terminal command is also a fallback when Finder opens the script as text.

Python installers are available from [python.org](https://www.python.org/downloads/).

For Windows/macOS installer-based classrooms, the [Python 3.11.9 release](https://www.python.org/downloads/release/python-3119/) has platform installers; use the school's approved Python 3.11 distribution when available.

Newer 3.11 patch releases may use a different distribution method.

The current package pins require compatible binary wheels; the launchers stop instead of attempting a compiler-based installation on an unsupported platform.

Windows and Intel Mac runtime compatibility must be checked on those machines; a successful Apple Silicon Mac run does not establish it.

On first launch, `scripts/bootstrap.py` creates `.venv`, installs `requirements.txt`, downloads the versioned official heavy model (~29 MB), verifies its SHA-256, checks imports and model loading, and starts Streamlit.

Allow several minutes and an internet connection before class.

Subsequent runs reuse the packages when the requirements fingerprint is unchanged and reuse the verified model without downloading.

Keep the terminal open while using the app; press **Ctrl+C** there to stop it.

If no browser opens, visit **http://127.0.0.1:8501** on the same computer.

The launcher binds only to `127.0.0.1` and disables Streamlit usage statistics.

This is a local app, not a public deployment.

A busy port produces a clear error instead of starting another service on an unexpected address.

Optional terminal commands from the project folder:

```bash
# macOS: install and verify before class, without opening the app
bash start.command --setup-only

# Recheck/install requirements after a package problem (internet required)
bash start.command --repair
```

```bat
rem Windows Command Prompt equivalents
start.bat --setup-only
start.bat --repair
```

If an existing `.venv` is broken or incompatible, the launcher preserves it and stops.

Close the app, rename `.venv` to `.venv-backup`, and retry.

`--repair` reruns normal pip installation; it does not rebuild a broken environment or force-reinstall damaged files.

For a model checksum error, rename the indicated model file and retry.

Interrupted downloads use temporary files and never become accepted models.

For a stale `.tennispose-setup.lock`, first close all setup terminals, then remove that lock file and retry.

Package/network errors remain visible in the terminal; show the error to the teacher instead of repeatedly changing Python versions.

Manual equivalent (Python 3.11 must be installed):

```bash
python3.11 -m venv .venv
.venv/bin/python scripts/bootstrap.py
```

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe scripts\bootstrap.py
```

Open the local URL shown by Streamlit and upload a photo you own or are authorized to analyze.

For the current MVP, the uploaded image must show a supported serve preparation position.

The racket arm is detected automatically; override it in the sidebar if the photo is unusual.

The page runs the local analysis immediately for the current upload and settings.

Future versions will allow players to analyze additional tennis strokes and positions.

Do not upload photos to a public deployment: public hosting is outside this MVP.

## Verify

```bash
.venv/bin/python -m unittest discover -s tests -v
```

`tests/test_reference_photos.py` replays ten authorized reference serve photos through the full pipeline and asserts the arm chosen, the verdict, and the angle against `tests/reference_expectations.json`.

These are model-output regression snapshots, not real 3D angle labels.

The licensed repository folder is the default; `TENNISPOSE_SAMPLE_DIR` can override it.

Missing photos/model are reported as skipped checks, not passes.

The October 11, 2026 suite passed 112 tests with zero skips on Apple Silicon macOS.

It also checks focus association, real positive/other-phase photos, evaluation denominators, and BVH forward kinematics.

See [validation](docs/validation.md) for the tested runtime and the distinction between arithmetic and photo accuracy.

```bash
TENNISPOSE_SAMPLE_DIR=docs/demo-assets/reference-photos \
  .venv/bin/python -m unittest discover -s tests -v
```

Before competition submission, manually exercise these local paths in the browser:

- No uploaded image.
- Unsupported or unreadable input.
- A Trophy Pose photograph that lands in the configured range (green).
- A Trophy Pose photograph outside the configured range (red).
- A photograph that does not support preparation cues in both automatic and manual modes, which must refuse rather than score.
- An occluded or unreliable-landmark photograph that returns cannot-analyze without a score.

### Future Testing

As Tennis360 expands, additional tests will evaluate:

- Forehand preparation, contact, and follow-through.
- One-handed and two-handed backhand positions.
- Forehand and backhand volley positions.
- Overhead and slice positions.
- Serve phases beyond the Trophy Pose.
- Ready-position and footwork measurements.
- Full-body joint-angle calculations.
- Movement identification and classification.
- Landmark reliability across different camera angles.
- Joint-angle comparisons with independent reference measurements.
- Consistency of movement-specific feedback.

Each supported tennis movement will require appropriate validation before technique feedback is considered reliable.

## Demo Assets and Results

The repository preserves **45 licensed real photos**, human 2D annotations, two optical-motion-derived serve BVHs, and reproducible evaluation outputs for teaching.

Fixed focus raised analyzed preparation views from **0/8 to 4/8** in the new Taipei development sample; its 19 clear other-stage views all refused.

The 12,000 BVH arm readings verify angle arithmetic, not photo-model accuracy.

No coach-correctness or paired photo/3D accuracy is inferred from these results.

Existing screenshots in `streamlit-results/` are historical August 2026 evidence.

See [the asset manifest](docs/demo-assets/README.md) for source links, author credits, license terms, result summaries, and public-use conditions.

[Dataset access request drafts](docs/dataset-access-requests.md) are prepared for coach labels and paired 3D references; they have not been sent.

Future Tennis360 datasets will include photographs of forehands, backhands, volleys, overheads, slices, ready positions, and footwork.

These additional datasets will support the development and evaluation of stroke recognition, full-body measurements, and position-specific feedback.

## Repository Layout

```text
start.bat / start.command   # classroom setup and local launch
scripts/bootstrap.py        # shared setup, integrity checks, loopback server
scripts/evaluate_photos.py  # offline replay of licensed teaching photos
scripts/evaluate_mocap.py   # offline optical-data geometry comparison
streamlit_app.py             # local Streamlit entry point
requirements.txt             # pinned Python dependencies

tennis360/
  __init__.py
  pose_math.py               # pure geometry, gating rules, and feedback
  image_input.py             # content validation and safe JPEG/PNG decoding
  pose_detector.py           # MediaPipe inference, arm selection, and reporting
  annotate.py                # result drawing
  evaluation.py              # evidence-aware offline metrics
  mocap.py                   # strict BVH forward kinematics and angle oracle
  cli.py                     # desktop CLI: video analysis, history, reports
  config.py                  # coach-customizable target ranges (YAML)
  history.py                 # cross-day SQLite history and trends
  reference.py               # reference-template comparison
  reports.py                 # Excel/CSV reports, trajectory and trend plots
  strokes.py                 # 11 stroke analyses (serve/forehand/backhands/slice/overhead/volleys/drop-shot/half-volley/lob)
  video.py                   # video frame pipeline, keyframes, annotated video
  default_targets.yaml       # demonstration target ranges (not coach-validated)

tests/
  test_pose_math.py          # geometry, gating, and pooling
  test_arm_selection.py      # racket-arm detection and refusal reasons
  test_quality_guards.py     # repeat reliability, association and boundary guards
  test_analysis_pipeline.py  # entry-point guards and empty-photo behavior
  test_reference_photos.py   # output regression over authorized photos
  test_image_input.py        # upload validation
  test_player_focus.py       # fixed focus and real-photo coverage regression
  test_evaluation.py         # missing truth, denominators and arm exclusions
  test_mocap.py              # independent FK and actual optical-data checks
  reference_expectations.json

models/                      # ignored local MediaPipe model file

docs/
  demo-assets/
    reference-photos/        # licensed reference inputs used by regression suite
    streamlit-results/       # full-page local-browser evidence for ten inputs
    teaching-photos/         # six licensed phase/visibility teaching cases
    taipei/                  # 29 photos and human 2D annotations, CC BY 4.0
    mocap/                   # two optical serve BVHs, CC BY-SA 3.0
    evaluation-2026-10-11/    # saved predictions, overlays, UI tree, angle CSV
    README.md                # attribution and result manifest
```

The current repository layout reflects the existing prototype.

Future development may add separate modules for tennis movement identification, full-body joint-angle analysis, stroke-specific feedback, and video processing.

## Development Roadmap

Tennis360 will expand from a serve-position analysis prototype into a broader tennis technique analysis application.

| Phase | Development Goal | Status |
|---|---|---|
| 1 | Local image upload and pose detection | Implemented |
| 2 | Trophy Pose elbow-angle analysis | Implemented |
| 3 | Full-body joint-angle measurements | Planned |
| 4 | Forehand and backhand analysis | Planned |
| 5 | Serve movement-phase analysis | Planned |
| 6 | Volley and overhead analysis | Planned |
| 7 | Slice and specialty-shot analysis | Planned |
| 8 | Ready-position and footwork analysis | Planned |
| 9 | Tennis stroke identification | Planned |
| 10 | Movement-specific positioning feedback | Planned |
| 11 | Video-based movement analysis | Future consideration |
| 12 | Practice progress and comparison features | Future consideration |

The next development priority is expanding the existing measurement pipeline to calculate additional joint angles and support multiple tennis positions.

Each tennis movement will require its own landmark checks, geometric measurements, and evaluation criteria.

Future improvements will focus on measurement consistency, clear visual annotations, and informative technique feedback.

## Project Goals

Tennis360 aims to make tennis technique analysis more accessible through computer vision and pose estimation.

The project focuses on five primary goals:

1. **Accessibility:** Provide a practical tool for players who may not have regular access to professional coaching or specialized training equipment.

2. **Technique Understanding:** Help players understand joint positioning, body alignment, and posture across different tennis strokes.

3. **Measurable Feedback:** Use body landmarks and joint-angle calculations to provide information beyond visual observation alone.

4. **Independent Practice:** Support players who want to review their technique and identify potential areas for improvement.

5. **Comprehensive Tennis Analysis:** Expand beyond serving to include groundstrokes, volleys, overheads, ready positions, footwork, and recovery.

The long-term vision is to provide a comprehensive training tool that helps players better understand their movements throughout the game.

## Documentation

- [Project profile](docs/project-profile.md)
- [Product requirements](docs/project-overview.md)
- [Solution architecture](docs/architecture.md)
- [Research and validation](docs/validation.md)
- [MVP roadmap and test plan](docs/mvp-plan.md)
- [Competition plan](docs/competition.md)
- [Data and storage boundary](docs/data-and-storage.md)
- [Dependencies](docs/integrations.md)
- [Security and privacy](docs/security-and-privacy.md)
- [Demo asset attribution and results](docs/demo-assets/README.md)
- [Dataset access request drafts](docs/dataset-access-requests.md)
- [Repository working rules](AGENTS.md)

Some existing documentation describes the original serve-specific prototype and will require updates as additional Tennis360 capabilities are developed.

## License and Attribution

No overall source-code license has been selected.

The versioned photos, annotations, motion-capture data, and derived results retain their individual upstream Creative Commons terms documented in [the asset manifest](docs/demo-assets/README.md).

Confirm source-code ownership, dependency licenses, model terms, asset attribution, and current competition rules before public submission or release.