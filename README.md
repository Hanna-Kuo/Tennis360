# 🎾 Tennis360

### Tennis Pose and Stroke Analysis

**Analyze your form. Understand your technique. Track your progress.**

Tennis360 is a computer vision-based tennis training application that helps players examine their movements using photographs and videos. It combines body landmark detection, joint-angle measurements, visual diagrams, and technique feedback in a local web application. The goal is to make movement analysis more accessible to players who do not have specialized motion-capture equipment.

Built for the **Congressional App Challenge**, Tennis360 currently supports **12 tennis actions**, with three modes: **Serve Photo Analysis**, **Stroke Video Analysis**, and **Progress**.

> **Note:** Tennis360 is a practice tool, not a replacement for a coach. Its current target ranges are examples for analysis, not coach-validated standards for perfect technique.

## Features

### 1. Serve Photo Analysis

Upload a tennis serve photo taken during the **Trophy Pose** to examine the racket-arm position.

- Detects estimated shoulder, elbow, and wrist landmarks with MediaPipe.
- Automatically identifies the racket arm, with an option to select the right or left arm manually.
- Estimates the elbow angle using MediaPipe's inferred 3D body landmarks.
- Compares the measurement with a **configurable target range** (80°–120° by default).
- Displays a **Green**, **Red**, or **Cannot Analyze** result, depending on the angle and whether the image can be evaluated reliably.
- Produces an annotated photograph showing the body landmarks, elbow angle, and result.
- Performs repeated measurement checks and reports agreement between valid estimates.
- Explains how the displayed angle was calculated and provides context for interpreting the result.

A Green result indicates that the *measured elbow angle* is inside the selected range; it does **not** mean that the entire serve is technically correct.

### 2. Stroke Video Analysis

Upload a video, select a tennis stroke, and analyze multiple attempts from the same practice clip.

- Supports **12 tennis actions**, including serves, groundstrokes, slices, volleys, overheads, and specialty shots.
- Accepts **MP4, MOV, and M4V** videos and processes them locally.
- **Analyze All Strokes** identifies individual attempts in the video and analyzes each one separately, so there is no need to trim every stroke into a different file.
- Lists each detected stroke by number, estimated contact or key-moment time, time range in the video, elbow angle, target-range result, and feedback.
- Shows a body-landmark skeleton and highlighted elbow angle for individual strokes, with a suggested adjustment when applicable.
- Identifies attempts that cannot be measured reliably and explains why they were not recorded.
- Saves each successfully analyzed stroke as a separate entry in **Progress**. Analyzing the same video again does not create duplicate entries.
- Measures additional movement checkpoints where supported, such as preparation, follow-through, contact-point position, wrist movement, and shoulder turn.

For serves, analysis focuses on the estimated Trophy Pose. For other strokes, the reported contact moment is an estimate based on movement in the video, not an exact measurement of racket–ball contact.

### 3. Progress Tracking

Keep a record of your practice and compare measured elbow angles across attempts.

- View separate progress charts for each supported tennis stroke.
- See **one point per saved attempt**, numbered in the order the strokes were recorded or analyzed.
- Compare measurements against the selected stroke's demonstration target range.
- Review practice history grouped by recording date, using the photo or video's capture time when available and the saved analysis time otherwise.
- Open a table showing attempt number, date and time, measured elbow angle, whether it was in range, time within the source video, and analysis result.
- Select and delete individual records you no longer want to keep, with confirmation before deletion.
- Store measurements in a **local SQLite database** without storing uploaded photos or videos in the history.

The charts show how measurements vary from attempt to attempt, not an overall tennis performance score. The displayed ranges are for demonstration and have not yet been validated by coaches.

## Supported Tennis Actions

| # | Tennis Action | Photo Analysis | Video Analysis |
|---|---|:---:|:---:|
| 1 | Serve | ✅ Trophy Pose | ✅ |
| 2 | Forehand — Topspin | — | ✅ |
| 3 | Forehand — Slice | — | ✅ |
| 4 | Backhand — Topspin (Two-Handed) | — | ✅ |
| 5 | Backhand — Topspin (One-Handed) | — | ✅ |
| 6 | Backhand — Slice | — | ✅ |
| 7 | Volley — Forehand | — | ✅ |
| 8 | Volley — Backhand | — | ✅ |
| 9 | Half-Volley — Forehand | — | ✅ |
| 10 | Overhead Smash | — | ✅ |
| 11 | Drop Shot — Forehand | — | ✅ |
| 12 | Lob — Forehand | — | ✅ |

Future updates will add more tennis strokes and variations, as well as Ready Position and Footwork analysis.

## How Tennis360 Works

1. **Select an analysis mode.** Choose a serve photo, one of the supported stroke videos, or your saved progress history.
2. **Upload a photo or video.** The application processes the media locally.
3. **Estimate body landmarks.** MediaPipe detects positions such as the shoulders, elbows, wrists, hips, knees, and ankles.
4. **Measure movement.** Tennis360 calculates relevant joint angles and other movement indicators using estimated landmarks. Photo serve analysis includes multiple measurement checks.
5. **Review visual feedback.** The application displays measured angles, annotated photos or skeleton diagrams, reference ranges, and adjustment suggestions.
6. **Compare practice sessions.** Successful measurements are saved locally and can be viewed in Progress.

## Technology

