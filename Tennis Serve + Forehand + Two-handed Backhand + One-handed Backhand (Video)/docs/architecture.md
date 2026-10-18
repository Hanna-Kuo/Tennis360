# Solution Architecture

## Delivery Model

TennisPose is a local Streamlit web application. A browser connects to a Streamlit process on the same machine; the process decodes one uploaded image, runs local MediaPipe PoseLandmarker CPU inference over a few variants of that image, selects and validates the racket arm, pools the elbow angle, and returns an annotated result. No remote service, cloud API, database, or remote model is required.

```text
Local browser
  -> Streamlit upload, arm mode, and target range
  -> in-memory image bytes
  -> local MediaPipe PoseLandmarker (CPU, loaded once per process)
  -> fixed small-player focus, verified against original shoulders when used
  -> per-arm reliability, body scale, and trophy-position gate
  -> racket-arm selection (auto or explicit)
  -> 3D elbow angle over original + downscaled + mirrored + two rotated passes
  -> median angle, observed bounds, and repeat agreement
  -> annotated image and typed report
  -> Streamlit feedback UI
```

`streamlit_app.py` is the application entry point. ```tennis360/` contains reusable local analysis code; it does not expose an HTTP API or run as a separate service.

## Module Boundaries

| Path | Responsibility | Must not do |
|---|---|---|
| `streamlit_app.py` | Streamlit page, upload control, arm mode, target range, and presentation of results | Contain geometry rules or persist user data |
| ```tennis360/image_input.py` | Enforce JPEG/PNG content, 10 MB upload, and 20 megapixel decode limits before RGB conversion | Persist source bytes or accept another format |
| ```tennis360/pose_math.py` | Point validation, 2D and 3D angle calculation, body scale, trophy-position gate, pooling, confidence, and feedback rule | Import Streamlit, OpenCV, MediaPipe, files, or network services |
| ```tennis360/pose_detector.py` | Cache the local model, run the inference passes, select the racket arm, and build the typed report | Create a backend, persist images, draw, or make medical claims |
| ```tennis360/annotate.py` | Draw the skeleton, measured arm, angle arc, and result banner onto one BGR canvas | Decide a verdict or run inference |
| ```tennis360/evaluation.py`, `scripts/evaluate_photos.py` | Offline licensed-photo metrics, hashes and optional teaching overlays | Export private app uploads or interpret missing labels as accuracy |
| ```tennis360/mocap.py`, `scripts/evaluate_mocap.py` | Offline BVH forward kinematics and independent angle-formula checks | Treat participant tier as pose correctness or renderings as photo validation |
| `tests/` | Deterministic coverage of geometry, gating, selection, entry-point guards, and reference-photo output regression | Depend on a browser or on photos that cannot be skipped |
| `models/` | Ignored local MediaPipe model dependency | Store user images or tracked project assets |

## Geometry and Preparation Contract

The elbow interior angle uses shoulder-elbow and wrist-elbow vectors in
estimated `pose_world_landmarks`. Monocular depth may be wrong; metric units do
not establish motion-capture accuracy. The 2D comparison uses pixel coordinates
(normalized x times width, y times height) and never decides a verdict.

Positions are normalized by shoulder-to-hip midpoint distance, falling back to
shoulder width when hips are unusable. Image vectors are projected onto the
hip-to-shoulder axis to reduce camera-roll/torso-lean sensitivity; image-up is the
fallback. These are engineering heuristics, not thresholds validated by a paper.

| Gate | Condition |
|---|---|
| Complete detection | 33 image and 33 world landmarks |
| Image arm reliability | finite, inside frame, visibility >=0.35, presence >=0.5 |
| World arm reliability | finite, visibility >=0.35, presence >=0.5 |
| Segment plausibility | each world segment 0.05–0.8 m; upper/forearm ratio 0.5–2.0 |
| Racket preparation geometry | wrist rise -0.25–0.65; elbow rise -0.45–0.30; wrist above elbow by >=0.10 body scales |
| Opposite preparation cue | whole opposite arm reliable; wrist rise >=0.25 and elbow rise >=-0.10 |
| Arm ambiguity | refuse when both candidates differ by <20 degrees |
| Repeat association | inverse affine + mirror index restoration; scale ratio 0.7–1.4; shoulders within 0.25 and selected joints within 0.45 primary body scales |
| Repeat support | >=3 valid readings; full spread <=20 degrees |
| Boundary ambiguity | all accepted angles must be inside, below, or above the interval together |

