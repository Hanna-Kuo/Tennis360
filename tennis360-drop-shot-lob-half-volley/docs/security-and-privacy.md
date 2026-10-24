# Security and Privacy Boundary

## Risk Context

The local Streamlit MVP has no login, payment, database, cloud API, or remote storage. Its main risk is an uploaded photo that may contain an identifiable person.

## Required Protections

- The page explains local processing before upload; competition operators must use only photos they own or are authorized to use.
- Run the application locally. Do not expose it through a public URL, tunnel, or shared server without a separate security and privacy review.
- Keep uploaded image bytes, decoded image data, landmarks, and results in the active local session only.
- Recheck JPEG/PNG content after upload and reject files above 10 MB or 20 megapixels before full image conversion.
- Do not transmit photos, landmarks, or results, and do not create analysis history, logs, or saved result files.
- Do not commit private test photos, screenshots containing private data, private evaluator notes, downloaded model binaries, device identifiers, or secrets. The approved exception is the explicitly licensed public teaching set in [`docs/demo-assets/`](demo-assets/README.md), including its photos, annotations, optical-motion-derived data and results. Retain attribution and do not add user uploads to it.
- Small-player focus uses an in-memory crop. Offline teaching evaluation is a separate, explicit command restricted to licensed manifest inputs; application uploads never invoke a file writer.
- Do not create an API key or `.env` requirement for the MVP.

## Responsible Product Language

- Use "demonstration range", "in range", "adjustment suggested", and "cannot analyze" rather than medical or safety claims.
- Explain that image quality, viewpoint, occlusion, clothing, orientation, framing, and landmark confidence can affect the result.
- Keep feedback wording aligned with the actual angle rule and evidence source.

## Scope-Change Trigger

Public deployment, cloud upload, result history, sharing, sign-in, telemetry, camera input, or video processing moves the project into a higher-risk state. Before such work, define consent, access control, retention, deletion, incident response, and deployment ownership.

## Classroom Launchers

First-time setup downloads packages and the official versioned model over HTTPS; it does not send photos. The model must match the pinned SHA-256 before use. The launchers preserve existing incompatible environments and unrecognized models, make no system-level changes, and start the interface on loopback only with Streamlit usage statistics disabled. Existing photo handling rules are unchanged. See README for interrupted-setup recovery; never disable certificate verification to work around a download error.

## Dependency Network Caveat

On September 6, 2026, the existing MediaPipe 0.10.35 binary emitted `portable_clearcut_uploader.cc` / `Failed to send to clearcut` messages during the browser verification run. This is evidence of a dependency background telemetry component; it is not evidence that uploaded photos were sent, nor a packet capture confirming its payload or successful transmission. Streamlit usage statistics are disabled by the launcher, but that switch does not disable MediaPipe internals. The same issue is recorded upstream at https://github.com/google-ai-edge/mediapipe/issues/6291. Do not describe this package combination as proven to make zero network attempts. Use the licensed reference set for class; stricter offline/privacy acceptance requires a separate dependency/network audit. No dependency version was changed in this launcher task.
