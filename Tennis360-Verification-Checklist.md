# Tennis360 Serve + Strokes Verification Checklist

> Scope: Verify all 12 actions — serve, forehand (topspin + slice), backhand (topspin one-handed + two-handed, slice), forehand volley, backhand volley, half-volley, overhead, drop shot, and lob. This package is complete.
> All 12 actions are in this package: Serve, Forehand: Topspin, Forehand: Slice, Backhand: Topspin – Two-Handed, Backhand: Topspin – One-Handed, Backhand: Slice, Volley: Forehand, Volley: Backhand, Half-Volley: Forehand, Overhead Smash, Drop Shot: Forehand, and Lob: Forehand. The package is now complete.
> Test Build: tennis360-serve-fh-bh.zip

## 1. Environment

```bash
cd <project folder>
python -m pytest tests/ -q
```
- Confirm all tests pass

## 2. Serve

### Photo Analysis (Optional — Hanna decided on 2026-10-24 to skip this and verify with video instead)
```bash
streamlit run streamlit_app.py
```
- Upload a serve Trophy Pose photo
- Confirm: racket arm detected, elbow angle measured

### Video Analysis
```bash
python -m tennis360.cli analyze <serve video>.mp4 --action serve
```
- Confirm: serve preparation found, no misjudgment, no crash
- Test one front-view and one side-view clip

## 3. Forehand

```bash
python -m tennis360.cli analyze <forehand video>.mp4 --action forehand
```
- Confirm: swing found (backswing → contact → follow-through)
- No crash

## 4. Backhand

```bash
python -m tennis360.cli analyze <backhand video>.mp4 --action backhand-one
python -m tennis360.cli analyze <backhand video>.mp4 --action backhand-two
```
- Test one-handed and two-handed separately
- Confirm: swing found, no crash

## 5. Slice (Forehand + Backhand)

```bash
python -m tennis360.cli analyze <forehand slice video>.mp4 --action forehand-slice
python -m tennis360.cli analyze <backhand slice video>.mp4 --action backhand-slice
```
- Test forehand slice and backhand slice separately (both share the same slice analysis)
- Confirm: swing found (backswing → contact → follow-through)
- No crash

## 6. Volley

```bash
python -m tennis360.cli analyze <volley video>.mp4 --action volley-forehand
python -m tennis360.cli analyze <volley video>.mp4 --action volley-backhand
```
- Test forehand volley and backhand volley separately
- Confirm: volley motion found (compact backswing → contact → forward push)
- No crash

## 7. Overhead

```bash
python -m tennis360.cli analyze <overhead video>.mp4 --action overhead
```
- Confirm: overhead motion found (preparation → contact at highest point → follow-through)
- No crash

## 8. Drop-shot

```bash
python -m tennis360.cli analyze <drop-shot video>.mp4 --action drop-shot
```
- Confirm: drop-shot motion found (backswing → soft contact → short follow-through)
- No crash

## 9. Lob

```bash
python -m tennis360.cli analyze <lob video>.mp4 --action lob
```
- Confirm: lob motion found (low backswing → upward contact → high follow-through)
- No crash

## 10. Half-volley

```bash
python -m tennis360.cli analyze <half-volley video>.mp4 --action half-volley
```
- Confirm: half-volley motion found (knee bend → low contact right after the bounce → compact swing)
- No crash

## 11. Website Video Mode

```bash
streamlit run streamlit_app.py
```
- In the sidebar, set Analysis Type to "Stroke Video Analysis"
- Pick a stroke (Stroke Type) and arm, upload one clip of that stroke (MP4/MOV/M4V), and click "Analyze All Strokes"
- Confirm: the page lists every detected stroke in the "All Detected Strokes in This Video" table (Stroke number, key-moment time, measured values, result), with the "Strokes Detected: N | Successfully Analyzed: M" counts
- Confirm: when no stroke is detected, the page shows the explanation text — no crash and no invented score
- Also test serve once: Analysis Type "Stroke Video Analysis", Stroke Type "Serve", upload a serve clip
- Confirm: each serve in the clip is listed with its trophy-frame time and elbow angle

## 12. Progress Mode

