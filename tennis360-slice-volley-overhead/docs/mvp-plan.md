# Streamlit MVP Roadmap and Test Plan

## Definition of Done

The MVP is complete when a reviewer can run the local Streamlit application, upload an authorized Trophy Pose JPEG or PNG, see the racket arm detected and a transparent elbow-angle result for both an in-range and an adjustment example, and receive a safe cannot-analyze response for unreliable input and for unsupported preparation cues in either automatic or manual mode.

The product is a locally served web application. There is no Android, iOS, APK, device-permission, or native-runtime acceptance gate.

## Delivery Plan

| Phase | Status | Exit evidence |
|---|---|---|
| 0. Repository migration | Complete | Active tracked product paths and documents are Streamlit/Python; the prior mobile sources are removed from the delivered repository. |
| 1. Local app bootstrap | Complete | `streamlit_app.py`, `requirements.txt`, and the ignored local model started on `127.0.0.1:8501` on August 28, 2026. |
| 2. Geometry and feedback tests | Complete | `tests/` covers 2D and 3D geometry, body scale, the trophy-position gate, racket-arm selection, pooling and confidence, entry-point guards, content validation, and size limits; 49 tests passed on August 28, 2026. |
| 3. Upload, inference, and annotation | Complete | Ten authorized reference photos were replayed through the full pipeline on August 28, 2026: four trophy positions returned green, three post-trophy frames returned red, and three refused. This historical behavior is superseded by the October quality-gate record below. |
| 4. Manual local acceptance | Verified on macOS | October browser checks cover all upload/result paths, manual selection, wide/narrow intervals and borderline refusal. August screenshots remain historical. Windows/classroom-machine acceptance is separate. |
| 5. Competition evidence | Pending | Prepare authorized photos, record the two-minute local demo, and state limitations. |
| 6. Submission check | Pending | Reconcile official rules, attribution, license, repository visibility, and final materials. |

Do not claim a phase complete until its stated evidence is actually recorded. The configurable angle range still requires coach validation or replacement before any stronger claim is made.

## Test Matrix

| Case | Expected result | Required evidence |
|---|---|---|
| Right and straight point sets | Correct angles within tolerance | `python -m unittest discover -s tests -v` |
| Arm bent toward the camera | The 3D formula preserves a known synthetic angle across rotation/scale; photo depth remains estimated | `python -m unittest discover -s tests -v` |
| Zero-length point geometry | Cannot-analyze outcome; no crash | `python -m unittest discover -s tests -v` |
| Feedback boundaries | 80 and 120 are in range; values outside are adjustment suggested | `python -m unittest discover -s tests -v` |
| Left-handed server | The left arm is auto-detected as the racket arm | `python -m unittest discover -s tests -v` |
| Ready stance, contact, or follow-through | Refused in both modes, even after widening the feedback interval | `python -m unittest discover -s tests -v` |
| Hidden racket arm | Ambiguous-arm refusal, not a measurement of the tossing arm | `python -m unittest discover -s tests -v` |
| Passes that do not agree | Require >=3 validated/associated readings, full spread <=20, and no boundary crossing | `python -m unittest discover -s tests -v` |
| Ten authorized reference photos | Recorded arm, verdict, and angle within tolerance | `TENNISPOSE_SAMPLE_DIR=... python -m unittest discover -s tests -v` |
| No image | Clear instruction and one primary upload action | Manual local Streamlit check |
| Unsupported, oversized, or unreadable input | Clear recovery guidance; no score | Automated content/size tests and manual local Streamlit check |
| Clear one-person Trophy Pose | Overlay, angle, confidence, and configured result | Manual local Streamlit check with authorized image |
| Blurry, occluded, or unsuitable photo | Cannot-analyze state; no score | Manual local Streamlit check with authorized image |
| In-range and adjustment examples | Separate green and red flows | Manual local recording-ready evidence |

## Competition Demo Script

1. State the learner problem and the deliberate single-photo scope.
2. Upload a supported Trophy photo with an explicitly demonstrated narrow target and explain the red result.
3. Upload the in-range image and show the same transparent calculation path.
4. Explain that the elbow angle comes from three visible landmarks, not an unexplained score.
5. Open "How this number was measured": show five validated repeats, the
   observed min/max and the pixel-aspect-correct 2D comparison. Explain that
   monocular depth is estimated and repeat agreement is not measured accuracy.
6. Leave auto-detect selected, upload a photo that is not a trophy position, and show the app refusing with a
   reason instead of inventing a score.
7. State limits: still image, viewpoint sensitivity, local processing, an
   adjustable demonstration range, and no medical claim.

## Verification Record

Record only checks run against the Streamlit implementation. Historical Flutter, emulator, APK, iOS, and separate desktop-prototype results are not acceptance evidence for this product and must not be reported as current verification.

Required commands:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/streamlit run streamlit_app.py
```

Include the reference photos when checking accuracy, so the suite runs the
regression gate rather than skipping it:

```bash
TENNISPOSE_SAMPLE_DIR=docs/demo-assets/reference-photos \
  .venv/bin/python -m unittest discover -s tests -v
