"""Submit edits, then poll for the result as the authenticated operator."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal
from pydantic import ValidationError
from services.consultation import Preferences, suggest
from typing import Annotated
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import JSONResponse, Response
from backend import database
from services import catalogue
from backend.auth import require_operator_or_admin
from backend.models import GenerateResponse
from services.image import read_image, jpeg, encoded
from services.bfl import submit_generation, poll_generation, fetch_image_bytes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/generate", tags=["generation"])


@router.post("/suggest")
async def suggestions(selfie: Annotated[UploadFile, File()], preferences: Annotated[str, Form()],
                      user=Depends(require_operator_or_admin)):
    try:
        prefs = Preferences.model_validate_json(preferences)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid consultation preferences") from exc
    return suggest(await read_image(selfie), prefs)


@router.post("", response_model=GenerateResponse, status_code=202)
async def submit_job(
    selfie: Annotated[UploadFile, File()],
    hairstyle_id: Annotated[int | None, Form()] = None,
    mode: Annotated[Literal["reference", "suggest"], Form()] = "reference",
    cut: Annotated[str, Form(max_length=1200)] = "",
    colour: Annotated[str, Form(max_length=64)] = "original",
    user=Depends(require_operator_or_admin),
):
    reference = None
    if mode == "reference":
        style = catalogue.get(hairstyle_id) if hairstyle_id is not None else None
        if style is None:
            raise HTTPException(404, "Select a catalogue haircut")
        reference = encoded(catalogue.path(style, prepared=True).read_bytes())
        brief = "Copy only the haircut, texture and silhouette in image 2."
    else:
        if hairstyle_id is not None or not cut.strip() or colour == "reference":
            raise HTTPException(422, "Select a suggested cut and a selfie-compatible colour")
        brief = "Apply this haircut: " + cut.strip()
    colour = {"original": "keep the colour from image 1", "reference": "match image 2"}.get(colour, colour)
    image = await read_image(selfie)
    try:
        result = await submit_generation(encoded(jpeg(image)), reference, brief, colour)
        request_id, polling_url = result["id"], result["polling_url"]
    except (httpx.HTTPError, KeyError) as exc:
        raise HTTPException(502, "Image editor could not accept the request") from exc
    job_id = uuid.uuid4().hex
    database.create_job(job_id, request_id, polling_url, user["id"], datetime.now(timezone.utc).isoformat())
    return GenerateResponse(job_id=job_id)


@router.get("/{job_id}")
async def poll_job(job_id: str, user=Depends(require_operator_or_admin)):
    job = database.get_job(job_id)
    if job is None or job["operator_id"] != user["id"]:
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

    elif bfl_status in ("Error", "Failed", "Request Moderated", "Content Moderated", "Task not found"):
        database.update_job_status(job_id, "failed")
        logger.warning("job=%s  status=%s  bfl_resp=%r", job_id, bfl_status, bfl_resp)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Generation failed: {bfl_status}",
        )

    # Still pending — return 202 with status body.
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"job_id": job_id, "status": "pending"},
    )
