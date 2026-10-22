# Data and Storage Boundary

## MVP Data Contract

| Data | Source | Processing | Persistence |
|---|---|---|---|
| Selected photo | Authorized JPEG or PNG uploaded to the local Streamlit session | Content validation, then in-memory decode, local pose detection, and overlay rendering | None by the application |
| Pose landmarks | Local MediaPipe result for the current image | In-memory validation and angle calculation | None |
| Angle and feedback | Pure Python demonstration rule | Visible in the current browser session | None |
| Versioned demo assets | 45 Creative Commons photos, human 2D annotations, two licensed optical-motion-derived BVHs and attributed results | Offline regression, geometry validation and teaching | Tracked only in `docs/demo-assets/` with attribution, hashes and license notices |
| PoseLandmarker model | Official model download | Local CPU inference | Ignored local dependency; not user data |

## Rules

- The MVP has no database, account, analytics pipeline, upload bucket, app-managed cache, result history, or public deployment.
- The app must not deliberately write uploaded photos, landmark coordinates, annotated images, or results to disk, logs, test fixtures, screenshots, temporary folders, or Git.
- Browser and Streamlit session memory may hold the current uploaded bytes and result only as needed to display the current analysis. Closing or refreshing the session is not a persistence feature.
- The application rejects non-JPEG/PNG content, files above 10 MB, and images above 20 megapixels before RGB conversion. Those limits reduce accidental or hostile resource exhaustion; they do not create a storage record.
- `uploads/`, `data/private/`, and `models/` remain ignored defensively. They are not approved storage locations for user data.
- The approved tracked asset exception is `docs/demo-assets/`. At the user's explicit request, it includes the original ten photos, six additional licensed photos, 29 Taipei photos and original human 2D annotations, two Tennis-MoCap sequences, and attributed teaching outputs. These are public documentation assets, not runtime storage. Preserve each source, author credit, hash, modification notice and license.
- `scripts/evaluate_photos.py` accepts only manifest-listed licensed assets inside that directory; `scripts/evaluate_mocap.py` checks the curated data manifest. Their explicit offline output folders are separate from Streamlit. Neither writer is called by the upload path. Focus crops in the app remain in session memory.
- `.gitattributes` preserves original BVH/annotation bytes for checksum verification across checkouts. Derived motion-angle tables use LF line endings; the upstream BVHs are unchanged, including their original whitespace.
- Do not move any other test photos, user uploads, annotated examples, or model binaries into tracked paths.
- A feature that saves, shares, uploads, synchronizes, or publicly serves a photo requires new consent, retention, deletion, access-control, and backup design.

## Asset Review

The versioned asset set is catalogued in [demo-assets/README.md](demo-assets/README.md).
Before using any additional demo image, record ownership, subject consent,
competition permission, and whether public repository or video use is allowed.
