"""BFL image editor adapters and asynchronous result retrieval."""
import httpx
from backend import config

_HEADERS = {"accept": "application/json"}

def payload(model, selfie, reference, brief, colour):
    prompt = (
        "Edit only the hairstyle of the person in image 1. Preserve their facial geometry, "
        "eyes, nose, skin, expression, glasses, clothing, pose, camera and background. "
        + brief + " Hair colour: " + colour + "."
    )
    if model == "flux-3-image":
        images = [selfie, reference] if reference else [selfie]
        return {"prompt": prompt, "images": images, "grounding": False}
    if model not in ("flux-2-pro", "flux-2-max"):
        raise ValueError("Unsupported image editor")
    data = {"prompt": prompt, "input_image": selfie, "output_format": "jpeg"}
    if reference:
        data["input_image_2"] = reference
    return data

async def submit_generation(selfie, reference, brief, colour):
    data = payload(config.BFL_MODEL, selfie, reference, brief, colour)
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{config.BFL_API_BASE}/{config.BFL_MODEL}",
            headers={"x-key": config.BFL_API_KEY}, json=data,
        )
        response.raise_for_status()
        return response.json()

async def poll_generation(polling_url: str, request_id: str) -> dict:
    """
    Poll BFL for the status of a generation request.

    Returns the raw BFL response dict; caller inspects ['status'] and
    ['result']['sample'] (a URL to the generated image).

    Possible status values: 'Pending', 'Ready', 'Error', 'Failed'.
    """
    if not config.BFL_API_KEY:
        raise ValueError("BFL_API_KEY is not configured")

    headers = {**_HEADERS, "x-key": config.BFL_API_KEY}
    

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(polling_url, headers=headers)
        response.raise_for_status()
        return response.json()


async def fetch_image_bytes(image_url: str) -> bytes:
    """Download the generated image from the BFL CDN URL."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(image_url)
        response.raise_for_status()
        return response.content
