"""
Hair/head mask generation using MediaPipe ImageSegmenter.

Uses the selfie_multiclass_256x256.tflite model which produces per-pixel
category labels:
  0 = background
  1 = hair
  2 = body-skin
  3 = face-skin
  4 = clothes
  5 = others

Two mask strategies are available (selected via the MASK_STRATEGY env var):

  hair        (default) — White pixels mark the detected hair region; black
              pixels mark everything else.  FLUX can only fill inside the
              original hair area, which works well for style/colour changes
              but cannot extend short hair into a longer style.

  head_region — White pixels mark a generously expanded bounding box around
              the head (above, left, right, and well below the face for long
              styles) with face-skin pixels zeroed out so FLUX cannot alter
              them.  This allows any hairstyle length (short→long, long→short)
              while locking the face identity.  Background and clothing outside
              the bounding box are also preserved.

  face_only   — The entire image is white (inpaint zone) except for the
              face-skin pixels, which are zeroed out (preserved).  FLUX has
              maximum freedom: it can paint any hairstyle, change the
              background, alter clothing etc.  Trade-off: only facial identity
              is guaranteed; everything else may change.

Both public mask functions accept optional `debug_dir` / `debug_prefix`
parameters (controlled by the DEBUG_MASK_DIR env var).  When `debug_dir` is
non-empty the following diagnostic images are written to that directory:

  {prefix}selfie.png        — the preprocessed selfie as decoded by Pillow
  {prefix}segmentation.png  — false-colour category map (see _DEBUG_PALETTE)
  {prefix}mask_raw.png      — binary mask before dilation
  {prefix}mask_final.png    — binary mask after dilation (the one sent to BFL)
"""

import base64
import io
import logging
import os
import urllib.request
from typing import Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "image_segmenter/selfie_multiclass_256x256/float32/latest/"
    "selfie_multiclass_256x256.tflite"
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_HERE, "..", "models")
_MODEL_PATH = os.path.join(_MODELS_DIR, "selfie_multiclass_256x256.tflite")

# Category indices from selfie_multiclass_256x256
_CAT_BACKGROUND = 0
_CAT_HAIR       = 1
_CAT_BODY_SKIN  = 2
_CAT_FACE_SKIN  = 3
_CAT_CLOTHES    = 4
_CAT_OTHERS     = 5

# False-colour palette for debug visualisation (one RGB per category index)
_DEBUG_PALETTE = [
    ( 20,  20,  20),  # 0 background — near-black
    (255, 215,   0),  # 1 hair       — gold
    (255, 160, 100),  # 2 body-skin  — peach
    (220, 120,  80),  # 3 face-skin  — terracotta
    ( 80, 120, 200),  # 4 clothes    — blue
    (160, 160, 160),  # 5 others     — grey
]


def _ensure_model() -> str:
    """Download the segmentation model if not already cached; return its path."""
    if os.path.exists(_MODEL_PATH):
        return _MODEL_PATH
    os.makedirs(_MODELS_DIR, exist_ok=True)
    tmp_path = _MODEL_PATH + ".tmp"
    print(f"[mask] Downloading segmentation model from {_MODEL_URL} …")
    urllib.request.urlretrieve(_MODEL_URL, tmp_path)
    os.replace(tmp_path, _MODEL_PATH)
    print(f"[mask] Model saved to {_MODEL_PATH}")
    return _MODEL_PATH


# ---------------------------------------------------------------------------
# Shared segmentation helper
# ---------------------------------------------------------------------------

