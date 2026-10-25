"""Tennis360 desktop deep-analysis command line.

Local-only: every command runs on this computer. Analysis *results*
(numbers, verdicts) may be stored in a local SQLite history; photo and video
bytes are never persisted by these commands. All user-visible output is
English-only, matching the mobile Live app.

Usage examples::

    python -m tennis360.cli analyze serve1.mp4 serve2.mp4 --action serve
    python -m tennis360.cli analyze forehand1.mp4 --action forehand --arm right
    python -m tennis360.cli analyze backhand1.mp4 --action backhand-two
    python -m tennis360.cli analyze slice1.mp4 --action backhand-slice
    python -m tennis360.cli analyze smash1.mp4 --action overhead
    python -m tennis360.cli analyze volley1.mp4 --action volley-forehand
    python -m tennis360.cli keyframes serve1.mp4 --out keyframes/
    python -m tennis360.cli annotate-video serve1.mp4 --out annotated.mp4
    python -m tennis360.cli multi-angle --side side.mp4 --front front.mp4
    python -m tennis360.cli history --action serve
    python -m tennis360.cli trend --action serve --out trend.png
    python -m tennis360.cli report --out report.xlsx
    python -m tennis360.cli trajectory serve1.mp4 --out traj.png
    python -m tennis360.cli compare --metric elbow_angle_deg --value 96 \
        --reference my_reference.json --action serve
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tennis360.config import Targets, disclaimer, load_targets, write_example_config
from tennis360.history import (
    AnalysisRecord,
    list_records,
    open_db,
    record,
    trend_points,
    utc_now_iso,
)
from tennis360.pose_detector import (
    DEFAULT_TROPHY_MAXIMUM,
    DEFAULT_TROPHY_MINIMUM,
    analyze_rgb_image,
)
from tennis360.reference import compare as compare_reference
from tennis360.reference import load_reference, write_template
from tennis360.reports import export_csv, export_excel, plot_trajectory, plot_trend
from tennis360.strokes import SWING_ACTIONS
from tennis360.video import (
    PHOTO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    analyze_groundstroke,
    analyze_multi_angle,
    analyze_video,
    blur_faces_video,
    extract_keyframes,
    write_annotated_video,
)

ACTION_CHOICES = [
    "serve",
    "forehand",
    "forehand-slice",
    "backhand-two",
    "backhand-one",
    "backhand-slice",
    "volley-forehand",
    "volley-backhand",
    "half-volley",
    "overhead",
    "drop-shot",
    "lob",
]


def _targets_or_defaults(config_path: str | None, action: str):
    try:
        targets: Targets | None = load_targets(config_path)
    except (FileNotFoundError, ValueError, ImportError) as error:
        print(f"Config load failed, using built-in demo values: {error}")
        targets = None
    if targets is not None:
        hit = targets.get(action)
        if hit is not None:
            return hit.minimum_deg, hit.maximum_deg, hit.source, targets
    return DEFAULT_TROPHY_MINIMUM, DEFAULT_TROPHY_MAXIMUM, "demo", targets


def _issue_text(report) -> str:
    if report.status != "analyzed":
        return "Cannot Analyze"
    if report.in_demo_range:
        return "Angle in Range"
    return "Elbow Angle Outside Demo Range"


def cmd_analyze(args: argparse.Namespace) -> int:
    """Batch-analyze photos and videos, storing results in local history."""

    demo_min, demo_max, source, targets = _targets_or_defaults(args.config, args.action)
    print(
        f"Target Range: {demo_min:.0f}°–{demo_max:.0f}° ({disclaimer(source)}). "
        f"Action: {args.action}."
    )

    db = open_db(args.db)
    analyzed = 0
    for raw in args.inputs:
        path = Path(raw)
        suffix = path.suffix.lower()
        if suffix in PHOTO_EXTENSIONS:
            analyzed += _analyze_photo(db, path, args, demo_min, demo_max, source)
        elif suffix in VIDEO_EXTENSIONS:
            if args.action in SWING_ACTIONS:
                analyzed += _analyze_groundstroke_video(
                    db, path, args, demo_min, demo_max, source, targets
                )
            else:
                analyzed += _analyze_video_file(db, path, args, demo_min, demo_max, source)
        else:
            print(f"Skipped unsupported file: {path}")
    print(f"Done: {analyzed} results stored in local history.")
    return 0


def _photo_arm(args) -> str:
    """Right-handed default for swing photos, matching the Live app."""

    if args.action in SWING_ACTIONS and args.arm == "auto":
        return "right"
    return args.arm


def _analyze_photo(db, path: Path, args, demo_min, demo_max, source) -> int:
    from tennis360.image_input import decode_uploaded_image

    try:
        image_rgb = decode_uploaded_image(path.read_bytes())
        _, report = analyze_rgb_image(
            image_rgb,
            _photo_arm(args),
            demo_minimum=demo_min,
            demo_maximum=demo_max,
        )
    except Exception as error:
        print(f"Failed: {path} ({error})")
        return 0
    message = report.message
    if args.action in SWING_ACTIONS:
        message = message.replace("trophy-position", f"{args.action} contact")
    issue = _issue_text(report)
    record(
        db,
        AnalysisRecord(
            recorded_at=utc_now_iso(),
            source_file=str(path),
            action=args.action,
            camera_angle=args.angle,
            arm=report.arm or args.arm,
            angle_deg=report.angle_degrees,
            in_range=report.in_demo_range,
            confidence=report.confidence or "",
            spread_deg=report.spread_degrees,
            main_issue_en=issue,
            target_source=source,
        ),
    )
    _print_report_line(path, report, message)
    return 1


def _analyze_video_file(db, path: Path, args, demo_min, demo_max, source) -> int:
    try:
        analysis = analyze_video(path, arm=args.arm)
    except Exception as error:
        print(f"Failed: {path} ({error})")
        return 0
    if analysis.best_trophy_index is None:
        print(f"No Trophy Segment Found: {path}")
        record(
            db,
            AnalysisRecord(
                recorded_at=utc_now_iso(),
                source_file=str(path),
                action=args.action,
                camera_angle=args.angle,
                arm=args.arm,
                main_issue_en="No Trophy Segment Found",
                target_source=source,
            ),
        )
        return 1
    frame = analysis.frames[analysis.best_trophy_index]
    in_range = frame.angle_3d is not None and demo_min <= frame.angle_3d <= demo_max
    if frame.angle_3d is not None and frame.angle_3d < demo_min:
        issue = "Elbow Over-Bent"
    elif frame.angle_3d is not None and frame.angle_3d > demo_max:
        issue = "Elbow Over-Extended"
    else:
        issue = "Angle in Range"
    record(
        db,
        AnalysisRecord(
            recorded_at=utc_now_iso(),
            source_file=str(path),
            action=args.action,
            camera_angle=args.angle,
            arm=frame.arm or args.arm,
            angle_deg=round(frame.angle_3d, 1) if frame.angle_3d else None,
            in_range=in_range,
            main_issue_en=issue,
            target_source=source,
        ),
    )
    angle_text = f"{frame.angle_3d:.0f}°" if frame.angle_3d else "n/a"
    verdict = "OK" if in_range else "CHECK"
    print(
        f"[{verdict}] {path.name}: Best Trophy Frame {frame.time_s:.2f} s, "
        f"Elbow {angle_text} ({issue})"
    )
    return 1


def _analyze_groundstroke_video(
    db, path: Path, args, demo_min, demo_max, source, targets
) -> int:
    try:
        targets_obj = targets if targets is not None else load_targets(args.config)
    except (FileNotFoundError, ValueError, ImportError):
        targets_obj = None
    try:
        analysis = analyze_groundstroke(
            path, action=args.action, arm=args.arm, targets=targets_obj
        )
    except Exception as error:
        print(f"Failed: {path} ({error})")
        return 0

    if analysis.moments is None or analysis.metrics is None:
        print(f"No Clear Swing Found: {path}")
        record(
            db,
            AnalysisRecord(
                recorded_at=utc_now_iso(),
                source_file=str(path),
                action=args.action,
                camera_angle=args.angle,
                arm=args.arm,
                main_issue_en="; ".join(analysis.suggestions) or "No Clear Swing Found",
                target_source=source,
            ),
        )
        return 1

    moments = analysis.moments
    metrics = analysis.metrics
    issue = "; ".join(analysis.suggestions[:2]) if analysis.suggestions else "Angle in Range"
    record(
        db,
        AnalysisRecord(
            recorded_at=utc_now_iso(),
            source_file=str(path),
            action=args.action,
            camera_angle=args.angle,
            arm=analysis.arm or args.arm,
            angle_deg=round(metrics.contact_elbow_deg, 1)
            if metrics.contact_elbow_deg
            else None,
            in_range=metrics.contact_elbow_in_range,
            main_issue_en=issue,
            target_source=source,
        ),
    )

    frames = analysis.sample_times
    print(f"[{args.action}] {path.name}:")
    for label, position in (
        ("Backswing", moments.backswing),
        ("Contact", moments.contact),
        ("Follow-Through", moments.followthrough),
    ):
        time_s = frames[position] if position < len(frames) else 0.0
        print(f"  {label}: {time_s:.2f} s (Estimated Key Moment)")
    for suggestion in analysis.suggestions:
        print(f"  - {suggestion}")
    return 1


def _print_report_line(path: Path, report, message: str) -> None:
    if report.status != "analyzed":
        print(f"Warning: {path.name} — Cannot Analyze: {message}")
        return
    verdict = "OK" if report.in_demo_range else "CHECK"
    print(f"[{verdict}] {path.name}: Elbow {report.angle_degrees:.0f}° ({message})")


def cmd_history(args: argparse.Namespace) -> int:
    db = open_db(args.db)
    rows = list_records(db, action=args.action, limit=args.limit)
    if not rows:
        print("No local history yet.")
        return 0
    for row in rows:
        angle = f"{row['angle_deg']:.0f}°" if row["angle_deg"] is not None else "n/a"
        mark = {1: "OK", 0: "CHECK"}.get(row["in_range"], "WARN")
        print(
            f"{row['recorded_at']}  {mark} {row['action']} {angle}  "
            f"{row['source_file']}  {row['main_issue_en']}"
        )
    return 0


def cmd_trend(args: argparse.Namespace) -> int:
    db = open_db(args.db)
    points = trend_points(db, args.action)
    demo_min, demo_max, source, _ = _targets_or_defaults(args.config, args.action)
    destination = plot_trend(
        points,
        args.out,
        target_min=demo_min,
        target_max=demo_max,
        action_label=args.action,
        target_source=source,
    )
    print(f"Trend chart written: {destination} ({len(points)} records)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    db = open_db(args.db)
    rows = list_records(db, action=args.action, limit=args.limit)
    mappings = [dict(row) for row in rows]
    suffix = Path(args.out).suffix.lower()
    if suffix == ".csv":
        destination = export_csv(mappings, args.out)
    else:
        destination = export_excel(mappings, args.out)
    print(f"Report written: {destination} ({len(mappings)} records)")
    return 0


def cmd_trajectory(args: argparse.Namespace) -> int:
    analysis = analyze_video(args.video, arm=args.arm)
    points = [
        (frame.time_s, frame.wrist_world)
        for frame in analysis.frames
        if frame.wrist_world is not None
    ]
    if len(points) < 2:
        print("Not enough trajectory points.")
        return 1
    destination = plot_trajectory(points, args.out, three_d=args.three_d)
    print(f"Trajectory written: {destination} ({len(points)} points)")
    return 0


def cmd_annotate_video(args: argparse.Namespace) -> int:
    destination = write_annotated_video(args.video, args.out, arm=args.arm)
    print(f"Annotated video written: {destination}")
    return 0


def cmd_anonymize(args: argparse.Namespace) -> int:
    destination = blur_faces_video(args.video, args.out)
    print(f"Anonymized video written: {destination}")
    return 0


def cmd_keyframes(args: argparse.Namespace) -> int:
    analysis = analyze_video(args.video, arm=args.arm)
    saved = extract_keyframes(analysis, args.out)
    if not saved:
        print("No keyframes extracted.")
        return 1
    for name, location in saved.items():
        print(f"Keyframe: {location}")
    return 0


def cmd_multi_angle(args: argparse.Namespace) -> int:
    fused = analyze_multi_angle(args.side, args.front, arm=args.arm)
    side = fused.side
    print("[Side View]")
    if side.best_trophy_index is not None:
        frame = side.frames[side.best_trophy_index]
        angle_text = f"{frame.angle_3d:.0f}°" if frame.angle_3d else "n/a"
        print(f"  Trophy Frame: {frame.time_s:.2f} s, Elbow Angle: {angle_text}")
    else:
        print("  No Trophy Segment Found.")
    front = fused.front
    print("[Front View]")
    toss = f"{front.max_toss_wrist_rise:.2f}" if front.max_toss_wrist_rise is not None else "n/a"
    turn = f"{front.shoulder_turn_amplitude_deg:.0f}°" if front.shoulder_turn_amplitude_deg is not None else "n/a"
    print(f"  Max Toss Wrist Rise: {toss} Body Scales")
    print(f"  Shoulder Turn Amplitude: {turn} (Estimated from the 2D Image)")

    db = open_db(args.db)
    if side.best_trophy_index is not None:
        frame = side.frames[side.best_trophy_index]
        record(
            db,
            AnalysisRecord(
                recorded_at=utc_now_iso(),
                source_file=f"{args.side}+{args.front}",
                action=args.action,
                camera_angle="side+front",
                arm=frame.arm or args.arm,
                angle_deg=round(frame.angle_3d, 1) if frame.angle_3d else None,
                main_issue_en="Multi-Angle Fused Analysis",
            ),
        )
        print("Stored in local history.")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    references = load_reference(args.reference)
    results = compare_reference({args.metric: args.value}, references, args.action)
    if not results:
        print("No matching reference entry. Check the action and metric names.")
        return 1
    for item in results:
        print(
            f"[{item.action}/{item.metric}] measured {item.measured:.1f} vs "
            f"reference {item.reference:.1f} (delta {item.delta:+.1f}; "
            f"source: {item.reference_source})"
        )
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    targets = load_targets(args.config)
    for name, target in targets.ranges.items():
        print(f"{name}: {target.minimum_deg:.0f}°–{target.maximum_deg:.0f}° [{disclaimer(target.source)}]")
    extras = targets.extras.get("groundstroke_extras", {})
    if extras:
        print("groundstroke_extras:")
        for key, value in extras.items():
            if key != "source":
                print(f"  {key}: {value}")
    return 0


def cmd_config_init(args: argparse.Namespace) -> int:
    destination = write_example_config(args.out)
    print(
        f"Example config written: {destination}. Edit the values with a text "
        f"editor and set source to coach."
    )
    return 0


def cmd_reference_template(args: argparse.Namespace) -> int:
    destination = write_template(args.out)
    print(
        f"Reference template written: {destination}. Fill in your own reference "
        f"data (e.g. coach-measured values); no professional-player data is included."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tennis360",
        description="Tennis360 desktop deep analysis (local only). Output is English-only.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=None, help="History database path")
    common.add_argument("--config", default=None, help="Target ranges YAML file")

    analyze = sub.add_parser("analyze", parents=[common], help="Batch-analyze photos/videos")
    analyze.add_argument("inputs", nargs="+", help="Photo or video paths")
    analyze.add_argument("--action", default="serve", choices=ACTION_CHOICES)
    analyze.add_argument("--arm", default="auto", choices=["auto", "left", "right"])
    analyze.add_argument("--angle", default="", help="Camera angle tag (side/front)")
    analyze.set_defaults(func=cmd_analyze)

    history = sub.add_parser("history", parents=[common], help="List local history")
    history.add_argument("--action", default=None)
    history.add_argument("--limit", type=int, default=50)
    history.set_defaults(func=cmd_history)

    trend = sub.add_parser("trend", parents=[common], help="Plot angle trend chart")
    trend.add_argument("--action", default="serve")
    trend.add_argument("--out", default="trend.png")
    trend.set_defaults(func=cmd_trend)

    report = sub.add_parser("report", parents=[common], help="Export Excel/CSV report")
    report.add_argument("--action", default=None)
    report.add_argument("--limit", type=int, default=500)
    report.add_argument("--out", default="report.xlsx")
    report.set_defaults(func=cmd_report)

    trajectory = sub.add_parser("trajectory", help="Plot wrist trajectory")
    trajectory.add_argument("video", help="Video path")
    trajectory.add_argument("--arm", default="auto", choices=["auto", "left", "right"])
    trajectory.add_argument("--out", default="trajectory.png")
    trajectory.add_argument("--three-d", action="store_true", help="3D plot")
    trajectory.set_defaults(func=cmd_trajectory)

    annotate = sub.add_parser("annotate-video", help="Write skeleton-annotated video")
    annotate.add_argument("video", help="Video path")
    annotate.add_argument("--out", default="annotated.mp4")
    annotate.add_argument("--arm", default="auto", choices=["auto", "left", "right"])
    annotate.set_defaults(func=cmd_annotate_video)

    anonymize = sub.add_parser("anonymize", help="Blur faces for privacy")
    anonymize.add_argument("video", help="Video path")
    anonymize.add_argument("--out", default="anonymized.mp4")
    anonymize.set_defaults(func=cmd_anonymize)

    keyframes = sub.add_parser("keyframes", help="Extract keyframes automatically")
    keyframes.add_argument("video", help="Video path")
    keyframes.add_argument("--out", default="keyframes")
    keyframes.add_argument("--arm", default="auto", choices=["auto", "left", "right"])
    keyframes.set_defaults(func=cmd_keyframes)

    multi = sub.add_parser("multi-angle", parents=[common], help="Side+front fused analysis")
    multi.add_argument("--side", required=True, help="Side-view video")
    multi.add_argument("--front", required=True, help="Front-view video")
    multi.add_argument("--action", default="serve")
    multi.add_argument("--arm", default="auto", choices=["auto", "left", "right"])
    multi.set_defaults(func=cmd_multi_angle)

    compare = sub.add_parser("compare", help="Compare against reference data")
    compare.add_argument("--action", default="serve")
    compare.add_argument("--metric", default="elbow_angle_deg")
    compare.add_argument("--value", type=float, required=True)
    compare.add_argument("--reference", required=True, help="Reference data JSON")
    compare.set_defaults(func=cmd_compare)

    config_show = sub.add_parser("config-show", help="Show current target ranges")
    config_show.add_argument("--config", default=None)
    config_show.set_defaults(func=cmd_config_show)

    config_init = sub.add_parser("config-init", help="Write an editable example config")
    config_init.add_argument("--out", default="my_targets.yaml")
    config_init.set_defaults(func=cmd_config_init)

    ref_template = sub.add_parser("reference-template", help="Write a reference data template")
    ref_template.add_argument("--out", default="my_reference.json")
    ref_template.set_defaults(func=cmd_reference_template)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
