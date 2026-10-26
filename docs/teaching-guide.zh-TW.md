# TennisPose Teacher's Lesson Plan for Tomorrow's Class (120 Minutes)

This lesson plan is for a teacher guiding students through an AI/Python mini-project for the first time. The goal is not to train students into pose-recognition engineers, but to let them explain clearly: how one authorized serve Trophy Pose photo obtains a checkable result **locally**, and why the system should sometimes refuse to answer.

TennisPose only checks the shoulder–elbow–wrist angle of the racket arm. Green, red, and the 80–120 degree range are adjustable demonstration rules, not coaching, medical, injury-prevention, or complete serve evaluations. The class uses the 45 authorized, attribution-carrying photos in `docs/demo-assets/`; two optical motion-capture datasets are also available for extension exercises. Do not put student or private photos into Git, teaching materials, or public services.

## Before-Class Preparation (Complete the Installation in Advance — Do Not Leave Only 10 Minutes)

Please complete the following on every demonstration computer before class; classroom computers can be shared by two to three students each.

1. Confirm that **64-bit Python 3.11** is installed. The launcher does not install Python by itself; if it is missing, have the school handle it through the normal software installation process first.
2. When the project root already has `start.command` (macOS) and `start.bat` (Windows), start the matching file by double-clicking. They share `scripts/bootstrap.py`, which creates `.venv`, installs `requirements.txt`, downloads and checks the official MediaPipe model, and then starts Streamlit bound only to `127.0.0.1`.
3. The first launch must be able to reach the network, because it needs to download Python packages and the official model; afterwards, photo analysis needs no API key, and the application code has no photo upload service. This is not a published or public website; the browser only connects to the local machine.
4. Confirm the browser opens the local page and shows the upload prompt before any photo is selected. Have the photos in `docs/demo-assets/reference-photos/` and the licensing information in `docs/demo-assets/README.md` ready.

Do not describe Windows as "tested on all computers": this plan only documents the `start.bat` launch flow. Before class, run it once on the actual classroom Windows computer and note the result.

## The 120-Minute Flow (The Teacher Can Read It Aloud As-Is)

| Time | Guidance and ready-to-say lines | Student output |
|---|---|---|
| 0–10 min | "Today we are not judging whose serve is good; we are looking at how a computer makes a limited, explainable judgment about one photo." Show the page with no photo uploaded; point out that it accepts only JPEG/PNG, one photo at a time. | Can state that the input is one authorized photo, and the output has three kinds: green, red, and cannot analyze. |
| 10–25 min | Demonstrate with one green example and one red example. Let students guess the difference first, then open *How this number was measured*. | Can point out the racket arm, angle, range, and repeat-agreement level. |
| 25–40 min | Explain the model and data boundaries in plain language (next section), then upload a cannot-analyze photo and stress that refusing is more reliable than inventing a score. | Can explain that "cannot analyze" is neither a zero score nor a malfunction. |
| 40–55 min | Draw shoulder S, elbow E, wrist W; let students understand the angle through the metaphor of two arm vectors meeting at the elbow. | Can state that the angle is the angle between `S−E` and `W−E`. |
| 55–70 min | Introduce 2D vs 3D, and let students compare the 2D reference value in the interface with the verdict value. | Can state that green/red looks only at the 3D world landmarks, not the flat 2D value. |
| 70–90 min | Guide group reading of the code following the "Suggested Reading Order". The teacher projects only the key functions and does not need to explain Python line by line. | Each group completes one low-risk mini exercise. |
| 90–105 min | Groups classify the ten authorized examples and compare them with the result screenshots and the manifest. | Complete the green/red/cannot grouping and state the limitations. |
| 105–115 min | Student acceptance: each group demonstrates one success case and one refusal case. | Explain results with evidence, not just by reporting the color. |
| 115–120 min | Closing: "The model is a measurement tool, not a referee; saying 'I don't know' when it doesn't know is part of the design." | Hand in a short spoken or written reflection. |

## Five Plain-Language Concepts

**Model (MediaPipe PoseLandmarker)**: Think of it as a local tool that "first finds the approximate positions of body joints in a photo". It is not a coach that understands tennis technique, and it cannot guarantee it finds the right points in every image; clothing, occlusion, lighting, angle, and a too-small person all affect it.

