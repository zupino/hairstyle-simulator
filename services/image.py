"""
In-memory image pre-processing for selfie uploads and hairstyle storage.

Selfie pipeline:
  1. Decode raw bytes → Pillow Image
  2. Convert to RGB (strip alpha, handle palette modes)
  3. Center-crop to square
  4. Downscale to max 1024 px on the long axis
  5. Encode to PNG bytes → base64 string for BFL API

Hairstyle upload pipeline:
  1. Decode raw bytes → Pillow Image
  2. Stamp a fixed label overlay ("hairstyle / <name>") at the bottom
  3. Return PNG bytes for storage on disk
"""

import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

MAX_SIZE = 1024  # pixels


def preprocess_selfie(raw_bytes: bytes) -> str:
    """Return a base64-encoded PNG string ready to send to BFL."""
    return _encode_png_b64(_preprocess_selfie_img(raw_bytes))


def preprocess_selfie_to_bytes(raw_bytes: bytes) -> bytes:
    """
    Return the normalised selfie as raw PNG bytes (crop → square, ≤1024 px).

    Use this when the same normalised image is needed both for BFL submission
    and for mask generation, so that both are guaranteed to be the same size.
    """
    buf = BytesIO()
    _preprocess_selfie_img(raw_bytes).save(buf, format="PNG")
    return buf.getvalue()


def image_file_to_b64(path: str) -> str:
    """Load a hairstyle image from disk and return base64-encoded PNG."""
    with open(path, "rb") as fh:
        img = Image.open(fh)
        img.load()  # ensure file is read before closing
    img = _to_rgb(img)
    return _encode_png_b64(img)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _preprocess_selfie_img(raw_bytes: bytes) -> Image.Image:
    img = Image.open(BytesIO(raw_bytes))
    img = _to_rgb(img)
    img = _center_crop_square(img)
    return _downscale(img, MAX_SIZE)


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    return img.convert("RGB")


def _center_crop_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def _downscale(img: Image.Image, max_px: int) -> Image.Image:
    w, h = img.size
    if w <= max_px and h <= max_px:
        return img
    # Both sides are equal after square crop; just resize.
    return img.resize((max_px, max_px), Image.LANCZOS)


def _encode_png_b64(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def stamp_hairstyle_label(raw_bytes: bytes, name: str) -> bytes:
    """
    Burn a 'hairstyle / <name>' banner into the bottom of the image.

    The overlay is a semi-transparent dark band so the model prompt can
    unambiguously refer to "the image labelled hairstyle" rather than a
    filename.  Returns PNG bytes ready to write to disk.
    """
    img = Image.open(BytesIO(raw_bytes)).convert("RGB")
    w, h = img.size

    # Banner height: roughly 1/8 of the image height, at least 56 px.
    banner_h = max(56, h // 8)
    padding = max(6, banner_h // 10)

    # Build a transparent overlay the same width as the image.
    overlay = Image.new("RGBA", (w, banner_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Dark semi-transparent background rectangle.
    draw.rectangle([(0, 0), (w, banner_h)], fill=(0, 0, 0, 175))

    # Font sizes proportional to banner height.
    small_size = max(11, banner_h // 5)
    large_size = max(16, banner_h // 3)

    try:
        # Pillow >= 10 supports load_default(size=N).
        small_font = ImageFont.load_default(size=small_size)
        large_font = ImageFont.load_default(size=large_size)
    except TypeError:
        small_font = ImageFont.load_default()
        large_font = ImageFont.load_default()

    # Top row: category label in muted grey.
    draw.text((padding, padding), "hairstyle", fill=(180, 180, 180, 255), font=small_font)

    # Bottom row: hairstyle name in bright white.
    name_y = padding + small_size + max(4, banner_h // 12)
    draw.text((padding, name_y), name, fill=(255, 255, 255, 255), font=large_font)

    # Composite overlay onto the image at the bottom edge.
    img_rgba = img.convert("RGBA")
    img_rgba.paste(overlay, (0, h - banner_h), overlay)

    buf = BytesIO()
    img_rgba.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