def _run_segmentation(image_bytes: bytes) -> Tuple[Image.Image, np.ndarray]:
    """
    Run MediaPipe segmentation on image_bytes.

    Returns:
        (pil_image, cat_array) where:
        - pil_image  is the decoded RGB image at original resolution
        - cat_array  is a uint8 ndarray of shape (H, W) with category indices,
                     resized to match pil_image using NEAREST interpolation so
                     category values are never blended across boundaries.

    Raises:
        RuntimeError: if MediaPipe is not installed or segmentation fails.
    """
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import vision as mp_vision
        from mediapipe.tasks.python.core import base_options as mp_base
    except ImportError as exc:
        raise RuntimeError(
            "mediapipe is not installed.  Run:  pip install mediapipe"
        ) from exc

    model_path = _ensure_model()

    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    original_size = pil_image.size  # (width, height)

    np_rgb = np.array(pil_image, dtype=np.uint8)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np_rgb)

    options = mp_vision.ImageSegmenterOptions(
        base_options=mp_base.BaseOptions(model_asset_path=model_path),
        output_category_mask=True,
        output_confidence_masks=True,
    )
    with mp_vision.ImageSegmenter.create_from_options(options) as segmenter:
        result = segmenter.segment(mp_image)

    # Prefer category_mask (single argmax map); fall back to argmax of all
    # confidence masks — more reliable on some mediapipe/platform combinations.
    if result.category_mask is not None:
        cat_array = np.squeeze(result.category_mask.numpy_view()).astype(np.uint8)
    elif result.confidence_masks:
        conf_stack = np.stack(
            [np.squeeze(np.array(m.numpy_view(), dtype=np.float32))
             for m in result.confidence_masks],
            axis=0,
        )  # shape: (num_categories, H, W)
        cat_array = np.argmax(conf_stack, axis=0).astype(np.uint8)
    else:
        raise RuntimeError(
            "MediaPipe segmentation returned no masks "
            "(both category_mask and confidence_masks are empty)"
        )

    # Resize to original image resolution.  NEAREST preserves integer category
    # values exactly (no interpolation blending across category boundaries).
    if cat_array.shape[::-1] != original_size:  # shape=(H,W), size=(W,H)
        cat_img = Image.fromarray(cat_array, mode="L")
        cat_img = cat_img.resize(original_size, Image.NEAREST)
        cat_array = np.array(cat_img, dtype=np.uint8)

    return pil_image, cat_array


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

def _save_debug(img: Image.Image, debug_dir: str, filename: str) -> None:
    """Save a PIL image to debug_dir/filename and log the path."""
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, filename)
    img.save(path)
    logger.info("[mask][debug] saved %s", path)


def _category_map_to_rgb(cat_array: np.ndarray) -> Image.Image:
    """Render a category index array as a false-colour RGB image for inspection."""
    h, w = cat_array.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for idx, colour in enumerate(_DEBUG_PALETTE):
        rgb[cat_array == idx] = colour
    return Image.fromarray(rgb, mode="RGB")


# ---------------------------------------------------------------------------
# Public mask-creation API
# ---------------------------------------------------------------------------

def create_hair_mask(
    image_bytes: bytes,
    debug_dir: str = "",
    debug_prefix: str = "",
) -> bytes:
    """
    Strategy 'hair': white = original hair region (inpaint here), black = rest.

    A circular dilation of radius 18 px (for 1024 px images) is applied to
    the raw hair mask so the fill covers hairline edge pixels cleanly.

    Suitable for hairstyle/colour changes within the existing hair footprint.
    Cannot extend hair beyond its current boundaries (short→long will clip).

    Args:
        image_bytes:   PNG bytes of the preprocessed selfie.
        debug_dir:     Directory for diagnostic images; empty = disabled.
        debug_prefix:  Filename prefix for all debug images (e.g. job ID + "_").
    """
    pil_image, cat_array = _run_segmentation(image_bytes)
    logger.info(
        "[mask] strategy=hair  image=%dx%d  hair_px=%d",
        pil_image.width, pil_image.height,
        int(np.sum(cat_array == _CAT_HAIR)),
    )

    if debug_dir:
        _save_debug(pil_image, debug_dir, f"{debug_prefix}selfie.png")
        _save_debug(
            _category_map_to_rgb(cat_array),
            debug_dir, f"{debug_prefix}segmentation.png",
        )

    raw = np.where(cat_array == _CAT_HAIR, np.uint8(255), np.uint8(0))

    if debug_dir:
        _save_debug(
            Image.fromarray(raw, mode="L"),
            debug_dir, f"{debug_prefix}mask_raw.png",
        )

    mask_img = _dilate_mask(Image.fromarray(raw, mode="L"), radius=18)

    if debug_dir:
        _save_debug(mask_img, debug_dir, f"{debug_prefix}mask_final.png")

    buf = io.BytesIO()
    mask_img.save(buf, format="PNG")
    return buf.getvalue()


