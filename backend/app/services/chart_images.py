from __future__ import annotations

import base64
import io
import warnings

from PIL import Image, UnidentifiedImageError

MAX_CHART_BYTES = 10 * 1024 * 1024
MAX_CHART_PIXELS = 25_000_000
MAX_CHART_DIMENSION = 10_000
_SUPPORTED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg"}


def validate_chart_image(data: bytes, claimed_type: str) -> tuple[str, str]:
    if not data:
        raise ValueError("Choose a non-empty chart image.")
    if len(data) > MAX_CHART_BYTES:
        raise OverflowError("Chart image must be 10 MiB or smaller.")
    if claimed_type.lower().split(";", 1)[0].strip() not in _SUPPORTED_FORMATS.values():
        raise TypeError("Upload a PNG or JPEG chart screenshot.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            if image.format not in _SUPPORTED_FORMATS:
                raise TypeError("Upload a PNG or JPEG chart screenshot.")
            if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
                raise TypeError("Animated images are not supported.")
            width, height = image.size
            if width <= 0 or height <= 0 or width > MAX_CHART_DIMENSION or height > MAX_CHART_DIMENSION or width * height > MAX_CHART_PIXELS:
                raise OverflowError("Chart image dimensions exceed the supported limit.")
            image.verify()
        with Image.open(io.BytesIO(data)) as decoded:
            decoded.load()
            if decoded.format not in _SUPPORTED_FORMATS:
                raise TypeError("Upload a PNG or JPEG chart screenshot.")
    except Image.DecompressionBombError as exc:
        raise OverflowError("Chart image dimensions exceed the supported limit.") from exc
    except Image.DecompressionBombWarning as exc:
        raise OverflowError("Chart image dimensions exceed the supported limit.") from exc
    except UnidentifiedImageError as exc:
        raise ValueError("The uploaded file is not a valid PNG or JPEG image.") from exc
    except OSError as exc:
        raise ValueError("The uploaded chart image could not be decoded.") from exc

    mime_type = _SUPPORTED_FORMATS[decoded.format]
    if claimed_type.lower().split(";", 1)[0].strip() != mime_type:
        raise TypeError("Image content does not match its declared type.")
    image_data_url = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
    return mime_type, image_data_url
