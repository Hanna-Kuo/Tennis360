"""Tests for best-effort capture-time extraction.

A record's time point is its source's recording time when the file
carries one, and the save time otherwise. These tests build synthetic
MP4/MOV byte fixtures (movie header, QuickTime creation date, ©day)
and EXIF-bearing photos, and pin the rules: a present tag parses to
the exact instant, the textual tag beats the header, and absent or
corrupt metadata yields None — never a guessed time.
"""

import struct
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from tennis360 import capture_time

SATURDAY = datetime(2026, 10, 24, 17, 0, 0, tzinfo=timezone.utc)
_MAC_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + kind + payload


def _mac_seconds(moment: datetime) -> int:
    return int((moment - _MAC_EPOCH).total_seconds())


def _mvhd(moment: datetime, *, version: int = 0, raw: int | None = None) -> bytes:
    seconds = _mac_seconds(moment) if raw is None else raw
    if version == 1:
        payload = (
            b"\x01\x00\x00\x00"
            + struct.pack(">Q", seconds)
            + struct.pack(">Q", seconds)
            + struct.pack(">I", 1000)
            + struct.pack(">I", 0)
        )
    else:
        payload = (
            b"\x00\x00\x00\x00"
            + struct.pack(">I", seconds)
            + struct.pack(">I", seconds)
            + struct.pack(">I", 1000)
            + struct.pack(">I", 0)
        )
    return _box(b"mvhd", payload)


def _quicktime_meta(text: str) -> bytes:
    name = b"com.apple.quicktime.creationdate"
    entry = struct.pack(">I", 8 + len(name)) + b"mdta" + name
    keys = _box(b"keys", b"\x00\x00\x00\x00" + struct.pack(">I", 1) + entry)
    data_atom = _box(
        b"data", struct.pack(">II", 1, 0) + text.encode("utf-8")
    )
    ilst = _box(b"ilst", _box(struct.pack(">I", 1), data_atom))
    return _box(b"meta", b"\x00\x00\x00\x00" + keys + ilst)


def _video(*moov_children: bytes) -> bytes:
    ftyp = _box(b"ftyp", b"isom\x00\x00\x00\x00isomiso2")
    return ftyp + _box(b"moov", b"".join(moov_children))


