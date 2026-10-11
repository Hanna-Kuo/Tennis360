"""Drawing helpers that turn one analysis into a legible annotated photo.

All drawing happens in BGR because OpenCV owns the canvas; the caller converts
back to RGB once, at the end of the pipeline.
"""

from __future__ import annotations

from math import atan2, degrees
from typing import Sequence

import cv2
import numpy as np

from tennispose.pose_math import Point, has_reliable_point


GREEN = (96, 174, 39)
RED = (55, 76, 232)
AMBER = (0, 165, 255)
NAVY = (55, 41, 31)
WHITE = (255, 255, 255)
GUIDE = (188, 178, 168)

FONT = cv2.FONT_HERSHEY_DUPLEX

# MediaPipe Pose landmark connections, grouped so the face mesh stays sparse.
POSE_CONNECTIONS = (
    (0, 2), (0, 5), (2, 7), (5, 8), (9, 10),
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24), (23, 25), (24, 26),
    (25, 27), (26, 28), (27, 31), (28, 32),
)


def reference_scale(image_bgr: np.ndarray) -> float:
    """Return a drawing scale so annotations read the same on any photo size."""

    height, width = image_bgr.shape[:2]
    return max(0.6, min(2.4, max(width, height) / 900))


def pixel_point(point: Point, width: int, height: int) -> tuple[int, int]:
    """Convert one normalized landmark to integer pixel coordinates."""

    return (round(point.x * width), round(point.y * height))


def draw_skeleton(image_bgr: np.ndarray, landmarks: Sequence[Point]) -> None:
    """Draw the whole detected body faintly, as context for the measured arm."""

    height, width = image_bgr.shape[:2]
    scale = reference_scale(image_bgr)
    thickness = max(1, round(2 * scale))

    for start, end in POSE_CONNECTIONS:
        if start >= len(landmarks) or end >= len(landmarks):
            continue
        first, second = landmarks[start], landmarks[end]
        if not has_reliable_point(first, 0.2) or not has_reliable_point(second, 0.2):
            continue
        cv2.line(
            image_bgr,
            pixel_point(first, width, height),
            pixel_point(second, width, height),
            GUIDE,
            thickness,
            cv2.LINE_AA,
        )

    for landmark in landmarks:
        if has_reliable_point(landmark, 0.2):
            cv2.circle(
                image_bgr,
                pixel_point(landmark, width, height),
                max(2, round(3 * scale)),
                WHITE,
                -1,
                cv2.LINE_AA,
            )


def draw_measured_arm(
    image_bgr: np.ndarray,
    shoulder: Point,
    elbow: Point,
    wrist: Point,
    color: tuple[int, int, int],
    angle_degrees: float,
) -> None:
    """Highlight the measured arm and label the elbow angle at the joint."""

    height, width = image_bgr.shape[:2]
    scale = reference_scale(image_bgr)
    points = [pixel_point(point, width, height) for point in (shoulder, elbow, wrist)]

    for start, end in ((points[0], points[1]), (points[1], points[2])):
        cv2.line(image_bgr, start, end, NAVY, max(3, round(9 * scale)), cv2.LINE_AA)
        cv2.line(image_bgr, start, end, color, max(2, round(5 * scale)), cv2.LINE_AA)

    _draw_angle_arc(image_bgr, points[1], points[0], points[2], color, scale)

    for index, point in enumerate(points):
        radius = max(4, round((10 if index == 1 else 7) * scale))
        cv2.circle(image_bgr, point, radius + max(1, round(2 * scale)), NAVY, -1, cv2.LINE_AA)
        cv2.circle(image_bgr, point, radius, WHITE, -1, cv2.LINE_AA)
        cv2.circle(image_bgr, point, radius, color, max(2, round(3 * scale)), cv2.LINE_AA)

    _draw_angle_label(image_bgr, points[1], f"{angle_degrees:.0f}", color, scale)


def _draw_angle_arc(
    image_bgr: np.ndarray,
    elbow: tuple[int, int],
    shoulder: tuple[int, int],
    wrist: tuple[int, int],
    color: tuple[int, int, int],
    scale: float,
) -> None:
    """Sweep an arc inside the elbow so the measured angle is visible, not implied."""

    radius = round(max(16.0, 26 * scale))
    start = degrees(atan2(shoulder[1] - elbow[1], shoulder[0] - elbow[0]))
    end = degrees(atan2(wrist[1] - elbow[1], wrist[0] - elbow[0]))
    sweep = (end - start + 180) % 360 - 180
    cv2.ellipse(
        image_bgr,
        elbow,
        (radius, radius),
        0.0,
        start,
        start + sweep,
        color,
        max(2, round(3 * scale)),
        cv2.LINE_AA,
    )


