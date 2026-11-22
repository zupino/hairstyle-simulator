"""
Image generation endpoints.

POST /api/generate            — submit a job (selfie + hairstyle_id)
GET  /api/generate/{job_id}  — poll; returns image bytes when ready

The active generation backend is selected by GENERATION_BACKEND (config):

  bfl_fill      — masked inpainting via flux-pro-1.0-fill.
                  The selfie is preprocessed and a hair mask is generated
                  (strategy from MASK_STRATEGY); both are sent to the BFL
                  fill model together with a text prompt.

  bfl_standard  — two-image transfer via flux-2-pro (or BFL_MODEL).
                  The selfie and the hairstyle reference image are sent
                  together; no mask is generated.

When DEBUG_MASK_DIR is set, diagnostic images (selfie, segmentation map,
raw mask, final mask) are written to that directory for every bfl_fill
request, with the job ID as filename prefix.
"""

import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import JSONResponse, Response

from backend import config, database
from backend.auth import require_operator_or_admin
from backend.models import GenerateResponse
from services.image import preprocess_selfie_to_bytes, image_file_to_b64
from services.mask import create_mask, mask_to_b64
from services.bfl import submit_generation, submit_fill_generation, poll_generation, fetch_image_bytes

router = APIRouter(prefix="/api/generate", tags=["generation"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(
    selfie: Annotated[UploadFile, File(description="Selfie image captured by operator")],
    hairstyle_id: Annotated[int, Form(description="ID of the target hairstyle")],
    user=Depends(require_operator_or_admin),
):
    # Validate hairstyle exists.
    hairstyle = database.get_hairstyle(hairstyle_id)
    if hairstyle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hairstyle not found")

    job_id = uuid.uuid4().hex
    backend = config.GENERATION_BACKEND

    # Read selfie bytes once; all subsequent steps are in-memory.
    raw_selfie = await selfie.read()

    # Normalise selfie to a square PNG at ≤1024 px.
    try:
        selfie_png = preprocess_selfie_to_bytes(raw_selfie)
    except Exception as exc:
        logger.exception("job=%s  Selfie preprocessing failed", job_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not process selfie image: {exc}",
        )

    selfie_b64 = base64.b64encode(selfie_png).decode()

    if backend == "bfl_standard":
        bfl_resp = await _submit_bfl_standard(job_id, hairstyle, selfie_b64)
    else:
        # Default: bfl_fill
        if backend != "bfl_fill":
            logger.warning(
                "job=%s  Unknown GENERATION_BACKEND=%r, falling back to bfl_fill",
                job_id, backend,
            )
        bfl_resp = await _submit_bfl_fill(job_id, hairstyle, selfie_png, selfie_b64)

    bfl_request_id = bfl_resp.get("id") or bfl_resp.get("request_id")
    bfl_polling_url = bfl_resp.get("polling_url")
    if not bfl_request_id or not bfl_polling_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected BFL response: {bfl_resp}",
        )

    database.create_job(
        job_id=job_id,
        bfl_request_id=bfl_request_id,
        bfl_polling_url=bfl_polling_url,
        operator_id=user["id"],
        created_at=_now(),
    )

    return GenerateResponse(job_id=job_id)


async def _submit_bfl_standard(job_id: str, hairstyle, selfie_b64: str) -> dict:
    """Two-image BFL approach: selfie + hairstyle reference, no mask."""
    hairstyle_path = os.path.join(config.STORAGE_PATH, hairstyle["filename"])
    logger.info(
        "job=%s  backend=bfl_standard  model=%s  hairstyle=%r",
        job_id, config.BFL_MODEL, hairstyle["name"],
    )
    try:
        hairstyle_b64 = image_file_to_b64(hairstyle_path)
    except Exception as exc:
        logger.exception("job=%s  Failed to load hairstyle image", job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not load hairstyle image: {exc}",
        )
    try:
        return await submit_generation(selfie_b64, hairstyle_b64)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"BFL API error: {exc}",
        )


async def _submit_bfl_fill(
    job_id: str, hairstyle, selfie_png: bytes, selfie_b64: str
) -> dict:
    """Inpainting fill approach: selfie + generated hair mask + text prompt."""
    logger.info(
        "job=%s  backend=bfl_fill  model=%s  mask_strategy=%s  debug_mask_dir=%r  hairstyle=%r",
        job_id, config.BFL_FILL_MODEL, config.MASK_STRATEGY,
        config.DEBUG_MASK_DIR or "(off)", hairstyle["name"],
    )
    try:
        mask_bytes = create_mask(
            selfie_png,
            strategy=config.MASK_STRATEGY,
            debug_dir=config.DEBUG_MASK_DIR,
            debug_prefix=f"{job_id}_",
        )
        mask_b64 = mask_to_b64(mask_bytes)
    except Exception as exc:
        logger.exception("job=%s  Mask generation failed (strategy=%s)", job_id, config.MASK_STRATEGY)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not generate mask: {exc}",
        )

    description = hairstyle["description"]
    logger.info(
        "job=%s  has_description=%s",
        job_id, bool(description),
    )
    try:
        return await submit_fill_generation(
            selfie_b64=selfie_b64,
            mask_b64=mask_b64,
            hairstyle_name=hairstyle["name"],
            description=description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"BFL API error: {exc}",
        )


@router.get("/{job_id}")
async def poll_job(job_id: str, user=Depends(require_operator_or_admin)):
    job = database.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    bfl_resp = await poll_generation(job["bfl_polling_url"], job["bfl_request_id"])
    bfl_status = bfl_resp.get("status", "")

    if bfl_status == "Ready":
        image_url = bfl_resp.get("result", {}).get("sample")
        if not image_url:
            database.update_job_status(job_id, "failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="BFL returned Ready but no image URL",
            )
        # Fetch and stream the image directly; delete job record (no storage).
        image_bytes = await fetch_image_bytes(image_url)
        database.delete_job(job_id)
        logger.info("job=%s  status=Ready  image_delivered", job_id)
        return Response(content=image_bytes, media_type="image/jpeg")

    elif bfl_status in ("Error", "Failed"):
        database.update_job_status(job_id, "failed")
        logger.warning("job=%s  status=%s  bfl_resp=%r", job_id, bfl_status, bfl_resp)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Generation failed: {bfl_resp}",
        )

    # Still pending — return 202 with status body.
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"job_id": job_id, "status": "pending"},
    )
