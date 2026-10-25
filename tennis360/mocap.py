"""Offline BVH geometry for licensed motion-capture evaluation, not app uploads.

Coordinates retain the source file's units and axes. BVH channel transforms are
post-multiplied in declared order: Zrotation Xrotation Yrotation means Rz @ Rx
@ Ry. A joint's offset is translated before its own channels are applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, isfinite
from pathlib import Path
import re

import numpy as np

from tennis360.pose_math import Point3, calculate_elbow_angle_3d


class BVHError(ValueError):
    """The BVH hierarchy, motion rows, or derived coordinates are invalid."""


@dataclass(frozen=True)
class Joint:
    name: str
    parent: int | None
    offset: tuple[float, float, float]
    channels: tuple[str, ...]
    channel_start: int
    end_site: bool = False


@dataclass(frozen=True)
class Motion:
    joints: tuple[Joint, ...]
    frames: np.ndarray
    frame_time: float

    @property
    def frame_count(self) -> int:
        return len(self.frames)


@dataclass(frozen=True)
class AngleReading:
    frame: int  # Zero-based, matching timestamp = frame * frame_time.
    time_seconds: float
    arm: str
    angle_degrees: float
    independent_degrees: float
    difference_degrees: float


_CHANNELS = frozenset(
    axis + kind for axis in "XYZ" for kind in ("position", "rotation")
)
ARM_JOINTS = {
    "left": ("LeftShoulder", "LeftElbow", "LeftWrist"),
    "right": ("RightShoulder", "RightElbow", "RightWrist"),
}


def parse_bvh(text: str) -> Motion:
    """Parse a single-root BVH, rejecting ambiguous or non-finite data.

    Motion requires one complete channel row per frame. End sites have no
    channels and receive the explicit synthetic name ``Parent:EndSite``.
    """
    parts = re.split(r"(?m)^\s*MOTION\s*$", text)
    if len(parts) != 2:
        raise BVHError("Expected exactly one MOTION section")
    tokens = re.findall(r"\{|\}|[^\s{}]+", parts[0])
    cursor = 0
    joints: list[Joint] = []
    names: set[str] = set()
    channel_count = 0

    def take(expected: str | None = None) -> str:
        nonlocal cursor
        if cursor >= len(tokens):
            raise BVHError("Unexpected end of hierarchy")
        token = tokens[cursor]
        cursor += 1
        if expected is not None and token != expected:
            raise BVHError(f"Expected {expected}, received {token}")
        return token

    def number() -> float:
        try:
            value = float(take())
        except ValueError as error:
            raise BVHError("Invalid hierarchy number") from error
        if not isfinite(value):
            raise BVHError("Non-finite hierarchy number")
        return value

    def joint(parent: int | None, kind: str) -> None:
        nonlocal channel_count
        if kind == "End":
            take("Site")
            assert parent is not None
            name = joints[parent].name + ":EndSite"
        else:
            name = take()
            if name in ("{", "}"):
                raise BVHError("Invalid joint name")
        if name in names:
            raise BVHError(f"Duplicate joint or end-site name: {name}")
        names.add(name)
        take("{")
        take("OFFSET")
        offset = (number(), number(), number())
        channels: tuple[str, ...] = ()
        if kind != "End":
            take("CHANNELS")
            count_token = take()
            if not re.fullmatch(r"[0-6]", count_token):
                raise BVHError("CHANNELS must be an integer from 0 to 6")
            channels = tuple(take() for _ in range(int(count_token)))
            if len(set(channels)) != len(channels) or not set(channels) <= _CHANNELS:
                raise BVHError(f"Invalid or duplicate channels for {name}")
        index = len(joints)
        joints.append(Joint(name, parent, offset, channels, channel_count, kind == "End"))
        channel_count += len(channels)
        while True:
            child_kind = take()
            if child_kind == "}":
                break
            if kind == "End" or child_kind not in ("JOINT", "End"):
                raise BVHError(f"Unexpected hierarchy entry: {child_kind}")
            joint(index, child_kind)

    take("HIERARCHY")
    take("ROOT")
    try:
        joint(None, "ROOT")
    except RecursionError as error:
        raise BVHError("Hierarchy nesting is too deep") from error
    if cursor != len(tokens) or channel_count == 0:
        raise BVHError("Unexpected hierarchy content or no motion channels")

    rows = [line.strip() for line in parts[1].splitlines() if line.strip()]
    if len(rows) < 2:
        raise BVHError("Missing motion headers")
    count_match = re.fullmatch(r"Frames:\s*(\d+)", rows[0])
    time_match = re.fullmatch(r"Frame\s+Time:\s*(\S+)", rows[1])
    if count_match is None or time_match is None:
        raise BVHError("Invalid motion headers")
    frame_count = int(count_match[1])
    try:
        frame_time = float(time_match[1])
    except ValueError as error:
        raise BVHError("Invalid frame time") from error
    if frame_count < 1 or not isfinite(frame_time) or frame_time <= 0:
        raise BVHError("Frame count and finite frame time must be positive")
    if not isfinite((frame_count - 1) * frame_time):
        raise BVHError("Derived frame timestamps must be finite")
    if len(rows) - 2 != frame_count:
        raise BVHError("Declared frame count does not match motion rows")
    frames = np.empty((frame_count, channel_count), dtype=np.float64)
    for index, row in enumerate(rows[2:]):
        values = row.split()
        if len(values) != channel_count:
            raise BVHError(f"Frame {index} does not match declared channel count")
        try:
            frames[index] = [float(value) for value in values]
        except ValueError as error:
            raise BVHError(f"Frame {index} contains an invalid number") from error
    if not np.isfinite(frames).all():
        raise BVHError("Motion contains non-finite values")
    frames.setflags(write=False)
    return Motion(tuple(joints), frames, frame_time)


def load_bvh(path: str | Path) -> Motion:
    return parse_bvh(Path(path).read_text(encoding="utf-8-sig"))


def joint_positions(motion: Motion) -> dict[str, np.ndarray]:
    """Return each named joint's (frame, xyz) positions in unscaled source units.

    All channel transforms, including interleaved position channels, follow
    their declared order. End-site offsets inherit the parent's rotation.
    """
    positions: list[np.ndarray] = []
    rotations: list[np.ndarray] = []
    identity = np.broadcast_to(np.eye(3), (motion.frame_count, 3, 3))
    with np.errstate(over="ignore", invalid="ignore"):
        for joint in motion.joints:
            local_rotation = identity.copy()
            local_position = np.broadcast_to(joint.offset, (motion.frame_count, 3)).copy()
            for offset, channel in enumerate(joint.channels):
                axis = "XYZ".index(channel[0])
                values = motion.frames[:, joint.channel_start + offset]
                if channel.endswith("position"):
                    local_position += local_rotation[:, :, axis] * values[:, None]
                else:
                    radians = np.deg2rad(values)
                    sine, cosine = np.sin(radians), np.cos(radians)
                    first, second = (axis + 1) % 3, (axis + 2) % 3
                    rotation = identity.copy()
                    rotation[:, first, first] = cosine
                    rotation[:, second, second] = cosine
                    rotation[:, first, second] = -sine
                    rotation[:, second, first] = sine
                    local_rotation = local_rotation @ rotation
            if joint.parent is None:
                world_position, world_rotation = local_position, local_rotation
            else:
                parent_rotation = rotations[joint.parent]
                world_position = positions[joint.parent] + np.einsum(
                    "nij,nj->ni", parent_rotation, local_position
                )
                world_rotation = parent_rotation @ local_rotation
            if not np.isfinite(world_position).all() or not np.isfinite(world_rotation).all():
                raise BVHError(f"Non-finite derived coordinates for {joint.name}")
            positions.append(world_position)
            rotations.append(world_rotation)
    return {joint.name: position for joint, position in zip(motion.joints, positions)}


def independent_angle(shoulder: np.ndarray, elbow: np.ndarray, wrist: np.ndarray) -> float | None:
    """An independent atan2/cross-product oracle using normalized vectors."""
    first, second = shoulder - elbow, wrist - elbow
    first_length, second_length = np.hypot.reduce(first), np.hypot.reduce(second)
    if not all(isfinite(value) and value >= 1e-9 for value in (first_length, second_length)):
        return None
    first, second = first / first_length, second / second_length
    angle = degrees(atan2(float(np.linalg.norm(np.cross(first, second))), float(np.dot(first, second))))
    return angle if isfinite(angle) else None


def evaluate_angles(motion: Motion) -> tuple[list[AngleReading], dict[str, int]]:
    """Compare both arms' interior angles on every frame; exclude invalid geometry.

    The Shoulder joint is used, never Collar. Point3 is only a geometry adapter:
    there is no inference that the source coordinates are meters. No Trophy Pose
    timestamp, correct/incorrect label, app verdict, or calibrated accuracy is
    produced from these framewise measurements.
    """
    positions = joint_positions(motion)
    readings: list[AngleReading] = []
    excluded = {arm: 0 for arm in ARM_JOINTS}
    for arm, names in ARM_JOINTS.items():
        if any(name not in positions for name in names):
            excluded[arm] = motion.frame_count
            continue
        for frame in range(motion.frame_count):
            points = [positions[name][frame] for name in names]
            angle = calculate_elbow_angle_3d(*(Point3(*point) for point in points))
            oracle = independent_angle(*points)
            if angle is None or oracle is None:
                excluded[arm] += 1
                continue
            readings.append(AngleReading(frame, frame * motion.frame_time, arm, angle, oracle, abs(angle - oracle)))
    return readings, excluded
