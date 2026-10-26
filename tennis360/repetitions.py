"""Multi-repetition analysis: the shared pure rules.

A practice video holds one stroke performed many times. The analysis
modules find and measure every repetition; this module holds the pure
rules shared by the command-line tool and the Streamlit app — the
sequential serve scan, the recording rules, and the shared display
rules (each stroke's time window in the video; the marking for
invalid repetitions; one skeleton diagram per analyzed stroke):

- every successfully analyzed repetition becomes its OWN history record,
  tagged with its repetition index and its key-moment time in the source
  video, so repetitions from one video never collapse into one record;
- when the source video carries a recording time, every repetition
  record's capture time is that recording start plus the repetition's
  own time in the video, so the records' effective time points keep
  the strokes' true hit order under the recording day;
- a repetition that could not be analyzed produces NO record, matching
  the single-analysis rule (only measured results are stored);
- a repetition that could not be analyzed is still listed in the
  results, marked as invalid and not recorded, with the reason when
  the pipeline provides one;
- single (non-repetition) analyses do not pass through here and keep
  their existing behavior.

This module imports nothing from OpenCV or MediaPipe, so the recording
rules are unit testable without a camera pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from tennis360.capture_time import offset_timestamp
from tennis360.history import AnalysisRecord, utc_now_iso
from tennis360.strokes import RepResult


def swing_rep_records(
    reps: list[RepResult],
    *,
    source_file: str,
    action: str,
    arm: str,
    target_source: str = "demo",
    capture_start: str | None = None,
) -> list[AnalysisRecord]:
    """Build one history record per successfully analyzed swing repetition.

    Repetitions with no measured swing are skipped. The result text
    mirrors the single-analysis swing records: the first suggestions, or
    "Angle in Range" when there is nothing to adjust.

    ``capture_start`` is the source video's recording start (an ISO
    UTC timestamp) when the file carries one; each record's capture
    time is then that start plus the repetition's contact time in
    the video, so the repetitions keep their true hit order under
    the video's recording day. Without it the records carry no
    capture time and fall back to their save time.
    """

    records: list[AnalysisRecord] = []
    for rep in reps:
        if not rep.analyzed or rep.metrics is None:
            continue
        metrics = rep.metrics
        issue = (
            "; ".join(rep.suggestions[:2])
            if rep.suggestions
            else "Angle in Range"
        )
        records.append(
            AnalysisRecord(
                recorded_at=utc_now_iso(),
                source_file=source_file,
                action=action,
                arm=arm,
                angle_deg=round(metrics.contact_elbow_deg, 1)
                if metrics.contact_elbow_deg
                else None,
                in_range=metrics.contact_elbow_in_range,
                main_issue_en=issue,
                target_source=target_source,
                rep_index=rep.rep_index,
                video_time_s=rep.contact_time_s,
                captured_at=offset_timestamp(
                    capture_start, rep.contact_time_s
                ),
            )
        )
    return records


@dataclass(frozen=True)
class ServeSample:
    """One sampled video frame's serve measurement, in pure terms.

    The video scan produces these observations per sampled frame; the
    repetition rules below only need these fields, so they stay
    testable without OpenCV or MediaPipe.
    """

    time_s: float
    frame_index: int
    arm: str | None
    angle_degrees: float | None
    wrist_rise: float | None
    in_preparation: bool


def best_trophy_sample(samples: list[ServeSample]) -> ServeSample | None:
    """Pick one serve window's trophy sample — the single-analysis rule.

    The single video analysis scores a clip from the sampled frame
    with the highest wrist inside its trophy segment: a frame the scan
    itself measured, in the preparation position, with a valid elbow
    angle. Applied per serve window, the same rule picks that serve's
    trophy sample. Returns None when the window holds no such sample —
    the repetition then has no measured trophy frame, exactly as a
    clip with no trophy segment has no score.
    """

    eligible = [
        sample
        for sample in samples
        if sample.in_preparation and sample.angle_degrees is not None
    ]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda s: s.wrist_rise if s.wrist_rise is not None else -9.0,
    )


def serve_rep_record(
    *,
    rep_index: int,
    trophy_time_s: float,
    source_file: str,
    angle_degrees: float | None,
    in_range: bool | None,
    arm: str | None,
    requested_arm: str,
    target_source: str = "demo",
    capture_start: str | None = None,
) -> AnalysisRecord | None:
    """Build the history record for one serve repetition, or None.

    The repetition's angle is the video scan's measurement at its
    trophy sample (see :func:`best_trophy_sample`) — the same
    measurement the single video analysis records for a whole clip.
    A repetition is recorded only when a trophy sample was actually
    measured; a repetition without one is not recorded.

    ``capture_start`` is the source video's recording start (an ISO
    UTC timestamp) when the file carries one; the record's capture
    time is then that start plus the trophy-frame time, matching
    the swing-repetition rule.
    """

    if angle_degrees is None:
        return None
    issue = (
        "Angle in Range" if in_range
        else "Elbow Angle Outside Demo Range"
    )
    return AnalysisRecord(
        recorded_at=utc_now_iso(),
        source_file=source_file,
        action="serve",
        arm=arm or requested_arm,
        angle_deg=angle_degrees,
        in_range=in_range,
        main_issue_en=issue,
        target_source=target_source,
        rep_index=rep_index,
        video_time_s=trophy_time_s,
        captured_at=offset_timestamp(capture_start, trophy_time_s),
    )


# --- serve repetition scanning -------------------------------------------------
# Serves are segmented by a SEQUENTIAL scan over the sampled timeline,
# never by grouping a whole-clip signal after the fact: the scan finds
# the next serve from the current cursor, determines its full window,
# and resumes after that serve completed. Between-serve gaps (pauses,
# ball fetching, resetting position) are simply skipped by the forward
# search, so separate serves can never merge into one repetition — the
# failure mode of the whole-clip trophy-segment grouping, where a
# single "segment" bridged every gap between serves. Where the scan
# observed nothing for a long stretch (a sample gap), the timeline is
# split into bursts first and each burst is scanned on its own: in
# automatic arm mode the timeline holds ONLY preparation samples, so
# without the split there is no low sample between serves for the
# valley rule to complete a serve against.

# Two serve peaks closer together than this are guarded against being
# counted as two serves. The serve scan samples at 5 fps by default
# and one serve's trophy plateau spans only a few samples, while real
# serves are seconds apart; 2.0 s (ten samples at the default rate) is
# only a guard against double-counting one serve's own motion — time
# distance alone never splits two serves (see TROPHY_VALLEY_MIN_DROP).
MIN_TROPHY_PEAK_SEPARATION_S = 2.0

# A serve counts as complete — and the next serve can only begin —
# once the wrist has fallen at least this far (body scales) below the
# trophy peak: the arm comes down through the follow-through and the
# player resets. Between two serves the wrist falls by most of the
# preparation band (the pose gate spans wrist rises of -0.25..0.65
# body scales), while one serve's own motion never dips this far
# between its trophy peak and its completion, so two peaks joined by
# only a shallow saddle are one serve, not two. This is a segmentation
# parameter only; it changes no angle, target range, or feedback rule.
TROPHY_VALLEY_MIN_DROP = 0.2

# Consecutive samples farther apart in time than this belong to
# different bursts of observed motion, and the scan treats each burst
# independently. A serve's own samples arrive about 0.2 s apart at the
# scan's 5 fps default (a few dropped detections still land well under
# this bound), while between two serves the scan observes nothing for
# seconds at a time: in automatic arm mode only preparation samples
# are kept at all, so the throw, the reset, and the next serve's early
# climb simply do not exist in the timeline, and in fixed-arm mode an
# arm can be unmeasurable through a whole reset. A gap this large is
# therefore a hard action boundary — it must split the timeline,
# because with no low samples between serves the valley rule has
# nothing to complete a serve against: the "valley" it finds is the
# next serve's own climb, one window absorbs the following serves,
# and every later search restarts mid-climb and discards real serves
# as bumps. (Field failure: a seven-serve clip scanned in automatic
# arm mode reported exactly one serve.) This is a segmentation
# parameter only; it changes no measurement or feedback rule.
SERVE_SAMPLE_GAP_S = 1.0


def _next_serve_action(
    series: list[float], cursor: int, valley_min_drop: float
) -> tuple[int, int, int] | None:
    """Find the next complete serve at or after ``cursor``.

    ``series`` is the sampled wrist-rise timeline. Returns (start, end,
    peak) sample positions: ``peak`` is the serve's trophy sample (its
    highest wrist rise), ``start`` is where the final climb to the peak
    began, and ``end`` is the valley sample where the serve completed —
    the wrist back down after the follow-through, before the next
    action's climb. Returns None when no complete serve remains.

    The walk tracks a running peak: the serve completes only at the
    first genuine fall of ``valley_min_drop`` below the running peak,
    so a small bump on the way up — or the wrist rising further into
    the throw after the trophy moment — simply moves the peak instead
    of ending or splitting the serve. A rise-and-fall too small to be
    a serve (its peak less than ``valley_min_drop`` above the floor it
    rose from) is skipped, and the search resumes after it.
    """

    count = len(series)
    pos = cursor
    while pos < count:
        peak = pos
        j = pos
        fell_at: int | None = None
        while j < count:
            if series[j] > series[peak]:
                peak = j
            if j > peak and series[j] <= series[peak] - valley_min_drop:
                fell_at = j
                break
            j += 1
        if fell_at is None:
            # The series ends with the wrist still up: a final serve
            # cut off by the end of the series counts when its climb
            # was genuine. A series that starts already at its peak
            # counts too when the wrist then genuinely comes down
            # from that peak — its climb happened before the first
            # sample (the clip begins mid-serve; when the scan splits
            # the timeline at a sample gap, the same holds for a burst
            # whose first sample is already at the trophy peak). A
            # flat timeline declines by nothing and is not a serve.
            if peak > pos:
                floor = min(series[pos : peak + 1])
                genuine = series[peak] - floor >= valley_min_drop
            elif peak == pos == 0:
                genuine = (
                    series[peak] - min(series[pos:])
                    >= valley_min_drop / 2
                )
            else:
                genuine = False
            if genuine:
                start = peak
                while start > pos and series[start - 1] <= series[start]:
                    start -= 1
                return start, count - 1, peak
            return None
        # The valley the serve completes into: the lowest sample after
        # the peak, before the signal climbs back into the next action.
        end = peak
        lowest = series[peak]
        j = peak
        while j < count:
            if series[j] < lowest:
                lowest = series[j]
                end = j
            if j > end and series[j] > lowest + valley_min_drop:
                break
            j += 1
        floor = min(series[pos : peak + 1])
        if series[peak] - floor >= valley_min_drop or peak == pos == 0:
            # ``peak == pos == 0``: the series itself starts mid-serve,
            # already at the trophy position; the climb happened
            # before the first sample, so the rise test cannot see it.
            # (The scan feeds the series burst by burst, so this is
            # the start of a burst, not only of the whole clip.)
            start = peak
            while start > pos and series[start - 1] <= series[start]:
                start -= 1
            return start, end, peak
        # Too small to be a serve (an arm wave, a ball catch): skip
        # past its completion and keep searching from there.
        pos = end + 1
    return None


def find_serve_actions(
    times_s: list[float],
    wrist_rises: list[float | None],
    *,
    min_separation_s: float = MIN_TROPHY_PEAK_SEPARATION_S,
    valley_min_drop: float = TROPHY_VALLEY_MIN_DROP,
    in_preparation: list[bool] | None = None,
    gap_s: float = SERVE_SAMPLE_GAP_S,
) -> list[tuple[int, int, int]]:
    """Scan a serve clip's sampled timeline and return every serve.

    ``times_s`` and ``wrist_rises`` are parallel per-sample lists from
    the video scan (sample times and trophy-signal wrist rises; a None
    rise counts as no signal). Returns one (start, end, peak) sample
    triple per serve, in time order, with non-overlapping windows.

    The timeline is first split into bursts at sample gaps larger
    than ``gap_s`` (see SERVE_SAMPLE_GAP_S): where the scan observed
    nothing for that long, one action has ended and another has not
    yet begun, so no serve window, valley search, or cursor ever
    crosses a gap. Within a burst the scan is sequential: each serve
    is found by a fresh search that starts only after the previous
    serve's completion, and two serves are separate only when a
    genuine valley — the wrist falling by ``valley_min_drop`` — lies
    between their trophy peaks, matching how serves actually happen
    (the player stops, fetches balls, and resets between them). The
    ``min_separation_s`` guard additionally refuses to count a
    rise-and-fall within that span of the previous serve's peak as a
    new serve.

    When ``in_preparation`` is given (parallel per-sample flags from
    the scan's preparation gate), a rise-and-fall counts as a serve
    only if its window contains at least one preparation sample: the
    motion must actually pass through the trophy position. A prep
    bump that never raises the arm into the preparation position — a
    ball bounce, a half practice motion — cannot be scored by any
    analysis path in the product (every serve score comes from a
    preparation frame), so it is not counted as a detected serve
    either. Skipped windows still advance the cursor past them, and a
    skipped window in one burst never affects the next burst.
    """

    series = [
        rise if rise is not None else float("-inf") for rise in wrist_rises
    ]
    # Burst boundaries: sample positions where a new burst starts.
    # Each burst is scanned on its own (sliced), so the per-burst
    # positions below are burst-relative and offset when recorded.
    burst_starts = [0]
    for position in range(1, len(series)):
        if times_s[position] - times_s[position - 1] > gap_s:
            burst_starts.append(position)
    burst_starts.append(len(series))

    actions: list[tuple[int, int, int]] = []
    last_peak_time: float | None = None
    for burst_lo, burst_hi in zip(burst_starts, burst_starts[1:]):
        sub_series = series[burst_lo:burst_hi]
        sub_times = times_s[burst_lo:burst_hi]
        sub_preparation = (
            in_preparation[burst_lo:burst_hi]
            if in_preparation is not None
            else None
        )
        cursor = 0
        while cursor < len(sub_series):
            found = _next_serve_action(sub_series, cursor, valley_min_drop)
            if found is None:
                break
            start, end, peak = found
            if (
                last_peak_time is not None
                and sub_times[peak] - last_peak_time < min_separation_s
            ):
                # A genuine rise-and-fall, but too soon after the
                # previous serve to be a separate one: it belongs to
                # that serve's own motion. Skip it — the cursor still
                # moves past it.
                cursor = end + 1
                continue
            if sub_preparation is not None and not any(
                sub_preparation[start : end + 1]
            ):
                # A rise-and-fall that never passes through the
                # trophy position is not a serve. Skip it — the
                # cursor still moves past it, and it does not become
                # the "previous serve" for the separation guard.
                cursor = end + 1
                continue
            actions.append((burst_lo + start, burst_lo + end, burst_lo + peak))
            last_peak_time = sub_times[peak]
            cursor = end + 1
    return actions


# --- repetition display text -----------------------------------------------------
# Every detected stroke is shown with the part of the video it
# occupies — its window from start second to end second — in the
# website results table and the command-line per-stroke lines, for
# valid and invalid strokes alike, so the user can see exactly which
# seconds of the clip each stroke covers and which ones succeeded.


def format_time_window(start_s: float, end_s: float) -> str:
    """Results-display text for one stroke's window in the source video."""

    return f"{start_s:.1f} s – {end_s:.1f} s"


def render_stroke_diagrams(candidates, extract_landmarks, build_png):
    """Render one skeleton diagram per successfully analyzed stroke.

    ``candidates`` holds one dict per detected stroke, in video order,
    with keys ``rep_index``, ``analyzed``, ``time_s`` (the stroke's key
    moment), ``arm``, ``angle``, ``minimum`` and ``maximum``.
    ``extract_landmarks(time_s)`` returns the key frame's 2D landmarks,
    or None when that frame shows no detectable pose; ``build_png`` is
    the skeleton-diagram renderer, called as ``build_png(points,
    arm=..., angle_deg=..., minimum=..., maximum=...)`` with the
    landmarks as plain (x, y) pairs, and returns PNG bytes.

    Returns ``[(rep_index, png_bytes)]`` in stroke order. A stroke that
    was not successfully analyzed is never rendered, and an analyzed
    stroke whose key frame yields no landmarks is skipped — no
    placeholder diagram is produced for either. Diagrams are a
    best-effort display extra: a failure while extracting or rendering
    one stroke's diagram skips that diagram, never the results.
    """

    diagrams = []
    for candidate in candidates:
        if not candidate["analyzed"]:
            continue
        if candidate["arm"] is None or candidate["angle"] is None:
            continue
        try:
            landmarks = extract_landmarks(candidate["time_s"])
        except Exception:
            continue
        if not landmarks:
            continue
        points = [(float(point.x), float(point.y)) for point in landmarks]
        try:
            png = build_png(
                points,
                arm=candidate["arm"],
                angle_deg=float(candidate["angle"]),
                minimum=candidate["minimum"],
                maximum=candidate["maximum"],
            )
        except Exception:
            continue
        diagrams.append((candidate["rep_index"], png))
    return diagrams


# --- invalid-repetition display --------------------------------------------------
# The two-way rule for repetitions that cannot be validly analyzed:
# they are NEVER recorded to history, but they are always SHOWN in the
# results list, marked with INVALID_REP_RESULT plus a brief reason when
# the pipeline can provide one — so the user sees that each invalid
# repetition was found and deliberately skipped, not silently dropped.

INVALID_REP_RESULT = "Invalid — Not Recorded"


def invalid_rep_result(reason: str | None) -> str:
    """Results-list text for a found-but-invalid repetition."""

    if reason:
        return f"{INVALID_REP_RESULT}: {reason}"
    return INVALID_REP_RESULT


def swing_rep_invalid_reason(rep: RepResult) -> str | None:
    """Why a swing repetition could not be analyzed, when reported.

    The single-swing analysis explains a refusal in its suggestions
    (for example "No clear swing found in this clip."); the first
    suggestion is the reason shown next to the invalid marking.
    """

    if rep.analyzed:
        return None
    return rep.suggestions[0] if rep.suggestions else None


def serve_rep_invalid_reason(error: str | None) -> str | None:
    """Why a serve repetition could not be analyzed, when known.

    ``error`` is the repetition's own explanation — for example that
    its window held no measured trophy frame. There is no other
    report to consult: serve repetitions are scored from the video
    scan, not from a per-repetition photo analysis.
    """

    return error or None