- Analyze the same action twice first (Serve Photo Analysis or Stroke Video Analysis; only successful measurements are saved)
- In the sidebar, set Analysis Type to "Progress" and pick the action you just analyzed
- Confirm: the chart shows at least 2 measurement points and the table lists both records (date/time, angle, in target range, Analysis Result)
- Confirm: the chart's x-axis is numbered by attempt (1, 2, 3, …) at exactly equal spacing in time order (oldest to newest) — it is not a calendar date axis, the spacing never varies, and several records from the same day spread out as separate points instead of stacking into one vertical line
- Confirm: dates appear only in the label row under the axis, grouped into sections — one label per section, centered under its attempts. The section unit is the finest one (days, then weeks starting on Monday, then months, then years) that keeps the section count at or below 15: a handful of attempts spread over months still shows one day section per practice day; more than 15 practice days roll up to "Week of …" sections; longer histories roll up to months, then years
- Confirm: with 15 or fewer points, every point is labelled with its angle value; with more than 60 points, no markers are drawn — the chart is one clean line
- Confirm: the table's Attempt column gives each record the same number the chart plots for it (the table lists newest first, so its Attempt values run from the highest number down to 1); after deleting a record, the chart and the table renumber the remaining records together (1..N over the survivors in both places)
- Confirm: the Progress table has NO "Stroke" column — Attempt is the only numbering it shows (the per-video stroke number still appears in the Stroke Video results list, and the records' Video Time column is still in the Progress table)
- Capture time first (do this on the Mac with a real phone clip): pick a practice video that was RECORDED on an earlier day than today (check the recording date in Finder/Get Info or the Photos app first) and analyze it (Stroke Video Analysis → Analyze All Strokes). Then open Progress and confirm: the new records' Date/Time shows the RECORDING day and time (for a multi-stroke clip, the recording start plus each stroke's time in the video), the records are numbered and sectioned under the recording day — not under today — and the table's sort order matches. A serve photo with EXIF behaves the same way (photo's capture day, not analysis day)
- Capture-time fallback: analyze a clip that carries NO embedded recording time (for example a screen recording, or a clip re-exported through an editor that strips metadata) and confirm its records show the analysis (upload) time as their Date/Time and are ordered by it — the fallback is silent and nothing is invented
- Confirm: not-found and cannot-analyze attempts are not saved to the history
- Selective deletion: confirm the records table has a Delete checkbox per record, and with nothing ticked the "Delete Selected Records" button is disabled
- Tick the Delete box beside one record (note its date/time), click "Delete Selected Records", then click "Cancel" — confirm: nothing is deleted; the record is still listed and the chart is unchanged
- Tick the same record again, click "Delete Selected Records", then "Confirm Delete" — confirm: only that record disappears from the table, the chart redraws from the remaining records only (its points renumber from 1 over the records that remain, and the date sections recompute over the survivors), and every unmarked record (including other strokes saved from the same video, and records of other stroke types) is unchanged

## 13. Interface Wording and Multi-Stroke Clips

- Confirm: titles, labels, and buttons use consistent Title Case throughout the website and CLI (e.g. Analysis Settings, Stroke Type, Analyze All Strokes), and result values read Yes / No / Angle in Range
- Confirm: the word "Heuristic" no longer appears in the interface
- Confirm: the Progress table header reads "Analysis Result" (not "Main Issue"), and in-range records show a positive result (e.g. Angle in Range) instead of an issue
- Multi-stroke clip check: analyze a clip containing 2 swings and confirm the Backswing, Contact, and Follow-Through times all come from the same swing, in the order Backswing < Contact < Follow-Through

## 14. Pass Criteria

- [ ] (Optional) Photo analysis correct
- [ ] Serve video finds the serve motion
- [ ] Forehand video finds the swing
- [ ] Backhand (one + two handed) videos find the swing
- [ ] Slice (forehand + backhand) videos find the swing
- [ ] Volley (forehand + backhand) videos find the volley motion
- [ ] Overhead video finds the overhead motion
- [ ] Drop-shot video finds the drop-shot motion
- [ ] Lob video finds the lob motion
- [ ] Half-volley video finds the half-volley motion
- [ ] Website Stroke Video Analysis mode analyzes a clip and shows results
- [ ] Progress mode chart and table show repeated measurements for one action
- [ ] Progress selective deletion: marked records are deleted after confirmation (cancel deletes nothing), and the chart and table keep only the remaining records
- [ ] Interface wording: consistent capitalization, no "Heuristic", Progress header reads "Analysis Result"
- [ ] Multi-stroke clip: key moments come from the same swing and are correctly ordered
- [ ] Multi-stroke video: all strokes counted, per-stroke results listed, Progress grows by the number of successfully analyzed strokes
- [ ] Front/side views: no misjudgment or crash
- [ ] All tests pass

## 15. After Verification

1. Update README: change all 12 actions' status from "✅ Implemented" to "✅ Verified" with one-line descriptions
2. Commit: `Tennis360-serve-fh-bh: verify all 12 actions on real footage`
3. Send me any bugs you find