**Python**: The programming language used in this project. Think of it as writing rules as repeatable steps: read the image, check it, ask the model to find points, compute the angle, display the result.

**`.venv`**: The project's own little toolbox. Packages are installed here so they do not interfere with other Python projects on the computer; it is a local, temporary environment and should not go into Git.

**Streamlit**: The tool that turns the Python program into the local web interface in front of you. The browser is only the control panel; the computation still happens in the Python program on the same computer.

**3D estimation and rule-based refusal**: A flat photo only shows left/right and up/down; if an arm reaches toward the camera, the flat angle gets compressed. The program judges using the model's estimated 3D `pose_world_landmarks`, and the 2D value is only a reference. Even the 3D estimate can be unreliable, so when the joints are not clearly visible, the pose screen is not passed, the racket arm is unclear, or fewer than three of the five repeat readings are valid, the readings cross the verdict boundary, or they disagree too much, the program shows cannot analyze instead of fabricating an angle.

## Suggested Reading Order (One Question per File)

1. `README.md`: What the product does and does not do, and the local-operation boundary.
2. `streamlit_app.py`: Where students see the upload, arm selection, and green/red or cannot analyze.
3. ```tennis360/image_input.py`: Why only JPEG/PNG is accepted, the 10 MB and 20 megapixel limits, and why uploaded images are never written to disk.
4. ```tennis360/pose_math.py`: See the vector angle from `calculate_elbow_angle_3d`; see the median of at least three valid readings out of five repeats, the full spread, and the agreement level from `pool_angles`; see the demonstration range from `DEFAULT_TROPHY_MINIMUM/MAXIMUM`.
5. ```tennis360/pose_detector.py`: How model loading, automatic arm selection, and `cannot_analyze` reason codes connect. Only read around `_select_arm`, `_collect_angles`, and `_cannot_analyze`.
6. `docs/architecture.md`: Put the earlier files back into the complete data flow, especially Result States and reason codes.
7. `tests/test_pose_math.py`, `tests/test_arm_selection.py`: How the program uses fixed inputs to confirm rules like "exactly 80/120 degrees on the boundary" and "refuse when it is not a Trophy Pose".
8. `docs/demo-assets/README.md`: The sources, authors, licenses, and results of the 45 photos and two motion-capture datasets; required reading when showing the assets.

## Safe, Low-Risk Mini Exercises (with Answers)

The first three learning modes are reading files, operating the local interface, and mental arithmetic; an additional simple code-modification exercise is included. Do not add student photos or upload anything to any external website.

### Exercise 1: Find the Evidence for "Not Guessing" (8 Minutes)

Question: In `docs/architecture.md`, find any two cannot-analyze reason codes and explain in your own words why there should be no score at that point.

Reference answer: `ambiguous_arm` means one hand is occluded, so the program cannot know which hand holds the racket; `unstable` means fewer than three valid readings or a full spread over 20°, which cannot support a verdict. `no_pose`, `no_reliable_arm`, `not_trophy_pose`, or `invalid_geometry` are also acceptable. The shared principle is "when the data is insufficient, output a reason, not a fake number".

### Exercise 2: Hand-Compute an Easy Angle (8 Minutes)

Suppose, with the elbow E as origin, the shoulder direction is `S−E = (0, 1, 0)` and the wrist direction is `W−E = (1, 0, 0)`. What is the angle? Which function in the program does this?

Reference answer: 90 degrees, because the two vectors are perpendicular and their dot product is 0. The corresponding function is `calculate_elbow_angle_3d` in ```tennis360/pose_math.py`, which passes the final computation to `_angle_between`. Real photos are not this tidy, so the result is only an estimate and must also pass the visibility and stability checks.

### Exercise 3: Change the Demonstration Range and Watch the Color (8 Minutes)

Pick one successfully analyzed example. First set the sidebar range to 80–120, then change it to 110–120 (for example using the roughly 99-degree McEnroe photo or the roughly 104-degree Taipei S_030), and observe whether the color changes. Do not interpret the result as good or bad technique.

Reference answer: The range is an "endpoints inclusive" demonstration rule: when the measured angle equals the minimum or maximum it is green, and outside it is red. The on-screen angle is rounded, so the displayed integer cannot verify an exact endpoint match; the exact 80/120 boundaries are tested by `tests/test_pose_math.py`. This operation only changes the current setting; it does not change the photo.

