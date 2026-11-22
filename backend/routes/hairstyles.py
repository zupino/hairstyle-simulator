"""
Hairstyle listing and image serving endpoints.
Accessible to both operators and admins.
"""

import os
import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from backend import config, database
from backend.auth import require_operator_or_admin
from backend.models import HairstyleOut

router = APIRouter(prefix="/api/hairstyles", tags=["hairstyles"])


@router.get("", response_model=list[HairstyleOut])
async def list_hairstyles(user=Depends(require_operator_or_admin)):
    rows = database.list_hairstyles()
    return [dict(r) for r in rows]


@router.get("/{hairstyle_id}/image")
async def get_hairstyle_image(hairstyle_id: int, user=Depends(require_operator_or_admin)):
    row = database.get_hairstyle(hairstyle_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Hairstyle not found")

    file_path = os.path.join(config.STORAGE_PATH, row["filename"])
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image file missing")

    with open(file_path, "rb") as fh:
        data = fh.read()

    content_type, _ = mimetypes.guess_type(file_path)
    content_type = content_type or "application/octet-stream"
    return Response(content=data, media_type=content_type)