Automatic mode chooses the more bent candidate when two arms pass phase cues
and are distinguishable. Manual selection overrides arm identification, but
cannot bypass visibility, preparation, association or repeat guards. The body
position gate never reads the adjustable 80–120 degree target. Association is
spatial consistency, not identity recognition or comprehensive multi-person detection.

## Pooling and Reporting

Before measurement, a complete full-image detection may propose one fixed crop
when the reliable landmark box occupies at most 10% of the image. The proposal
requires two reliable shoulders, at least eight usable points, finite coordinates,
at least 20 pixels of torso scale, and a crop of at least 64 pixels per dimension.
It adds 30% horizontal and 15% vertical margins, clipped to the frame. A fresh
crop detection must restore both shoulders within 0.25 original torso scales;
otherwise return `focus_lost`, with no coarse-angle fallback. The decision reads
neither the target interval nor the candidate elbow angle.

A successful crop becomes the measurement image. One extra localization pass
is excluded from the five readings; the original full-image world estimate is
also excluded. `focused_on_player` accompanies both analyzed and refused crop
reports. The UI identifies the crop, limits its display width, and shows the
verdict outside it so a banner cannot cover the small player's arms. Cropping
does not establish absolute angle accuracy and is not saved by the app.

Original, 75% downscaled, horizontally mirrored, and -8/+8 degree rotated images
are inferred locally. Every repeat reruns the visibility, presence, geometry and
phase checks, then verifies association with the primary arm. The median uses
only accepted repeats; all their readings contribute to the full spread and
boundary check, so no otherwise valid outlier is discarded.

The internal `confidence` field represents repeat agreement only: high for
spread <=8 degrees with all five passes valid; moderate for spread <=20 degrees
or only three/four valid passes; otherwise refusal. One/two passes cannot produce
a verdict, even with zero spread. Observed bounds are not a statistical confidence
interval or a bound on absolute angle error.

## Result States

| State | Trigger | Browser behavior |
|---|---|---|
| Idle | No image uploaded | Explain the one-photo requirement and local-processing boundary. |
| Image ready | A readable JPEG or PNG is uploaded | Keep the current arm selector visible; after inference, show only the annotated result rather than a duplicate original-photo preview. |
| Analyzing | The current upload or any setting changes | Run the local inference passes and show Streamlit's progress indicator. |
| Analyzed | An arm was selected, gated, and pooled successfully | Show annotated image, angle, configured range, repeat agreement, green/red feedback, and the measurement detail panel. |
| Cannot analyze | Any reason code below | Explain the issue and allow another image without a score. |

### Cannot-analyze reason codes

| Code | Meaning |
|---|---|
| `no_pose` | No person was detected in the photo. |
| `focus_lost` | The fixed crop lost or changed the detected player; no coarse-angle fallback. |
| `no_scale` | The player is too small or too cropped to normalize positions against. |
| `no_reliable_arm` | Neither arm was visible enough to measure. |
| `arm_not_visible` | The explicitly selected arm was not visible enough to measure. |
| `not_trophy_pose` | Dual-arm geometry does not support the preparation checkpoint. |
| `ambiguous_arm` | Opposite arm hidden, invalid arm geometry, or candidates cannot be distinguished. |
| `invalid_geometry` | Zero-length or non-finite shoulder-elbow-wrist geometry. |
| `invalid_landmarks` | Detector returned incomplete landmark arrays. |
| `unstable` | Fewer than three valid readings or their full spread exceeds 20 degrees. |
| `borderline` | Accepted estimates cross a selected target boundary. |

## Local Processing Boundary

- Image bytes, landmarks, angle, and feedback stay in memory for the active local Streamlit session. JPEG/PNG content is rechecked after upload; the app rejects files above 10 MB or 20 megapixels before RGB conversion.
- The MediaPipe model is downloaded once to an ignored `models/` path. Model loading and inference are local. Application code does not upload photos; the dependency network caveat in `security-and-privacy.md` records MediaPipe background telemetry messages.
- The application does not intentionally write uploaded photos, landmark coordinates, or results to disk, logs, databases, or history.
- Public deployment, result storage, sharing, telemetry, camera input, or video support are separate architecture and privacy changes requiring explicit approval.

## Setup and Launch Boundary

The OS-specific launchers call `scripts/bootstrap.py` before starting the product. It owns local environment creation, dependency installation, a versioned official model download with SHA-256 verification and atomic promotion, and startup checks. An exclusive temporary lock prevents simultaneous setup writes. It handles no uploaded photo or landmark data. The launch command binds Streamlit to `127.0.0.1:8501` and disables usage statistics; it does not publish a service. Package fingerprints reside inside ignored `.venv/`, models inside ignored `models/`, and the ignored setup lock is removed on ordinary completion or error.