### Exercise 4: 2D Cannot Replace 3D (8 Minutes)

Open the details of any analyzed result. If the 2D reference angle differs from the displayed elbow angle, which one decides green/red? Why?

Reference answer: The angle from the 3D `pose_world_landmarks` decides green/red; when the arm points toward or away from the camera, the flat projection shortens the depth direction and 2D can clearly underestimate the real angle. That does not mean the 3D estimate has reached professional biomechanics accuracy — only that it fits this project's design better than judging from a flat projection.

## Ten Authorized Examples: Classroom Screening and Limits

The following are the recorded local results currently in the repository, for the teacher to hand out to groups. The photos, screenshots, and complete author/license information are all in `docs/demo-assets/README.md`; when showing them externally, the manifest's sources, attribution, and Creative Commons terms must be retained.

| Result | File | Recorded reason or angle |
|---|---|---|
| Cannot analyze | 01 Dominic Pagon | Ready stance, not a Trophy Pose, no score given. |
| Green | 02 John McEnroe | Left arm, 99.2°, fixed focus crop. |
| Cannot analyze | 03 Jelena Ostapenko | Racket arm occluded, arm unclear. |
| Cannot analyze | 04 Carlos Alcaraz | 3D repeat readings conflict, verdict refused. |
| Cannot analyze | 05 Gökberk Ergeneman | Follow-through phase, verdict refused. |
| Cannot analyze | 06 Nicolas Mahut | Contact phase, verdict refused. |
| Cannot analyze | 07 Tommy Haas | Arm unreliable / racket arm unclear. |
| Green | 08 Roger Federer | Right arm, 85.3°. |
| Green | 09 Novak Djokovic | Right arm, 111.1°, fixed focus crop. |
| Cannot analyze | 10 Maria Sharapova | Contact phase, verdict refused. |

2026-10-11 update: 05, 06, and 10 are follow-through or contact moments, and the new version refuses to measure them; manually selecting an arm or widening the range cannot bypass this check. The old result screenshots belong to a historical version. The red flow can be demonstrated with the McEnroe photo set to 110–120°, with the explanation that this is a settings demonstration, not verified faulty technique.

These ten photos are not "all ten kinds of situations" or proof of model accuracy. They are sourced regression examples, still limited by the single-photo moment, camera angle, crop, occlusion, person size, clothing, lighting, and model estimation. Remind students in particular: red only means this 3D estimate fell outside the currently set demonstration range; green does not mean the movement is correct, healthy, or safe; and cannot analyze does not mean the player moves badly.

## New Real Photos and Motion-Capture Exercises

`docs/demo-assets/teaching-photos/` holds six supplementary photos for comparing left-handed serves, occlusion, contact, and follow-through. `taipei/` holds 29 real photos with manual 2D annotations; first use the contact sheet to judge the phase, then upload S_030, S_120, S_200, S_300. The new version applies a fixed crop based on person size and shows the crop on screen; it does not pick the angle most favorable to a green result. Out of this batch, the eight visually preparation-pose photos went from 0 analyzable to 4, and the other 19 phases are all refused; that is the usability rate of a development sample and must not be called an accuracy rate.

Extension question: Why can't manual 2D points, model-estimated 3D, optical ground-truth data, and coach correctness labels be interchanged? Reference answer: 2D has no depth; model 3D can still be estimated wrong; optical motion capture can verify geometry but these two clips have no corresponding photos or Trophy moments; and only coach labels answer technical correctness. The current HP/RP are participant ability categories, not per-frame correctness labels.

The teacher can use the following commands, with a separate output folder for student exercise reports:

```bash
.venv/bin/python scripts/evaluate_photos.py --output archive/class-photos --save-overlays
.venv/bin/python scripts/evaluate_mocap.py --report-dir archive/class-mocap
```

The motion-capture tool compares two independent angle formulas; the maximum difference over the recorded 12,000 valid readings is about 1.85e-12°. That proves the math implementations agree; it cannot serve as photo angle error. The coach correctness labels and photo-measured 3D errors in the reports are kept as `null`. `class-mocap` must be a new folder to avoid overwriting reports. When showing or distributing photos, crops, and angle tables, keep each dataset's author, source, and CC license with them; motion-capture derivative data uses CC BY-SA 3.0.