class VideoCaptureTimeTest(unittest.TestCase):
    def test_mvhd_creation_time_is_parsed(self):
        data = _video(_mvhd(SATURDAY))
        self.assertEqual(capture_time.video_capture_time(data), SATURDAY)

    def test_mvhd_version_1_creation_time_is_parsed(self):
        data = _video(_mvhd(SATURDAY, version=1))
        self.assertEqual(capture_time.video_capture_time(data), SATURDAY)

    def test_quicktime_creation_date_wins_over_mvhd(self):
        # The phone's textual tag says Saturday 10:00 at UTC-07:00,
        # which is Saturday 17:00 UTC; the header disagrees (an edit
        # rewrote it), and the textual tag is the precise one.
        meta = _quicktime_meta("2026-10-24T10:00:00-07:00")
        header = _mvhd(datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(
            capture_time.video_capture_time(_video(header, meta)), SATURDAY
        )

    def test_quicktime_creation_date_alone_is_parsed(self):
        meta = _quicktime_meta("2026-10-24T17:00:00Z")
        self.assertEqual(
            capture_time.video_capture_time(_video(meta)), SATURDAY
        )

    def test_udta_day_atom_is_the_fallback(self):
        udta = _box(b"udta", _box(b"\xa9day", b"2026-10-24T17:00:00.000Z"))
        self.assertEqual(
            capture_time.video_capture_time(_video(udta)), SATURDAY
        )

    def test_video_without_metadata_returns_none(self):
        data = _box(b"ftyp", b"isom\x00\x00\x00\x00") + _box(b"free", b"1234")
        self.assertIsNone(capture_time.video_capture_time(data))
        self.assertIsNone(capture_time.video_capture_time(b""))

    def test_zero_mvhd_creation_time_returns_none(self):
        self.assertIsNone(
            capture_time.video_capture_time(_video(_mvhd(SATURDAY, raw=0)))
        )

    def test_corrupt_boxes_return_none(self):
        self.assertIsNone(capture_time.video_capture_time(b"\x00\x01\x02"))
        # A moov box whose declared size runs past the end of the data.
        truncated = _box(b"ftyp", b"isom") + struct.pack(">I", 9999) + b"moov"
        self.assertIsNone(capture_time.video_capture_time(truncated))
        # Garbage inside moov where mvhd should be.
        garbage = _video(b"\xff" * 12)
        self.assertIsNone(capture_time.video_capture_time(garbage))

    def test_capture_time_from_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "clip.mov"
            path.write_bytes(_video(_mvhd(SATURDAY)))
            self.assertEqual(
                capture_time.video_capture_time_from_path(path), SATURDAY
            )
            self.assertIsNone(
                capture_time.video_capture_time_from_path(
                    Path(folder) / "missing.mov"
                )
            )


def _jpeg_bytes(exif_tags: dict) -> bytes:
    from PIL import Image

    image = Image.new("RGB", (8, 8))
    exif = image.getexif()
    for tag, value in exif_tags.items():
        exif[tag] = value
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


class PhotoCaptureTimeTest(unittest.TestCase):
    def test_exif_original_with_offset_is_exact(self):
        data = _jpeg_bytes(
            {36867: "2026:10:24 10:00:00", 36881: "-07:00"}
        )
        self.assertEqual(capture_time.photo_capture_time(data), SATURDAY)

    def test_exif_without_offset_keeps_the_local_wall_time(self):
        data = _jpeg_bytes({36867: "2026:10:24 10:00:00"})
        moment = capture_time.photo_capture_time(data)
        self.assertIsNotNone(moment)
        assert moment is not None
        # The camera's wall-clock time, read as this computer's local
        # time and converted to UTC.
        self.assertEqual(
            moment, datetime(2026, 10, 24, 10, 0, 0).astimezone(timezone.utc)
        )
        self.assertEqual(
            moment.astimezone().replace(tzinfo=None),
            datetime(2026, 10, 24, 10, 0, 0),
        )

    def test_exif_datetime_tag_is_the_fallback(self):
        data = _jpeg_bytes({306: "2026:10:24 10:00:00", 36881: "-07:00"})
        self.assertEqual(capture_time.photo_capture_time(data), SATURDAY)

    def test_photo_without_exif_returns_none(self):
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (8, 8)).save(buffer, format="PNG")
        self.assertIsNone(capture_time.photo_capture_time(buffer.getvalue()))
        self.assertIsNone(capture_time.photo_capture_time(b"not an image"))
        self.assertIsNone(capture_time.photo_capture_time(b""))


class OffsetTimestampTest(unittest.TestCase):
    def test_offset_shifts_the_base(self):
        self.assertEqual(
            capture_time.offset_timestamp("2026-10-24T17:00:00+00:00", 90.0),
            "2026-10-24T17:01:30+00:00",
        )

    def test_missing_base_or_offset(self):
        self.assertIsNone(capture_time.offset_timestamp(None, 5.0))
        self.assertEqual(
            capture_time.offset_timestamp("2026-10-24T17:00:00+00:00", None),
            "2026-10-24T17:00:00+00:00",
        )
        self.assertIsNone(capture_time.offset_timestamp("junk", 5.0))

    def test_to_utc_iso_converts_offsets(self):
        moment = datetime(
            2026, 10, 24, 19, 0, 0, tzinfo=timezone(timedelta(hours=2))
        )
        self.assertEqual(
            capture_time.to_utc_iso(moment), "2026-10-24T17:00:00+00:00"
        )


if __name__ == "__main__":
    unittest.main()
