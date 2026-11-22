"""Normalize uploads once and preserve their framing and orientation."""
import base64
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps
from fastapi import HTTPException, UploadFile

async def read_image(file: UploadFile) -> Image.Image:
    data = await file.read(12_000_001)
    if len(data) > 12_000_000:
        raise HTTPException(413, "Please use an image under 12 MB")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > 32_000_000:
                raise HTTPException(413, "Please use an image under 32 megapixels")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            return image
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Could not read the photo") from exc

def jpeg(image):
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=93)
    return buffer.getvalue()

def encoded(data):
    return base64.b64encode(data).decode("ascii")