def create_head_region_mask(
    image_bytes: bytes,
    debug_dir: str = "",
    debug_prefix: str = "",
) -> bytes:
    """
    Strategy 'head_region': inpaint an expanded area around the head while
    keeping face-skin pixels black (preserved by FLUX).

    Algorithm:
      1. Find the bounding box of face-skin pixels (category 3).
      2. Expand: +60 % above, ±50 % left/right, +200 % below the face bbox.
         The generous downward padding lets long hair grow toward the shoulders.
      3. Fill the expanded box white (inpaint zone).
      4. Zero-out every face-skin pixel so the face is mathematically locked.
      5. Apply a light dilation (radius 6 px) to smooth the face boundary edge,
         then re-apply face-skin zeroing so dilation cannot creep into the face.

    Args:
        image_bytes:   PNG bytes of the preprocessed selfie.
        debug_dir:     Directory for diagnostic images; empty = disabled.
        debug_prefix:  Filename prefix for all debug images (e.g. job ID + "_").
    """
    pil_image, cat_array = _run_segmentation(image_bytes)
    img_w, img_h = pil_image.size
    logger.info(
        "[mask] strategy=head_region  image=%dx%d  face_px=%d",
        img_w, img_h,
        int(np.sum(cat_array == _CAT_FACE_SKIN)),
    )

    if debug_dir:
        _save_debug(pil_image, debug_dir, f"{debug_prefix}selfie.png")
        _save_debug(
            _category_map_to_rgb(cat_array),
            debug_dir, f"{debug_prefix}segmentation.png",
        )

    face_pixels = np.argwhere(cat_array == _CAT_FACE_SKIN)  # shape: (N, 2) as (row, col)

    if len(face_pixels) == 0:
        logger.warning(
            "[mask] no face-skin pixels detected; using full-image inpaint zone"
        )
        inpaint_zone = np.full((img_h, img_w), 255, dtype=np.uint8)
    else:
        min_row, min_col = face_pixels.min(axis=0)
        max_row, max_col = face_pixels.max(axis=0)
        face_h = max_row - min_row
        face_w = max_col - min_col

        top    = max(0,     int(min_row - face_h * 0.6))
        bottom = min(img_h, int(max_row + face_h * 2.0))
        left   = max(0,     int(min_col - face_w * 0.5))
        right  = min(img_w, int(max_col + face_w * 0.5))

        logger.info(
            "[mask] face bbox rows=%d-%d cols=%d-%d  "
            "expanded top=%d bottom=%d left=%d right=%d",
            min_row, max_row, min_col, max_col,
            top, bottom, left, right,
        )

        inpaint_zone = np.zeros((img_h, img_w), dtype=np.uint8)
        inpaint_zone[top:bottom, left:right] = 255

    # Preserve face-skin pixels — zero them out inside the inpaint zone.
    inpaint_zone[cat_array == _CAT_FACE_SKIN] = 0

    if debug_dir:
        _save_debug(
            Image.fromarray(inpaint_zone, mode="L"),
            debug_dir, f"{debug_prefix}mask_raw.png",
        )

    # Light dilation to smooth the face boundary, then re-lock face pixels.
    mask_img = _dilate_mask(Image.fromarray(inpaint_zone, mode="L"), radius=6)
    mask_arr = np.array(mask_img, dtype=np.uint8)
    mask_arr[cat_array == _CAT_FACE_SKIN] = 0
    mask_img = Image.fromarray(mask_arr, mode="L")

    if debug_dir:
        _save_debug(mask_img, debug_dir, f"{debug_prefix}mask_final.png")

    buf = io.BytesIO()
    mask_img.save(buf, format="PNG")
    return buf.getvalue()


