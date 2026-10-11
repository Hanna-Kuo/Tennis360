"""Tests for content validation before a photo reaches MediaPipe."""

from __future__ import annotations

from io import BytesIO
import unittest

from PIL import Image

from tennispose.image_input import UploadedImageError, decode_uploaded_image


def image_bytes(image_format: str, size: tuple[int, int] = (2, 2)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color="white").save(output, format=image_format)
    return output.getvalue()


class UploadedImageTests(unittest.TestCase):
    def test_jpeg_is_decoded_to_rgb(self) -> None:
        image = decode_uploaded_image(image_bytes("JPEG"))

        self.assertEqual(image.shape, (2, 2, 3))

    def test_png_is_decoded_to_rgb(self) -> None:
        image = decode_uploaded_image(image_bytes("PNG"))

        self.assertEqual(image.shape, (2, 2, 3))

    def test_non_jpeg_or_png_content_is_rejected(self) -> None:
        with self.assertRaisesRegex(UploadedImageError, "Only JPEG and PNG"):
            decode_uploaded_image(image_bytes("GIF"))

    def test_byte_limit_is_enforced_before_decoding(self) -> None:
        with self.assertRaisesRegex(UploadedImageError, "larger"):
            decode_uploaded_image(b"x" * 11, maximum_bytes=10)

    def test_pixel_limit_is_enforced_before_rgb_conversion(self) -> None:
        with self.assertRaisesRegex(UploadedImageError, "megapixel"):
            decode_uploaded_image(image_bytes("PNG", size=(2, 2)), maximum_pixels=3)


if __name__ == "__main__":
    unittest.main()
