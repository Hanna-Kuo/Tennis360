# Local Dependencies and Model Integration

## Local Pose Strategy

The delivered application uses Streamlit for a locally served browser interface and MediaPipe Tasks PoseLandmarker for five validated variants of one still image. The PoseLandmarker uses the CPU delegate so the MVP does not require a GPU or any cloud computer-vision service.

`tennis360.pose_detector` owns model loading, the inference passes, and racket-arm selection. It must require reliable shoulder, elbow, and wrist points before passing values to `tennis360.pose_math`, and it must read the angle from `pose_world_landmarks` rather than the normalized image landmarks. The model is cached for the process lifetime and guarded by a lock, because building a PoseLandmarker costs about half a second while a detection costs about thirty milliseconds, and the MediaPipe detector is not safe to call concurrently. The geometry, gating, and feedback rules remain pure Python and independent of Streamlit widgets or MediaPipe objects.

## Resolved Dependencies

| Category | Role |
|---|---|
| Python | Local runtime; Python 3.11 is the documented setup baseline. |
| Streamlit | Local web interface, upload control, selection, and result presentation. |
| MediaPipe Tasks | Local PoseLandmarker model invocation for one image. |
| NumPy and image-rendering dependency | Image conversion and local annotation support as pinned in `requirements.txt`. |
| Python `unittest` | Standard-library unit tests for geometry and feedback behavior. |

Exact dependency versions are pinned in `requirements.txt`; update this document when dependency roles, model format, or runtime requirements change.

## Model Handling

- The heavy PoseLandmarker task file is a local dependency at `models/pose_landmarker_heavy.task`, an ignored path.
- The classroom launchers download version 1 of the official heavy model during setup and verify SHA-256 `64437af838a65d18e5ba7a0d39b465540069bc8aae8308de3e318aad31fcbc7b`. Analysis must not download the model automatically or send uploaded images to the internet.
- Review MediaPipe and model terms before redistribution, public hosting, or packaging.
- Local landmarks are sensitive to image quality, orientation, occlusion, framing, and model limitations. The application must return cannot-analyze when required points cannot be trusted.

## Primary References

- Streamlit documentation: https://docs.streamlit.io/
- MediaPipe Pose Landmarker for Python: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python
- Pose Landmarker model catalog: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker

No LLM, remote computer-vision API, analytics SDK, identity provider, payment service, backend service, or API key is part of this MVP. Adding any of these changes privacy, cost, reliability, and competition disclosure requirements.

## Classroom Bootstrap

`start.bat` and `start.command` require preinstalled 64-bit Python 3.11 and share `scripts/bootstrap.py`. Setup creates a project-local `.venv`, installs binary wheels from the existing requirements, verifies imports and local model loading, and launches Streamlit on 127.0.0.1:8501 with usage statistics disabled. Python and OS settings are not modified. Subsequent runs skip pip installation when the requirements fingerprint matches; pip check and model integrity/loading checks still run. `--setup-only` prepares a machine before class; `--repair` reruns pip installation. Incompatible environments and model checksum mismatches are preserved and reported rather than deleted. See README for recovery and platform verification limits.

The current MediaPipe binary showed background Clearcut uploader failures during verification. See the dependency network caveat in `security-and-privacy.md`; local inference and disabled Streamlit usage statistics do not establish zero dependency telemetry.

## Research-informed quality guards

The fixed small-player crop adds one localization detection when used; all five
measurement variants still use the same cached CPU model. NumPy also supports
offline BVH forward kinematics; no dependency, model, external AI, or network
analysis service was added. Offline download/evaluation tools handle only
explicitly licensed teaching data and are never called by Streamlit uploads.

No additional model, cloud API or third-party source code was incorporated.
Torso-relative features were informed by official Google pose classification
guidance; phase cues by primary serve kinematics literature. These are local
heuristics with recorded validation, not a pretrained tennis classifier. See
[validation.md](validation.md) for sources and the monocular estimate boundary.
