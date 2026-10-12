# Project Profile

| Field | Value |
|---|---|
| Project | TennisPose - AI Tennis Trophy Pose Coach |
| Repository | `TennisPose` |
| Project slug | `tennis360` |
| Stage | Competition MVP |
| Product type | Local Streamlit web application |
| Delivery | Browser UI served by a local Python process |
| Framework | Streamlit and Python |
| Pose inference | Local MediaPipe PoseLandmarker CPU delegate |
| Deployment | Not planned |

## Product Statement

TennisPose lets a learner inspect one Trophy Pose photo in a local browser. The application finds local pose landmarks, measures the chosen arm's elbow angle, and makes green, red, or cannot-analyze feedback visible and explainable.

## Technology Decision

Streamlit is the delivered product because the competition MVP needs a fast, transparent local interface for one-image upload, angle annotation, and recorded demonstration. It avoids native mobile packaging and does not require a backend or cloud service.

The application uses Python 3.11, Streamlit, and a local MediaPipe Tasks PoseLandmarker model with the CPU delegate. `tennis360.pose_math` owns the pure three-point geometry, the trophy-position gate, and the feedback rule; `tennis360.pose_detector` owns landmark extraction, racket-arm selection, and reporting; `tennis360.annotate` owns drawing.

## Constraints

- One JPEG or PNG still image, one Trophy Pose, and one racket arm — detected automatically, overridable by the user.
- No video, backend, account, database, cloud storage, remote AI, camera, or public deployment.
- Local in-memory processing only; no history or saved results.
- No medical, injury-prevention, rehabilitation, or professional coaching claim.
- The 80–120 degree interval is an adjustable demonstration range, not a validated performance target. Historical elite-reference model outputs motivated widening the original 90–105 range; these outputs do not establish real angles or a calibrated ±10 degree error bound.

## Current Verification Boundary

- The executable baseline is a local Python/Streamlit application, not a Flutter or native-mobile project.
- Unit tests must cover geometry, invalid landmarks, and inclusive feedback behavior.
- Manual browser checks with authorized images remain necessary for upload handling, annotation alignment, green/red flows, and cannot-analyze behavior.
- No public deployment, external integration, or competition acceptance has been verified solely by this repository.

## Open Decisions

- Coach validation or replacement of the adjustable 80–120 degree demonstration range.
- Authorized in-range, adjustment, and unsuitable photo set for recording.
- Current competition requirements, asset policy, attribution, repository visibility, and project license.