```

### Recorded accuracy run — August 28, 2026

Ten authorized reference photos, auto arm detection, 80-120 degree range:

| Photo shows | Photos | Result |
|---|---|---|
| Trophy position | 4 | Green, racket arm auto-detected, 83-111 degrees |
| Contact or follow-through | 3 | Red, elbow straighter than the range |
| Ready stance, hidden arm, or arm still low | 3 | Cannot analyze, with distinct reason codes |

The previous 2D pipeline scored the same four trophy photos at 33-89 degrees and
reported red for three of them.

The exact source-photo and full-page result pairs used for this record are
versioned in [`demo-assets/`](demo-assets/README.md), with their attribution and
licensing terms.

### Classroom launchers — September 6, 2026

- Added Windows `start.bat`, executable macOS `start.command`, and shared `scripts/bootstrap.py`; requires preinstalled 64-bit Python 3.11.
- Fresh Apple Silicon macOS setup passed in an isolated temporary folder whose path contained spaces and Chinese characters: environment creation, binary package installation, official version-1 model download, SHA-256 verification, and model loading.
- Second setup passed with no package/model download; direct dependency versions, pip compatibility, imports, model checksum and model loading were checked. This was a reuse-path check, not an OS-level network-disconnection test.
- All 55 tests passed using the freshly installed environment, including six bootstrap safety/reuse tests and full inference over all ten authorized reference photos.
- Started the actual macOS launcher and confirmed the listener was `127.0.0.1:8501`. Browser checks passed for no upload; Alcaraz green (101 degrees); Mahut red (168 degrees); Ostapenko cannot-analyze with no score; unreadable JPEG rejection; and unsupported text-file rejection. These checks used the new temporary environment, not the pre-existing project environment.
- Windows launcher received static review only. No Windows runtime, Intel Mac, Finder double-click, or classroom-machine acceptance is claimed. Test those targets before class.
- Teaching material: `docs/teaching-guide.zh-TW.md`, including a 120-minute lesson, worked exercises, startup recovery and student acceptance checks.

- Ctrl+C stopped the launcher and Streamlit cleanly. MediaPipe background Clearcut uploader failures were observed during the longer browser run; recorded in `security-and-privacy.md`. No zero-network or telemetry-payload claim is made.

### Quality guards and independent photo checks — October 11, 2026

- Replaced raised-hand-only acceptance with torso-relative dual-arm preparation
  cues, independent of the adjustable feedback interval. Manual selection must
  pass the same guards.
- Five variants each validate visibility, presence, bounds, world geometry,
  phase and inverse-transform association. Require >=3 survivors, full spread
  <=20 degrees, and no interval-category disagreement. UI reports observed
  bounds and repeat agreement rather than a calibrated confidence claim.
- Original ten-photo regression now gives three green/seven refusals. All
  former wrong-phase red examples refuse; Alcaraz's conflicting estimates refuse.
- Six new licensed stills were visually phase/arm-labelled before first inference.
  Four unsuitable/other-phase examples all refused. Of two preparation-like
  examples, Nadal's left arm was analyzed and Murray's distant/occluded arm refused.
  Murray's three images share an event/player/photographer. No true-angle or
  poor-technique ground truth is claimed.
- Geometry tests check 72 known-angle/rotation/scale combinations; mock pipeline
  tests isolate malformed landmarks, invalid repeat quality, boundary conflict,
  wrong phase, arm/person drift, and insufficient readings. These do not measure
  MediaPipe photo accuracy.
- Current commands, browser evidence and remaining validation boundaries are
  recorded in [validation.md](validation.md). Historical runs above remain dated.

### Small-player coverage and licensed teaching data — October 11, 2026

- Added fixed size-dependent focus, with shoulder association and fresh five-pass
  measurement. Coarse localization cannot decide the angle or feedback interval.
- Taipei development preparation coverage improved 0/8 to 4/8; all 19 clear
  other-stage inputs refused. Across 45 photos, preparation coverage improved
  4/15 to 8/15 and all 28 unsuitable/other-stage inputs refused. Two uncertain
  labels are excluded, not forced into correctness labels.
- Preserved 45 licensed photos, original human 2D annotations, two optical
  serve BVHs and reproducible reports under `docs/demo-assets/`. 12,000 valid
  bilateral BVH readings verify two formulas to <=1.85e-12 degrees; this is
  arithmetic evidence, not photo-estimator accuracy.
- The expanded suite passes 112 tests with zero skips on Apple Silicon macOS.
  Focus tests include real positive and other-stage photos, association loss,
  target independence and refusal provenance. Metric tests protect missing truth
  and wrong-arm exclusions. Dependencies/model checksum remain unchanged.
- The saved current UI demonstrates Taipei S_030 focused green, 104.0 degrees
  and four valid readings. Crop output is identified and does not obscure the
  player's arms with a banner. Local checks are recorded in validation.md.
- Independent coach-correctness and paired photo/3D labels remain absent.
  Access request drafts are prepared at the user's request, not sent. No stronger
  technique, medical, deployment or competition acceptance is claimed.