## 16. Multi-Stroke Video Analysis

A practice video holds one stroke performed many times; every stroke must be analyzed and recorded separately. Strokes are found by a sequential scan: each stroke is located by a fresh search that starts after the previous stroke completed, so separate strokes can never be merged into one.

```bash
python -m tennis360.cli analyze <multi-stroke practice video>.mp4 --action forehand --reps
python -m tennis360.cli analyze <multi-serve video>.mp4 --action serve --reps
```
- Count the strokes in the video by hand first; confirm "Strokes Detected" matches
- Serves: use a clip with several separate serves (for example seven serves with pauses, ball fetching, and resets between them). Confirm the scan reports one stroke per serve — even when the single analysis of the same clip reports one long trophy segment — and that each serve's trophy-frame time matches a serve you counted by hand
- Serves (failure mode — every stroke Invalid): use a multi-serve clip where the single analysis succeeds (Serve Found, with an elbow angle). Confirm "Analyze All Strokes" does NOT report every serve as "Invalid — Not Recorded": each serve is scored from the video scan's trophy-frame measurement — the same machinery the single analysis scores a whole clip with — and is recorded with that angle. Serve repetitions must NOT be scored by re-running the still-photo pipeline on an extracted frame: its player-focus and stability guards are written for uploaded photos and refuse video frames wholesale (focus changed the detected player / focused player could not be measured / no clear trophy-position preparation cues), even for frames the scan itself measured. A serve is Invalid only when its own window holds no measured trophy frame ("No clear trophy frame was measured in this serve.")
- Serves: confirm "Strokes Detected" counts only motions that pass through the trophy position — prep bumps that never raise the arm into the preparation position (bouncing the ball, half practice motions) are not counted as serves
- Serves (failure mode — detected count collapses to 1): use the same multi-serve clip twice, once with Arm = Auto and once with Arm = Right (or Left). Confirm "Strokes Detected" matches your hand count under BOTH arm settings, and that each serve's "Time in Video" window stays within that serve itself (no window stretches across the pause into the next serve). Background: in Auto the scan keeps only preparation samples, so between serves the sampled timeline is empty for seconds and holds no low samples; the serve scan must treat such a sample gap as a hard boundary between actions (it splits the timeline into bursts and scans each burst on its own). Scanning the filtered timeline as one continuous signal lets one window absorb the following serves — the reported count collapses to a single stroke with one long window (for example 2.6 s – 9.6 s on a seven-serve clip) even though the per-serve scoring itself is correct. If the count collapses under Auto but matches under a fixed arm, this failure mode is back
- Confirm: every detected stroke is listed separately (Stroke number, contact time — or trophy-frame time for serves — elbow angle, in-range Yes/No), numbered by its order in the video whether or not it could be analyzed
- Confirm: each stroke's row shows its "Time in Video" — that stroke's start–end seconds in the source video (for example "12.4 s – 15.1 s") — for valid and invalid strokes alike; the command-line per-stroke lines show the same start–end range
- Confirm: below the "All Detected Strokes in This Video" table there is one skeleton diagram per SUCCESSFULLY ANALYZED stroke, in stroke order, captioned "Stroke N — <start> s – <end> s" and drawn from that stroke's key moment (trophy frame for serves, contact frame for swings): skeleton points and lines, the measured arm highlighted, the elbow angle labeled, and a dashed target arm when the angle is outside the target range. Invalid strokes have NO diagram, and no placeholder is shown for them
- Confirm: Progress grows by exactly the number of successfully analyzed strokes; each stroke is its own record, tagged with its Stroke number and its time in the video
- Confirm the two-way rule for invalid strokes: a stroke that cannot be validly analyzed (pose not detected, no clear/complete swing, invalid data) is listed in the results as "Invalid — Not Recorded" with a brief reason and BLANK measurement fields (no angle, no in-range value), and is NOT saved to Progress; the counts distinguish Strokes Detected / Successfully Analyzed / Invalid and skipped (website and command line)
- Website: Stroke Video Analysis → upload the same practice clip → click "Analyze All Strokes" (the one analysis button) → confirm the "All Detected Strokes in This Video" table and the "Strokes Detected: N | Successfully Analyzed: M" counts; then open Progress and confirm the new records appear (Attempt and Video Time columns)
- Confirm: reanalyzing the same clip in the website does not add duplicate records
- Confirm: the website has ONE analysis button, "Analyze All Strokes"; the command-line single analysis (`analyze` without `--reps`) is unchanged (one swing per clip, one record)
