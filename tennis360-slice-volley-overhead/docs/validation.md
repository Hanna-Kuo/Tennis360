# Research and Validation — October 11, 2026

The current local MVP screens for preparation-like dual-arm geometry, then
compares a supported elbow estimate against the user's target interval. It now
refuses wrong-phase examples, invalid repeats, insufficient support and boundary
conflicts. This validates those safeguards; it does not establish universal
serve correctness or absolute monocular angle accuracy.

## Evidence Behind the Design

- [Jacquier-Bret and Gorce, Sensors 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11175047/)
  measured four players with ten cameras. Trophy position, racket low point and
  ball impact are distinct sequence events. A single still can only support
  preparation-like appearance; it cannot establish a temporal maximum. Their
  segment-rotation/flexion conventions are not this application's three-point
  interior angle, so published values cannot directly become its angle labels.
- [Google's official pose classification guide](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/pose_classification.md)
  and [pose embedding source](https://github.com/googlesamples/mlkit/blob/master/android/vision-quickstart/app/src/main/java/com/google/mlkit/vision/demo/java/posedetector/classification/PoseEmbedding.java)
  informed torso normalization and relative-joint features. The examples are
  not validated tennis classifiers. A small collection of stills does not
  justify training and claiming a general classifier. No source code was copied
  and no ML Kit/Android dependency was added.
- [BlazePose GHUM's primary paper](https://arxiv.org/abs/2206.11678) describes
  monocular 3D estimation. Hip-relative metric coordinates and repeated image
  transforms do not provide measured 3D ground truth.

The numerical position, limb-plausibility, association and repeat thresholds
are conservative engineering heuristics documented in
[architecture.md](architecture.md). They are not thresholds supplied or validated
by these publications. The 80–120 target remains a configurable demonstration.

## Changes and Regression Evidence

| Prior failure | Current safeguard and evidence |
|---|---|
| A raised contact/follow-through arm could be graded, even green after widening the target | Torso-relative racket-arm geometry plus elevated opposite-hand cues; target-independent; automatic and manual modes both gate. Twelve real-photo checks across four unsuitable images and three arm modes refuse at 40–180. |
| Low-visibility repeats could overwrite a reliable primary angle | Every repeat checks image/world visibility, presence, bounds, finite coordinates, segment geometry and preparation. Mock regression preserves refusal instead of inventing a green result. |
| One surviving pass or a conflicting majority could be called high confidence | At least three valid readings; full spread <=20 degrees; no interval-category crossing. All accepted readings count, including reliable outliers. |
| Repeat detection could change person or arm | Inverse affine/mirror restoration and spatial association with the primary arm. Person-shift, arm-drift and actual affine round-trip tests pass. This is not identity recognition. |
| NaN/short landmarks crashed annotation/indexing | Complete-array check before indexing and reliable-point checks before drawing; regression returns no score. |
| 2D comparison ignored rectangular image aspect | Compute it in pixels; keep it out of verdict decisions. |
| Displayed symmetric uncertainty and implied accuracy | Show actual observed min/max, valid/attempted passes and repeat agreement; no accuracy probability or calibrated confidence interval. |

Numeric reference expectations are model-output snapshots. The default unittest
command now uses the repository's licensed photos, avoiding an accidental skip
caused by an unrelated personal Desktop path.

## Real-Photo Results

The original ten licensed images were previously used for development. They are
regression inputs, not heldout accuracy data. Current default results:

| Input | Result |
|---|---|
| McEnroe | Left, 99.2 degrees; 95.2–103.1 observed; high repeat agreement; fixed focus |
| Federer | Right, 85.3 degrees; 81.4–90.7; moderate agreement |
| Djokovic | Right, 111.1 degrees; 98.3–112.3; moderate agreement; fixed focus |
| Alcaraz | Genuine preparation view, but conflicting inferred angles; `unstable`, no score |
| Pagon, Ergeneman, Mahut, Sharapova | Unsupported preparation cues; no score |
| Ostapenko, Haas | Unreliable/ambiguous arm; no score |

Six additional licensed images were collected and visually labelled for phase
and racket arm **before their first inference**. Thresholds were not tuned on
them. Labels are visual inspection, not coach or motion-capture ground truth:

| Heldout input and credit | Pre-inference label | Result |
|---|---|---|
| [Murray part 1](https://commons.wikimedia.org/wiki/File:Andy_Murray_Serve_Part_1.jpg), Nick Hewson, CC BY 2.0 | Preparation-like, right | Ambiguous arm; refused |
| [Murray part 2](https://commons.wikimedia.org/wiki/File:Andy_Murray_serve_part_2.jpg), Nick Hewson, CC BY 2.0 | Near/after contact | Not preparation; refused |
| [Murray part 3](https://commons.wikimedia.org/wiki/File:Andy_Murray_serve_part_3.jpg), Nick Hewson, CC BY 2.0 | Follow-through | Ambiguous arm; refused |
| [Nadal Serving](https://commons.wikimedia.org/wiki/File:Nadal_Serving.jpg), Donna and Keith, CC BY 2.0 | Preparation-like, left | Left, 102.0 degrees; 100.9–102.7; high agreement |
| [Nadal lefty serve](https://commons.wikimedia.org/wiki/File:Nadal_lefty_serve_(4944616391).jpg), JC, CC BY-SA 2.0 | Foreground receiver/multiple distant players; unsuitable | No reliable arm; refused |
| [Stephens serve](https://commons.wikimedia.org/wiki/File:Sloane_Stephens_serves_at_the_US_Open_(9662688451)_(cropped).jpg), Boss Tweed, CC BY 2.0 | Late cocking/acceleration, not clear TP | Not preparation; refused |

All four unsuitable/other-phase heldout examples refused. One of two preparation
examples was usable; the distant Murray example refused. This is an explicit
coverage cost, not a perfect accuracy claim. Murray's three images share a
player/event/photographer. Six images are too few to estimate population accuracy.
Nadal/Stephens use the uncropped licensed Flickr upstream images; the local
manifest records the actual URLs, sizes, hashes and terms. Additional photos
and annotations were initially stored in ignored local archives; the six reviewed
photos are now preserved in [teaching-photos/](demo-assets/teaching-photos/README.md)
with exact source, license, upstream/local hashes and modification notices.

## Positive Coverage Optimization and Saved Data

A fixed small-player crop improves the model input before the same five
measurement variants. It reads coarse image landmarks and player size, never
the target/angle/green result. Shoulder association must survive; localization
estimates never enter the angle pool. Failure has no coarse-angle fallback.
The full rule is in [architecture.md](architecture.md#pooling-and-reporting).

The new [Taipei photos](demo-assets/taipei/README.md) provide 29 actual JPEGs and
original human 2D joints. Before first inference, full-frame and annotated-ROI
inspection labelled eight clear preparation views, 19 other-stage views and two
uncertain views. Coach verdicts and measured 3D angles remain null.

| Development-sample measure | Without focus | Fixed focus |
|---|---:|---:|
| Taipei preparation views analyzed | 0/8 | 4/8 |
| All visually labelled preparation views analyzed | 4/15 | 8/15 |
| Clear other-stage/unsuitable views incorrectly analyzed | 0/28 | 0/28 |

Focused Taipei positives are S_030 (104.0°), S_120 (112.7°), S_200 (109.7°) and
S_300 (110.8°), each with four valid readings, <=8.9° spread, the visually
labelled racket arm and no interval crossing. These are estimates, not true-angle
labels. The two uncertain Taipei frames are excluded from phase fractions.
The original ten-photo regression remains three green/seven refusals; Nadal
remains analyzed. No refusal was re-labelled as incorrect technique.

Taipei frames share one evaluation group because verified player/session IDs
are unavailable. They were used for focus development, not unseen acceptance.
Unconditional cropping harmed an existing positive, and square/resize treatment
did not improve coverage. Only the size-dependent crop with unchanged repeat
guards was adopted. Zero wrong-phase acceptances here is not a population bound.

[Two Tennis-MoCap BVHs](demo-assets/mocap/README.md) provide optical
capture-derived joints. Forward kinematics honors channel order and
parent-transformed offsets, tested with independent noncommuting rotations and
hierarchies. Two 3,000-frame/100 Hz sequences yield **12,000 valid bilateral
readings, zero exclusions**. Maximum difference between the application's acos
formula and independent atan2/cross-product geometry is
**1.8474111129762605e-12°**. This checks arithmetic, not MediaPipe photo error.
HP/RP is participant tier, not correctness; paired RGB and Trophy timestamps
are absent.

The [teaching catalog](demo-assets/README.md) retains all 45 photos, predictions,
source/model/input hashes, four positive overlays, a current UI tree record,
BVHs and angle tables. Offline metrics keep missing truth null, exclude
wrong/unknown arm matches from angle/coach agreement, and count exclusions.
Coverage, numerical agreement and participant tier cannot become accuracy labels.

## Verification and Reproduction

```bash
.venv/bin/python -m unittest discover -s tests -v
bash start.command
```

The first quality-guard milestone passed 80 tests. The expanded suite passed
**112 tests, zero skips** on Apple Silicon macOS/Python
3.11.14 with the pinned dependencies and official version-1 heavy model.
Geometry tests include 72 analytically known angle/rotation/scale combinations;
these validate the formula, not MediaPipe's image accuracy. The model checksum
and startup procedure are unchanged from the verified launcher.

Local browser checks cover no upload, unreadable JPEG, unsupported text, green
Nadal, a deliberately configured red interval, wrong-phase refusal at 40–180
including manual selection, conflicting estimates and target-boundary refusal.
The red interval demo does not supply a poor-technique ground-truth photo.
The application remains available only at `http://127.0.0.1:8501` while running.

Final focused-UI checks replayed S_030 auto green at 80–120 and manual-right red
at 110–120, with the same 104.0°/4-of-5 evidence; S_080 refused while identifying
the displayed crop; S_020 refused in auto and manual-right modes, including
40–180; unreadable JPEG and unsupported text were rejected without a score.
The current UI tree and visually inspected positive overlays are saved. Final
full-page screenshot export timed out; no new full-page visual capture is claimed.

Local evidence: `archive/optimization-2026-10-11/unittest.log`,
`photo-results-final.json`, `wide-band-guards.json`, `heldout/blind-labels.json`,
`heldout/manifest.json`, and `output/playwright/`. Historical August screenshots
remain attributed in `demo-assets/`; they are not current result screenshots.

Replay the saved teaching inputs with:

```bash
.venv/bin/python scripts/evaluate_photos.py --without-focus --output archive/class-baseline
.venv/bin/python scripts/evaluate_photos.py --output archive/class-focused --save-overlays
.venv/bin/python scripts/evaluate_mocap.py --report-dir archive/class-mocap
```

The photo command replays only licensed manifest-listed repository assets. The
MoCap command verifies its manifest and requires a new report directory. Both
are separate from the in-memory application upload path. Current results are
saved in [evaluation-2026-10-11/](demo-assets/evaluation-2026-10-11/README.md).

## Remaining Accuracy Acceptance

Candidate datasets were also inspected, rather than assuming an open repository
provides independently measured angle labels:

| Source | Current suitability |
|---|---|
| [Tennis-MoCap](https://github.com/jdpulgarin/Tennis-MoCap) | CC BY-SA 3.0 optical-motion-derived BVH; two serves saved. Numerical geometry validation is possible, but no paired RGB/correctness labels. |
| [Taipei / Mendeley](https://data.mendeley.com/datasets/nv3rpsxhhk/1), [primary paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11282921/) | CC BY 4.0 actual photos and human 2D joints; 29 photos and the original 500-frame serve annotation file saved. These are not measured 3D or coach labels. |
| [TAGS / Tennis Action-GE, ICCVW 2025](https://openaccess.thecvf.com/content/ICCV2025W/AMFG/html/Wang_Generating_Tennis_Action_Instruction_Based_on_a_Large_Language_Model_ICCVW_2025_paper.html) | 3,000 video/query/evaluation triplets: initial LLM drafts refined by 20 experienced coaches, checked by 10 senior coaches. STCFormer 3D is estimated. No licensed downloadable release located; request serve/Trophy labels and their scope. |
| [SportsPose](https://christianingwersen.github.io/SportsPose/download.html) | Multi-view sports benchmark; academic identity/email and intended use required. Academic-only, nontransferable terms do not authorize raw classroom redistribution. Request paired references and separate teaching permission. |
| [University of Bath serve motion capture](https://researchdata.bath.ac.uk/1454/) | CC BY 4.0 marker trajectories are available. The released file list does not include paired RGB frames for running this photo model against the measurements. |
| [UVA tennis serve dataset](https://github.com/jasnwag/tennis_serve_dataset) | Its documented RTMPose/MotionBERT pipeline estimates 3D from broadcast video; these are model-derived labels, not measured 3D ground truth. |
| [THETIS](https://github.com/THETIS-dataset/dataset) | Kinect action sequences include beginner/expert players, but the inspected README lists rendered skeleton videos and supplies no dataset reuse license or numerical joint table. Further data/terms review is needed before local photo evaluation. |
| [VAL tennis dataset](https://val.cs.tut.ac.jp/project/tennis/) | VICON trajectories, including coach participants; noncommercial permission/attribution terms need scope review. Coach participation does not label every pose as correct. |
| [CalTennis](https://ilonadem.github.io/caltennis-website/) | CC BY-NC 4.0 benchmark; multiview consistency is not directly measured elbow-angle gold, and noncommercial terms need teaching-scope review. No large download was made. |

The photo sets contain no independently measured 3D elbow angles and no
coach-labelled incorrect Trophy technique. Before a stronger correct/incorrect
claim, obtain authorized, independent coach labels and synchronized calibrated
3D reference measurements across players, views, lighting and occlusion. Freeze
development and heldout splits by player/session; report angle error, accepted
coverage, wrong-phase false acceptance, interval errors and refusals separately.
The acceptable errors/coverage must be set with the intended evaluator before
testing. More heuristics or the same model's repeated outputs cannot supply that
missing ground truth. No full-serve, injury, deployment or competition acceptance
claim is made by this local verification.

At the user's request, [research-data access drafts](dataset-access-requests.md)
are prepared for TAGS and SportsPose. They ask for correct/incorrect Trophy
rubrics, coach agreement, frame/player/session IDs, paired calibrated references
and classroom/storage/redistribution rights. **They have not been sent.** No
academic affiliation, account, budget or grant is assumed.
