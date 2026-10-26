"""Best-effort capture-time extraction from uploaded media.

A history record's time point is the moment its source photo or
video was RECORDED when the file carries that information, and the
moment the analysis was saved otherwise (see history.effective_time).
This module reads the recording time out of the media file itself —
never the filesystem modification time, which says when a file was
copied, not when it was recorded:

- Videos (MP4 / MOV / M4V): the ISO-BMFF movie header (mvhd)
  creation time, and the textual creation date phones embed —
  ``com.apple.quicktime.creationdate`` in the meta box, or a ©day
  atom in udta. The textual tag wins when both exist: it carries an
  explicit UTC offset, while mvhd is UTC by specification. Parsing
  is pure Python over the file bytes; no OpenCV is involved, so the
  extractor is testable anywhere.
- Photos (JPEG / PNG / HEIC): the EXIF DateTimeOriginal, with its
  OffsetTimeOriginal when present, read with Pillow. An EXIF time
  without an offset is the camera's wall-clock time; it is read as
  the local time of the computer running the app (normally where
  the photo was taken) and converted to UTC.

Everything is best-effort: a file whose metadata is absent or does
not parse yields None, and callers fall back to the save time. A
guessed or filesystem-derived time is never returned.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Callable

try:  # iPhone photos default to HEIC; pillow-heif lets PIL read them.
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover - pillow-heif is in requirements.txt
    pass

# ISO-BMFF timestamps count seconds from 1904-01-01 (Mac epoch).
_MAC_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)

_QUICKTIME_CREATION_KEY = "com.apple.quicktime.creationdate"

ReadAt = Callable[[int, int], bytes]


def to_utc_iso(moment: datetime) -> str:
    """Format an aware datetime as an ISO 8601 UTC timestamp."""

    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def offset_timestamp(base_iso: str | None, offset_s: float | None) -> str | None:
    """Shift an ISO timestamp by ``offset_s`` seconds, or None.

    Used to place one stroke of a multi-stroke video: the stroke's
    capture instant is the video's recording start plus the stroke's
    own time in the video. Returns None when there is no base time.
    """

    if not base_iso:
        return None
    try:
        base = datetime.fromisoformat(base_iso)
    except ValueError:
        return None
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    shift = float(offset_s) if offset_s else 0.0
    return to_utc_iso(base + timedelta(seconds=shift))


# --- ISO-BMFF (MP4 / MOV / M4V) -------------------------------------------------


def _iter_boxes(read: ReadAt, start: int, end: int):
    """Yield (type, content_start, content_end) for boxes in a range.

    Box headers are a 32-bit size plus a 4-byte type; a size of 1
    means a 64-bit largesize follows, and a size of 0 means the box
    runs to the end of its container. Malformed sizes simply end the
    iteration — the caller treats missing boxes as missing metadata.
    """

    position = start
    while position + 8 <= end:
        header = read(position, 16)
        if len(header) < 8:
            return
        size = int.from_bytes(header[0:4], "big")
        header_size = 8
        if size == 1:
            if len(header) < 16:
                return
            size = int.from_bytes(header[8:16], "big")
            header_size = 16
        elif size == 0:
            size = end - position
        if size < header_size or position + size > end:
            return
        yield header[4:8], position + header_size, position + size
        position += size


def _find_box(read: ReadAt, start: int, end: int, wanted: bytes):
    """Return the content range of the first box of a type, or None."""

    for box_type, content_start, content_end in _iter_boxes(read, start, end):
        if box_type == wanted:
            return content_start, content_end
    return None


def _mvhd_creation_time(read: ReadAt, start: int, end: int) -> datetime | None:
    """Read the mvhd creation time (UTC per the specification)."""

    data = read(start, min(end - start, 32))
    if len(data) < 8:
        return None
    if data[0] == 1:  # version 1: 64-bit creation time
        if len(data) < 12:
            return None
        raw = int.from_bytes(data[4:12], "big")
    else:
        raw = int.from_bytes(data[4:8], "big")
    if raw == 0:
        return None
    try:
        return _MAC_EPOCH + timedelta(seconds=raw)
    except OverflowError:
        return None


def _parse_text_datetime(text: str) -> datetime | None:
    """Parse an embedded textual timestamp to an aware UTC datetime.

    A value without an offset is read as UTC: the textual tags this
    reads (QuickTime creation date, ©day) are written either with an
    explicit offset or in UTC.
    """

    cleaned = text.strip().strip("\x00").strip()
    if not cleaned:
        return None
    if cleaned[-1:] in ("Z", "z"):
        cleaned = cleaned[:-1] + "+00:00"
    moment = None
    try:
        moment = datetime.fromisoformat(cleaned)
    except ValueError:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                moment = datetime.strptime(cleaned, pattern)
                break
            except ValueError:
                continue
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _meta_creation_date(read: ReadAt, start: int, end: int) -> datetime | None:
    """Read com.apple.quicktime.creationdate from a meta box.

    The meta box holds a keys box (an ordered list of key names) and
    an ilst box (values addressed by 1-based key index); the value
    lives in a data atom whose first word is the value type (1 is
    UTF-8 text).
    """

    keys: dict[int, str] = {}
    values: dict[int, str] = {}
    # The meta content opens with 4 bytes of version/flags.
    for box_type, box_start, box_end in _iter_boxes(read, start + 4, end):
        if box_type == b"keys":
            data = read(box_start, box_end - box_start)
            if len(data) < 8:
                continue
            count = int.from_bytes(data[4:8], "big")
            position = 8
            for index in range(1, count + 1):
                if position + 8 > len(data):
                    break
                entry_size = int.from_bytes(
                    data[position : position + 4], "big"
                )
                if entry_size < 8 or position + entry_size > len(data):
                    break
                name = data[position + 8 : position + entry_size]
                keys[index] = name.decode("utf-8", errors="replace")
                position += entry_size
        elif box_type == b"ilst":
            for entry_type, entry_start, entry_end in _iter_boxes(
                read, box_start, box_end
            ):
                index = int.from_bytes(entry_type, "big")
                data_box = _find_box(read, entry_start, entry_end, b"data")
                if data_box is None:
                    continue
                data_start, data_end = data_box
                payload = read(data_start, data_end - data_start)
                if len(payload) < 8:
                    continue
                value_type = int.from_bytes(payload[0:4], "big")
                if value_type != 1:  # not UTF-8 text
                    continue
                values[index] = payload[8:].decode(
                    "utf-8", errors="replace"
                )
    for index, name in keys.items():
        if name == _QUICKTIME_CREATION_KEY and index in values:
            parsed = _parse_text_datetime(values[index])
            if parsed is not None:
                return parsed
    return None


def _udta_creation_date(read: ReadAt, start: int, end: int) -> datetime | None:
    """Read a ©day atom inside a udta box, when present."""

    day_box = _find_box(read, start, end, b"\xa9day")
    if day_box is None:
        return None
    day_start, day_end = day_box
    payload = read(day_start, day_end - day_start)
    return _parse_text_datetime(payload.decode("utf-8", errors="replace"))


def _scan_video(read: ReadAt, size: int) -> datetime | None:
    moov = _find_box(read, 0, size, b"moov")
    if moov is None:
        return None
    moov_start, moov_end = moov
    header_time = None
    text_time = None
    day_time = None
    for box_type, box_start, box_end in _iter_boxes(read, moov_start, moov_end):
        if box_type == b"mvhd" and header_time is None:
            header_time = _mvhd_creation_time(read, box_start, box_end)
        elif box_type == b"meta" and text_time is None:
            text_time = _meta_creation_date(read, box_start, box_end)
        elif box_type == b"udta" and day_time is None:
            day_time = _udta_creation_date(read, box_start, box_end)
    # The textual tag carries an explicit offset, so it is the most
    # precise statement of the instant; the header is UTC by spec;
    # ©day is the least structured and the last resort.
    return text_time or header_time or day_time


def video_capture_time(data: bytes) -> datetime | None:
    """Return the recording time embedded in video bytes, or None."""

    if not data:
        return None
    try:
        return _scan_video(lambda offset, count: data[offset : offset + count], len(data))
    except Exception:
        return None


def video_capture_time_from_path(path: str | Path) -> datetime | None:
    """Return the recording time embedded in a video file, or None.

    The box structure is read with seeks, so the file is never loaded
    into memory whole just to find its metadata.
    """

    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()

            def read(offset: int, count: int) -> bytes:
                handle.seek(offset)
                return handle.read(count)

            return _scan_video(read, size)
    except Exception:
        return None


# --- Photos (EXIF) ---------------------------------------------------------------


def _exif_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("ascii", errors="replace")
    text = str(value).strip().strip("\x00").strip()
    return text or None


def _parse_exif_offset(text: str | None) -> timezone | None:
    """Parse an EXIF UTC offset string like "-07:00", or None."""

    if not text or len(text) != 6 or text[0] not in "+-" or text[3] != ":":
        return None
    try:
        hours = int(text[1:3])
        minutes = int(text[4:6])
    except ValueError:
        return None
    delta = timedelta(hours=hours, minutes=minutes)
    if text[0] == "-":
        delta = -delta
    try:
        return timezone(delta)
    except ValueError:
        return None


def photo_capture_time(data: bytes) -> datetime | None:
    """Return the capture time embedded in a photo's EXIF, or None.

    Reads DateTimeOriginal (falling back to the file's DateTime tag)
    with Pillow. When the photo also carries OffsetTimeOriginal the
    instant is exact; without it the naive camera time is read as
    the local time of this computer and converted to UTC.
    """

    if not data:
        return None
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            exif = image.getexif()
            if not exif:
                return None
            try:
                exif_ifd = exif.get_ifd(0x8769)
            except Exception:
                exif_ifd = {}
            raw = (
                _exif_text(exif_ifd.get(36867))
                or _exif_text(exif.get(36867))
                or _exif_text(exif.get(306))
            )
            offset_raw = _exif_text(exif_ifd.get(36881)) or _exif_text(
                exif.get(36881)
            )
    except Exception:
        return None
    if raw is None:
        return None
    try:
        moment = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    offset = _parse_exif_offset(offset_raw)
    if offset is not None:
        return moment.replace(tzinfo=offset).astimezone(timezone.utc)
    # No recorded offset: the camera's wall-clock time, read as this
    # computer's local time (astimezone assumes local for naive
    # datetimes) and converted to UTC.
    return moment.astimezone(timezone.utc)
