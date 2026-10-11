# Repository Working Rules

## Product Context

TennisPose is a competition-stage local Streamlit web application. It accepts one JPEG or PNG tennis-serve Trophy Pose photo, lets the user choose an arm, detects the selected shoulder, elbow, and wrist with a local MediaPipe PoseLandmarker CPU model, calculates the elbow angle, and presents an annotated green, red, or cannot-analyze result.

The delivered product runs locally from `streamlit_app.py`. It has no backend, database, cloud model, account system, deployment, camera capture, or video pipeline. `tennispose/` contains reusable analysis logic; it is part of the product, not a service.

## Technology Boundary

- Use Python and Streamlit for the local web interface and result state.
- Use the local MediaPipe Tasks PoseLandmarker CPU delegate for one-image landmarks.
- Keep photo decoding, landmark validation, angle calculation, annotation, and result rendering in this repository's local process.
- Keep geometry and feedback rules in the `tennispose/` package, separate from Streamlit widget code.
- Do not add Flutter, Android/iOS targets, React Native, a backend API, cloud storage, external AI, camera capture, or video support without explicit approval.
- Do not make the local application publicly hosted or imply that a browser deployment exists without explicit approval and a separate privacy/deployment review.

## Scope Guardrails

- Analyze one still image, one Trophy Pose, and one racket arm — detected automatically, overridable by the user.
- The adjustable 80–120 degree inclusive interval is demonstration logic, not coaching, medical, or injury-prevention validation.
- Measure the elbow angle from estimated MediaPipe `pose_world_landmarks`. The pixel-aspect-correct 2D projection must never decide a verdict; monocular world coordinates are estimates, not motion-capture ground truth.
- Automatic and manual selection both require preparation cues independent of the target angle interval. Each repeat must validate landmarks, phase and association with the primary arm. Require at least three valid readings, a full spread of at most 20 degrees, and no target-boundary crossing; report repeat agreement rather than calibrated accuracy.
- Prefer refusing with a reason code over reporting a number the pipeline cannot stand behind.
- Missing, unreliable, non-finite, or degenerate shoulder/elbow/wrist landmarks mean `cannot analyze`; never generate a score from incomplete data.
- Do not add live video, continuous tracking, full-swing scoring, injury claims, accounts, sharing, payments, or social features.

## Documentation Sources of Truth

- `README.md`: product, local setup, commands, scope, and status.
- `docs/project-overview.md`: user needs, acceptance, and exclusions.
- `docs/architecture.md`: Streamlit modules, local inference, geometry, and result states.
- `docs/mvp-plan.md`: milestones, test plan, and delivery evidence.
- `docs/competition.md`: demo, assets, and submission checklist.
- `docs/integrations.md`: Python, Streamlit, and MediaPipe dependency decision record.
- `docs/data-and-storage.md` and `docs/security-and-privacy.md`: photo handling and privacy boundary.

Documentation synchronization is part of done. Update the document that owns any changed product, architecture, dependency, command, test, privacy, or competition fact in the same task.

## Local Data and Privacy Rules

- Use only team-owned or authorized photos. Do not persist uploaded photo bytes, landmarks, or results.
- Streamlit's upload object and decoded image data must exist only for the active local session. Do not write them to tracked paths, logs, test fixtures, or caches.
- Keep downloaded prototype photos and generated annotations in ignored local folders unless they are part of the explicit, licensed documentation asset set in `docs/demo-assets/`. That set must retain its attribution manifest; do not redistribute the MediaPipe model without checking its terms.
- Do not commit test photos other than the explicitly licensed `docs/demo-assets/` set, personal information, API keys, `.env` files, certificates, contracts, or confidential material.
- Keep Python versions, dependency constraints, model path, and local-run commands synchronized with `requirements.txt`, implementation, and verified test evidence.

## Verification Rules

- Treat the repository as an executable local Streamlit MVP. A unit-test pass does not establish pose-detection behavior for real photos.
- Run `python -m unittest discover -s tests -v` after changing geometry, feedback rules, invalid-landmark handling, or result-state behavior.
- Run the Streamlit application locally after changing the UI, upload handling, local inference, or annotation rendering, and report skipped checks truthfully.
- Manually test no upload, unsupported input, invalid image, reliable in-range analysis, adjustment analysis, and cannot-analyze paths with authorized local photos.

## Git Rules

Before every branch, commit, merge, push, or pull-request operation, run:

```bash
git status --short --branch
git branch --show-current
git remote -v
```

- Use Conventional Commits: `<type>(<scope>): <English summary>`.
- Stage exact paths; never use `git add .`.
- Inspect staged, unstaged, and untracked content for secrets, private images, personal data, contracts, and legal documents before committing.
- Do not commit, push, merge, open a pull request, release, deploy, or create external services without explicit user authorization.
