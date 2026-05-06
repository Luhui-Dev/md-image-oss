"""High-quality image compression using Pillow.

The goal is to reduce file size meaningfully while preserving visual quality:
- JPEG: progressive + quality 85 (visually near-lossless), MozJPEG-style optimization.
- PNG: lossless optimization; only kept if smaller than the original.
- WebP: re-encoded with method=6 (max effort) at the configured quality.
- GIF / SVG / animated images: returned unchanged so we don't break animation
  or vector graphics.
"""

from __future__ import annotations

import io
from typing import Tuple

try:
    from PIL import Image, ImageOps
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "Pillow is required for image compression. "
        "Install it with: pip install Pillow"
    ) from e


# Extensions we leave untouched.
_SKIP_EXTS = {".gif", ".svg", ".bmp", ".ico", ".tif", ".tiff"}


def compress_image(data: bytes, ext: str, quality: int = 85) -> Tuple[bytes, str]:
    """Compress an image and return (data, extension).

    The returned extension may differ from the input (always lowercase, and
    .jpeg is normalized to .jpg). If compression cannot meaningfully reduce
    size, the original bytes are returned.
    """
    ext = (ext or "").lower()
    if not ext.startswith("."):
        ext = "." + ext

    if ext in _SKIP_EXTS:
        return data, ext

    try:
        img = Image.open(io.BytesIO(data))
    except Exception:
        # Not a recognizable image — leave it alone.
        return data, ext

    # Don't break animations.
    if getattr(img, "is_animated", False):
        return data, ext

    # Honor the EXIF orientation so the encoded image is upright.
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    fmt = (img.format or "").upper()

    if ext in (".jpg", ".jpeg") or fmt == "JPEG":
        return _encode_jpeg(img, data, quality)

    if ext == ".png" or fmt == "PNG":
        return _encode_png(img, data)

    if ext == ".webp" or fmt == "WEBP":
        return _encode_webp(img, data, quality)

    # Unknown but openable — try JPEG as a sensible default for photos,
    # otherwise PNG. Fall back to original on failure.
    try:
        if img.mode in ("RGBA", "LA", "P"):
            return _encode_png(img.convert("RGBA"), data)
        return _encode_jpeg(img.convert("RGB"), data, quality)
    except Exception:
        return data, ext


def _encode_jpeg(img: "Image.Image", original: bytes, quality: int) -> Tuple[bytes, str]:
    if img.mode != "RGB":
        # JPEG can't carry alpha — flatten onto a white background.
        if img.mode in ("RGBA", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert("RGB")

    out = io.BytesIO()
    img.save(
        out,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
        subsampling=2,
    )
    encoded = out.getvalue()
    if len(encoded) < len(original):
        return encoded, ".jpg"
    return original, ".jpg"


def _encode_png(img: "Image.Image", original: bytes) -> Tuple[bytes, str]:
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    encoded = out.getvalue()
    if len(encoded) < len(original):
        return encoded, ".png"
    return original, ".png"


def _encode_webp(img: "Image.Image", original: bytes, quality: int) -> Tuple[bytes, str]:
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=quality, method=6)
    encoded = out.getvalue()
    if len(encoded) < len(original):
        return encoded, ".webp"
    return original, ".webp"