def create_face_only_mask(
    image_bytes: bytes,
    debug_dir: str = "",
    debug_prefix: str = "",
) -> bytes:
    """
    Strategy 'face_only': white = entire image except face-skin pixels.

    Face-skin pixels (category 3) are zeroed out so FLUX preserves them
    exactly.  Everything else — hair, background, body, clothes — is white
    (inpaint zone), giving the model maximum freedom to apply any hairstyle
    regardless of length or shape.

    A dilation of radius 10 px is applied to the face preservation area
    before inverting, so a clean buffer around the face boundary (hairline
    edge, ears, chin) is also locked, preventing the model from accidentally
    eroding facial features at the boundary.

    Trade-off: background, clothing, and body may change.  Only facial
    identity is mathematically guaranteed.

    Args:
        image_bytes:   PNG bytes of the preprocessed selfie.
        debug_dir:     Directory for diagnostic images; empty = disabled.
        debug_prefix:  Filename prefix for all debug images (e.g. job ID + "_").
    """
    pil_image, cat_array = _run_segmentation(image_bytes)
    img_w, img_h = pil_image.size
    logger.info(
        "[mask] strategy=face_only  image=%dx%d  face_px=%d",
        img_w, img_h,
        int(np.sum(cat_array == _CAT_FACE_SKIN)),
    )

    if debug_dir:
        _save_debug(pil_image, debug_dir, f"{debug_prefix}selfie.png")
        _save_debug(
            _category_map_to_rgb(cat_array),
            debug_dir, f"{debug_prefix}segmentation.png",
        )

    # Build a binary face-skin mask and dilate it to include a boundary buffer.
    face_raw = np.where(cat_array == _CAT_FACE_SKIN, np.uint8(255), np.uint8(0))
    face_dilated = np.array(
        _dilate_mask(Image.fromarray(face_raw, mode="L"), radius=10),
        dtype=np.uint8,
    )

    # Invert: everything outside the (dilated) face is inpainted.
    inpaint_zone = np.where(face_dilated > 0, np.uint8(0), np.uint8(255))

    if debug_dir:
        _save_debug(
            Image.fromarray(inpaint_zone, mode="L"),
            debug_dir, f"{debug_prefix}mask_raw.png",
        )

    # The mask IS the final mask — no further dilation needed.
    mask_img = Image.fromarray(inpaint_zone, mode="L")

    if debug_dir:
        _save_debug(mask_img, debug_dir, f"{debug_prefix}mask_final.png")

    buf = io.BytesIO()
    mask_img.save(buf, format="PNG")
    return buf.getvalue()


def create_mask(
    image_bytes: bytes,
    strategy: str = "hair",
    debug_dir: str = "",
    debug_prefix: str = "",
) -> bytes:
    """
    Dispatch to the requested mask strategy.

    Args:
        image_bytes:  PNG bytes of the preprocessed selfie.
        strategy:     "hair" (default), "head_region", or "face_only".
        debug_dir:    Directory for diagnostic images; empty = disabled.
        debug_prefix: Filename prefix for all debug images (e.g. job ID + "_").
    """
    logger.info("[mask] create_mask called: strategy=%s debug_dir=%r", strategy, debug_dir or "(off)")
    if strategy == "head_region":
        return create_head_region_mask(image_bytes, debug_dir=debug_dir, debug_prefix=debug_prefix)
    if strategy == "face_only":
        return create_face_only_mask(image_bytes, debug_dir=debug_dir, debug_prefix=debug_prefix)
    return create_hair_mask(image_bytes, debug_dir=debug_dir, debug_prefix=debug_prefix)


# ---------------------------------------------------------------------------
# Encoding helper
# ---------------------------------------------------------------------------

def mask_to_b64(mask_bytes: bytes) -> str:
    """Base64-encode a mask PNG for the BFL API payload."""
    return base64.b64encode(mask_bytes).decode()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dilate_mask(mask_img: Image.Image, radius: int) -> Image.Image:
    """
    Morphological dilation using a circular structuring element implemented
    with numpy only (no scipy / cv2 dependency).

    Expands the white region by `radius` pixels in every direction.
    """
    arr = np.array(mask_img, dtype=np.uint8)

    diameter = 2 * radius + 1
    y_coords, x_coords = np.ogrid[-radius: radius + 1, -radius: radius + 1]
    kernel = (x_coords**2 + y_coords**2 <= radius**2).astype(np.uint8)

    h, w = arr.shape
    kh, kw = kernel.shape
    pad_h, pad_w = kh // 2, kw // 2
    padded = np.pad(arr, ((pad_h, pad_h), (pad_w, pad_w)), mode="constant", constant_values=0)

    out = np.zeros_like(arr)
    ky_indices, kx_indices = np.where(kernel)
    for ky, kx in zip(ky_indices, kx_indices):
        region = padded[ky: ky + h, kx: kx + w]
        out = np.maximum(out, region)

    return Image.fromarray(out, mode="L")