| Technology | Role |
|---|---|
| **Python** | Application and analysis logic |
| **Streamlit** | Local interactive web interface |
| **MediaPipe** | Body pose detection and estimated landmarks |
| **OpenCV** | Video frame extraction and image processing |
| **NumPy** | Angle and movement calculations |
| **Matplotlib** | Progress charts and visualizations |
| **Pandas** | Organizing analysis history |
| **SQLite** | Locally stored measurements |
| **Pillow** | Image handling |

## Run Locally

### Requirements

- **Python 3.11, 64-bit**
- **macOS or Windows**
- A web browser
- Internet access for initial dependency/model setup

### Installation

**1. Download Tennis360**

Download the repository as a ZIP file from GitHub and extract it to your computer.

**2. Open the project folder**

Open Terminal and use `cd` to navigate to the extracted Tennis360 folder:

```bash
cd /path/to/Tennis360
```

You can also type `cd`, add a space, and drag the project folder into Terminal to fill in its path.

**3. Start Tennis360**

On **macOS**, run:

```bash
./start.command
```

On **Windows**, run `start.bat` from the project folder.

The launcher checks the Python environment, sets up required dependencies if needed, and starts the application.

**4. Open the application**

Tennis360 should open automatically in your browser. If it doesn't, visit:

**http://127.0.0.1:8501**

Keep Terminal open while using Tennis360. Press `Ctrl+C` to stop the application.

## Using the Application

**Serve Photo Analysis:** Select the mode, upload a Trophy Pose image, choose automatic or manual racket-arm selection, and review the annotated image, elbow-angle estimate, result, and measurement details.

**Stroke Video Analysis:** Select a stroke and racket arm, upload a video, then click **Analyze All Strokes**. Tennis360 detects and evaluates individual attempts in the clip. You can review each stroke in the results table and the accompanying diagrams. Successfully analyzed attempts are saved to Progress; invalid attempts are listed with an explanation but are not saved.

**Progress:** Select a stroke to see an elbow-angle chart by attempt, review saved measurements and recording dates, or remove selected records.

## Privacy and Local Storage

Tennis360 runs on the user's own computer. Uploaded media is processed by the local application rather than being sent to a cloud analysis service. Temporary video files used for processing are deleted after analysis. The history database stores **measurement records, not uploaded photos or videos**.

Saved history is stored locally at `~/.tennis360/history.db`.

## Future Improvements

There is still a lot I want to add to Tennis360, especially more stroke coverage and feedback based on examples reviewed by tennis coaches. Planned improvements include:

### Additional Movement Analysis

- **Ready Position and Split Step:** Analyze knee bend, stance width, hip alignment, and preparation for incoming shots.
- **Footwork and Recovery:** Evaluate lateral movement, forward/backward movement, recovery steps, and balance.
- **More Strokes and Variations:** Keep expanding the selection of strokes and variations beyond the 12 currently supported.
- **Full-Body Measurements:** Add more detailed analysis of shoulder, hip, knee, and ankle angles instead of focusing primarily on the racket-arm elbow.
- **Detailed Serve Breakdown:** Evaluate the starting stance, ball toss, Trophy Pose, contact, and landing as separate phases.
- **Additional Technique Indicators:** Explore grip positioning, body rotation, weight transfer, and balance.

### Coach Collaboration and Better Reference Standards

- **Collaborate with tennis coaches** to review the analysis approach and develop stroke-specific evaluation criteria.
- **Build a larger reference dataset** by collecting more professional-player and coach-demonstrated movement examples, with appropriate permissions.
- **Develop improved comparison baselines** using multiple high-quality reference examples rather than relying on a single demonstration angle range.
- **Introduce meaningful technique scores** only after the relevant measurements and scoring criteria have been reviewed and validated.
- **Provide more detailed coaching suggestions** informed by coach-reviewed examples and differences between the player's movement and the comparison baseline.

### Smarter Analysis and Comparisons

- **Automatic Stroke Recognition:** Identify the tennis action from video without requiring users to select it manually.
- **Side-by-Side Pose Comparison:** Compare a player's movement with a reference technique example.
- **Improved Camera-Angle Awareness:** Combine additional signals to detect difficult viewing angles and improve the reliability of pose measurements.
- **Richer Progress Reports:** Show movement-specific changes across multiple sessions as more validated measurements become available.

## Limitations

- Pose estimation depends on visibility, video quality, camera angle, lighting, and the movement of the player.
- Estimated 3D landmarks are **not** equivalent to calibrated 3D motion capture.
- Stroke phase detection and reported contact moments may be approximate.
- Current angle ranges are **configurable demonstration references**, not universally validated coaching standards.
- A measurement being inside or outside a target range does not by itself determine whether the overall stroke is correct.
- Current feedback is rule-based and should not be interpreted as individualized professional coaching.

## Project Purpose

Tennis lessons can be expensive, and even players who work with a coach cannot have one at every practice. When practicing alone, it can be difficult to see what needs to change or tell whether an adjustment made a difference.

I created Tennis360 to give players another way to review their technique between lessons. By analyzing photos and videos, the app shows body positions, joint-angle measurements, and suggestions that players can refer to during independent practice. The Progress page also lets players look back at earlier measurements instead of relying only on memory.

The goal is not to replace tennis coaches. I want Tennis360 to become a useful tool alongside coaching, especially as more stroke variations are added and experienced coaches help develop better reference examples, technique comparisons, and feedback.

**Project:** Tennis360  
**Competition:** Congressional App Challenge  
**Application:** Local Python / Streamlit web app

---

*🎾 Tennis360 — Analyze Your Form. Understand Your Technique. Track Your Progress.*
