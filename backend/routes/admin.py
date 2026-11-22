"""
Admin-only endpoints for operator management and hairstyle uploads.
All routes require a valid JWT with role='admin'.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status

from backend import config, database
from backend.auth import require_admin, hash_password
from backend.models import OperatorCreate, OperatorUpdate, OperatorOut, HairstyleOut
from services.image import read_image, jpeg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Operator management
# ---------------------------------------------------------------------------

@router.get("/operators", response_model=list[OperatorOut])
async def list_operators(admin=Depends(require_admin)):
    rows = database.list_operators()
    return [dict(r) for r in rows]


@router.post("/operators", response_model=OperatorOut, status_code=status.HTTP_201_CREATED)
async def create_operator(body: OperatorCreate, admin=Depends(require_admin)):
    existing = database.get_user_by_username(body.username)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    now = _now()
    user_id = database.create_user(
        username=body.username,
        password_hash=hash_password(body.password),
        role="operator",
        created_at=now,
    )
    return OperatorOut(
        id=user_id,
        username=body.username,
        role="operator",
        is_active=True,
        created_at=now,
    )


@router.put("/operators/{operator_id}", response_model=OperatorOut)
async def update_operator(operator_id: int, body: OperatorUpdate, admin=Depends(require_admin)):
    ok = database.update_operator(operator_id, int(body.is_active))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
    row = database.get_user_by_id(operator_id)
    return dict(row)


@router.delete("/operators/{operator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_operator(operator_id: int, admin=Depends(require_admin)):
    ok = database.delete_operator(operator_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")


# ---------------------------------------------------------------------------
# Hairstyle management
# ---------------------------------------------------------------------------

@router.post("/hairstyles", response_model=HairstyleOut, status_code=status.HTTP_201_CREATED)
async def upload_hairstyle(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    admin=Depends(require_admin),
):
    if file.content_type not in _ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type: {file.content_type}. Use JPEG, PNG, or WebP.",
        )

    filename = f"{uuid.uuid4().hex}.jpg"
    dest_path = os.path.join(config.STORAGE_PATH, filename)
    os.makedirs(config.STORAGE_PATH, exist_ok=True)
    image = await read_image(file)
    with open(dest_path, "wb") as fh:
        fh.write(jpeg(image))
    description = None
    now = _now()
    hairstyle_id = database.create_hairstyle(
        name=name,
        filename=filename,
        uploaded_by=admin["id"],
        created_at=now,
        description=description,
    )
    return HairstyleOut(
        id=hairstyle_id,
        name=name,
        filename=filename,
        uploaded_by=admin["id"],
        created_at=now,
        description=description,
    )


@router.delete("/hairstyles/{hairstyle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hairstyle(hairstyle_id: int, admin=Depends(require_admin)):
    row = database.get_hairstyle(hairstyle_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hairstyle not found")

    file_path = os.path.join(config.STORAGE_PATH, row["filename"])
    if os.path.exists(file_path):
        os.remove(file_path)

    database.delete_hairstyle(hairstyle_id)
