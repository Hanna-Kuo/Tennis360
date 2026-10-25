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
- Pick a stroke (Stroke Type) and arm, upload one clip of that stroke (MP4/MOV/M4V), and click "Analyze Video"
- Confirm: when the stroke is found, the page shows key-moment times, measured values, and the suggestions list
- Confirm: when no stroke is found, the page shows the explanation text — no crash and no invented score
- Also test serve once: Analysis Type "Stroke Video Analysis", Stroke Type "Serve", upload a serve clip
- Confirm: the serve clip finds the trophy segment and shows the best-frame time and elbow angle
- Confirm: after a successful analysis a skeleton dot diagram appears, the highlighted arm's angle matches the measured value shown, and an out-of-range angle shows a dashed ghost target arm

## 12. Progress Mode

- Analyze the same action twice first (Serve Photo Analysis or Stroke Video Analysis; only successful measurements are saved)
- In the sidebar, set Analysis Type to "Progress" and pick the action you just analyzed
- Confirm: the chart shows at least 2 measurement points (oldest to newest) and the table lists both records (date/time, angle, in target range, Analysis Result)
- Confirm: not-found and cannot-analyze attempts are not saved to the history

## 13. Interface Wording and Multi-Stroke Clips

- Confirm: titles, labels, and buttons use consistent Title Case throughout the website and CLI (e.g. Analysis Settings, Stroke Type, Analyze Video), and result values read Yes / No / Angle in Range
- Confirm: the serve video result heading reads "Detected Trophy Segments" and the word "Heuristic" no longer appears in the interface
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
- [ ] Interface wording: consistent capitalization, no "Heuristic", Progress header reads "Analysis Result"
- [ ] Multi-stroke clip: key moments come from the same swing and are correctly ordered
- [ ] Front/side views: no misjudgment or crash
- [ ] All tests pass

## 15. After Verification

1. Update README: change all 12 actions' status from "✅ Implemented" to "✅ Verified" with one-line descriptions
2. Commit: `Tennis360-serve-fh-bh: verify all 12 actions on real footage`
3. Send me any bugs you find