def _draw_angle_label(
    image_bgr: np.ndarray,
    elbow: tuple[int, int],
    text: str,
    color: tuple[int, int, int],
    scale: float,
) -> None:
    """Place the degree reading next to the elbow, kept inside the frame."""

    height, width = image_bgr.shape[:2]
    font_scale = 0.7 * scale
    thickness = max(1, round(1.6 * scale))
    label = f"{text} deg"
    (text_width, text_height), baseline = cv2.getTextSize(label, FONT, font_scale, thickness)
    padding = max(4, round(8 * scale))

    left = min(max(padding, elbow[0] + round(30 * scale)), width - text_width - padding * 3)
    top = min(max(padding, elbow[1] - round(30 * scale)), height - text_height - padding * 3)
    box_end = (left + text_width + padding * 2, top + text_height + baseline + padding * 2)

    cv2.rectangle(image_bgr, (left, top), box_end, NAVY, -1)
    cv2.rectangle(image_bgr, (left, top), box_end, color, max(2, round(2 * scale)))
    cv2.putText(
        image_bgr,
        label,
        (left + padding, top + text_height + padding),
        FONT,
        font_scale,
        WHITE,
        thickness,
        cv2.LINE_AA,
    )


def draw_banner(
    image_bgr: np.ndarray,
    headline: str,
    detail_lines: Sequence[str],
    color: tuple[int, int, int],
) -> None:
    """Draw the result header so the annotated photo explains itself on its own."""

    width = image_bgr.shape[1]
    scale = reference_scale(image_bgr)
    padding = max(8, round(14 * scale))
    headline_scale = 0.82 * scale
    detail_scale = 0.55 * scale
    headline_thickness = max(1, round(2 * scale))
    detail_thickness = max(1, round(1.2 * scale))

    available = width - padding * 2
    wrapped: list[str] = []
    for line in detail_lines:
        wrapped.extend(_wrap_line(line, available, detail_scale, detail_thickness))

    headline_height = cv2.getTextSize(headline, FONT, headline_scale, headline_thickness)[0][1]
    detail_height = round(cv2.getTextSize("Ag", FONT, detail_scale, detail_thickness)[0][1] * 2.0)
    banner_height = padding * 2 + headline_height + detail_height * len(wrapped)
    accent = max(4, round(7 * scale))

    overlay = image_bgr.copy()
    cv2.rectangle(overlay, (0, 0), (width, banner_height + accent), NAVY, -1)
    cv2.addWeighted(overlay, 0.88, image_bgr, 0.12, 0, image_bgr)

    cursor = padding + headline_height
    cv2.putText(
        image_bgr,
        _fit_line(headline, available, headline_scale, headline_thickness),
        (padding, cursor),
        FONT,
        headline_scale,
        color,
        headline_thickness,
        cv2.LINE_AA,
    )
    for line in wrapped:
        cursor += detail_height
        cv2.putText(
            image_bgr,
            line,
            (padding, cursor),
            FONT,
            detail_scale,
            WHITE,
            detail_thickness,
            cv2.LINE_AA,
        )

    cv2.rectangle(
        image_bgr,
        (0, banner_height),
        (width, banner_height + accent),
        color,
        -1,
    )


def _wrap_line(
    line: str,
    available_width: int,
    font_scale: float,
    thickness: int,
    *,
    maximum_lines: int = 4,
) -> list[str]:
    """Break one sentence across banner rows so a full explanation stays readable."""

    def width_of(text: str) -> int:
        return cv2.getTextSize(text, FONT, font_scale, thickness)[0][0]

    if width_of(line) <= available_width:
        return [line]

    rows: list[str] = []
    current = ""
    for word in line.split():
        candidate = f"{current} {word}".strip()
        if current and width_of(candidate) > available_width:
            rows.append(current)
            current = word
            if len(rows) == maximum_lines - 1:
                break
        else:
            current = candidate

    remaining = line.split()[sum(len(row.split()) for row in rows):]
    current = " ".join(remaining)
    rows.append(_fit_line(current, available_width, font_scale, thickness))
    return rows


def _fit_line(line: str, available_width: int, font_scale: float, thickness: int) -> str:
    """Shorten a line with an ellipsis so a narrow photo stays readable."""

    if cv2.getTextSize(line, FONT, font_scale, thickness)[0][0] <= available_width:
        return line
    shortened = line
    while len(shortened) > 4:
        shortened = shortened[:-1]
        candidate = f"{shortened}..."
        if cv2.getTextSize(candidate, FONT, font_scale, thickness)[0][0] <= available_width:
            return candidate
    return "..."
