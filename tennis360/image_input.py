"""Safe local decoding rules for one user-provided JPEG or PNG."""

from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
ALLOWED_IMAGE_FORMATS = frozenset({"JPEG", "PNG"})


class UploadedImageError(ValueError):
    """An uploaded image is unsupported, unsafe to decode, or unreadable."""


def decode_uploaded_image(
    file_bytes: bytes,
    *,
    maximum_bytes: int = MAX_UPLOAD_BYTES,
    maximum_pixels: int = MAX_IMAGE_PIXELS,
) -> np.ndarray:
    """Return an oriented RGB image after enforcing local upload limits.

    This function does not write source bytes or decoded pixels to disk.
    """

    if not file_bytes:
        raise UploadedImageError("The uploaded file was empty.")
    if len(file_bytes) > maximum_bytes:
        raise UploadedImageError(
            f"The image is larger than the {maximum_bytes // (1024 * 1024)} MB limit."
        )

    try:
        with Image.open(BytesIO(file_bytes)) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise UploadedImageError("Only JPEG and PNG images are supported.")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > maximum_pixels:
                raise UploadedImageError(
                    f"The image exceeds the {maximum_pixels // 1_000_000} megapixel limit."
                )
            corrected = ImageOps.exif_transpose(image).convert("RGB")
            return np.asarray(corrected)
    except UploadedImageError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as error:
        raise UploadedImageError("This file could not be read as a supported image.") from error
