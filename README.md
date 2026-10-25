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

Upload a video, choose the tennis action, and receive a breakdown of its movement checkpoints.

- Supports **12 tennis actions**, including serves, topspin groundstrokes, slices, volleys, overheads, and specialty shots.
- Accepts **MP4, MOV, and M4V** uploads.
- Samples video frames locally and uses pose landmarks to estimate key moments in the stroke.
- Reports timing information for relevant phases, such as **Preparation**, **Contact**, and **Follow-Through**. Serve analysis focuses on the detected Trophy Pose.
- Displays movement-specific measurements, which may include elbow angle, shoulder turn, wrist position, contact-point location, follow-through, and backswing characteristics.
- Offers suggested technique adjustments based on the detected checkpoints.
- Generates a **skeleton visualization** highlighting the analyzed arm and measured elbow angle; when applicable, a dashed reference arm illustrates a target position.

**Important:** Detected phases and contact times are estimates based on visible motion, not precise racket–ball contact detection. The measurements and feedback available depend on the selected stroke and the usable video data.

### 3. Progress Tracking

Review saved measurements to see how your technique measurements vary over time.

- Saves measurements from successful photo and video analyses.
- Displays a **line chart of elbow angles over time** for the selected stroke.
- Highlights the demonstration target-angle range on the graph.
- Shows a table of recent analyses, including dates, measured angles, whether a measurement fell within the target range, and analysis results.
- Keeps measurement history in a **local SQLite database**, without saving uploaded photos or videos to that history.

Progress graphs show measurement trends, **not an overall performance grade**. A changing angle does not necessarily indicate improvement without considering the stroke, camera view, and context.

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

Future development will expand Tennis360’s range of supported strokes and variations, along with Ready Position and Footwork analysis.

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

**Stroke Video Analysis:** Select the mode, choose a stroke and arm, upload a supported video, click **Analyze Video**, and review key moments, measured checkpoints, suggestions, and the skeleton visualization.

**Progress:** Select the mode and stroke to view your saved elbow-angle trend and recent analysis records.

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

**Already implemented:** Stroke Video Analysis and Progress Tracking. These are current features, not future milestones.

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