## Common Failures and On-Site Handling

| Symptom | Do this first | Do not do this |
|---|---|---|
| The launcher says Python cannot be found or the environment cannot be created | Confirm 64-bit Python 3.11 is installed; close and rerun the launcher. | Do not let students download Python installers from unknown sources or manually copy `.venv`. |
| The first installation download fails | Check the classroom network, proxy, or firewall, then rerun; finish the exercises after the model and package downloads complete. | Do not commit model files or network credentials to the repository. |
| The browser does not open automatically | Read the local URL shown in the terminal and open it in a browser on the same computer; confirm it is `127.0.0.1`. | Do not set up a public IP, tunnel, or sharing link. |
| "Model not installed" is displayed | Rerun the launcher through the model download and check steps, then restart the app. | Do not download a same-named `.task` file from an unknown website. |
| Cannot analyze after upload | Switch to a clear, single-person, both-arms-visible authorized photo close to a Trophy Pose; read the displayed reason. | Do not treat cannot analyze as a bug the program must force into a score. |
| Green/red looks counterintuitive | Expand the measurement details and confirm the selected arm, 3D angle, range, and repeat agreement; use an explicit left/right arm for comparison if needed. | Do not claim it proves pose technique, injury risk, or a medical conclusion. |
| A file is rejected | Use a readable JPEG/PNG under 10 MB and under 20 megapixels. | Do not add converted private photos into `docs/demo-assets/`. |

## Student Acceptance (Final 10 Minutes)

Each group passes by showing the teacher, or answering orally, the following five items:

1. Successfully start the local page and explain that it binds only to local `127.0.0.1`, with no API key, account, or public publishing.
2. Get green or red from one authorized example, pointing out which arm was measured, the displayed angle, and the current demonstration range.
3. Get cannot analyze from another authorized example, read out the reason, and explain why refusing is better than forcing a score.
4. Explain that 2D is a flat reference, the 3D world landmarks are the basis for this project's green/red verdict, and acknowledge it is still a single-image estimate.
5. State at least two limitations: for example, it cannot analyze a full swing or video, example results are not coach advice, image quality affects it, and private photos must not be retained or published.

If students can complete these five items, they have verified the behavior the project actually promises: an explainable local single-photo measurement, and an honest refusal when the evidence is insufficient.

## Bonus: Really Change One Line of Python (10 Minutes)

Open `streamlit_app.py`, find `st.title("🎾 TennisPose")`, and change it to `st.title("🎾 Our Group's Tennis Angle Experiment")`, save, and return to the browser. If a Rerun prompt appears, press it; otherwise refresh.

Ask students to point out "which line of code changed, where the page changed, and whether the angle calculation changed". The answer: only the title changed; the measurement logic did not. Then use the same McEnroe photo to confirm the angle and color are consistent. This is the smallest modification-and-regression-check exercise.

## Launcher Recovery Operations

- When a Mac cannot double-click after extraction: open Terminal, type `cd ` (with a trailing space), drag the project folder into the window, press Enter, then run `bash start.command`.
- When Python is missing: first install 64-bit Python 3.11 from the official installation source in the README. On Windows, include the Python Launcher and check PATH during installation; do not install only the latest other major version.
- When an incompatible environment is reported: close all TennisPose windows, rename `.venv` to `.venv-backup`, and rerun. In Mac Finder, press Command+Shift+period to show hidden files. Do not rename code or photo folders.
- When `.tennispose-setup.lock` is reported to exist: first confirm no other installation terminal is running; if a previous installation was interrupted, close the related terminals, delete this lock file in the project folder, and retry. It contains no photos or code.
- `--setup-only` can install and verify before class without opening the web page. `--repair` reruns the package installation and needs the network; if package files are damaged, use the `.venv` rebuild flow above instead.

## Teacher's Note: Local Computation Does Not Mean Every Package Is Fully Offline

In this testing, the existing MediaPipe 0.10.35 background Clearcut telemetry was seen sending failure messages; that does not confirm photos were sent out, and the sent content was not verified. What the launcher turns off is Streamlit usage statistics, so it cannot guarantee MediaPipe also has no telemetry. Use the authorized examples in class, and explain "inference runs locally" separately from "verified fully zero-network". A stricter privacy acceptance requires separately checking dependency and network behavior.
