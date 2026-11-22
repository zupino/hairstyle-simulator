"""
Async client for the Black Forest Labs FLUX API.

Two generation functions are provided, corresponding to the two supported
backends (selected via GENERATION_BACKEND in config):

  submit_generation()      — bfl_standard: two-image approach (selfie + hairstyle
                             reference image); no mask required.
  submit_fill_generation() — bfl_fill: inpainting approach (selfie + hair mask +
                             text prompt); uses flux-pro-1.0-fill.
"""

import httpx
from backend import config

_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
}

# Legacy two-image prompt (kept for reference).
_LEGACY_PROMPT = (
    "A professional high-resolution photograph "
    "of the person from image 1, strictly maintaining their "
    "exact facial features, skin tone, and identity, "
    "but precisely matching the hairstyle and hair color from image 2."
)

# Fill prompt used when a detailed description is available (preferred).
_FILL_PROMPT_WITH_DESCRIPTION = (
    "Apply the following hairstyle to the person: {description} "
    "The hairstyle is called '{hairstyle_name}'. "
    "Keep all facial features, skin tone, facial structure, and background "
    "exactly the same. The new hair should look natural, well-lit, and "
    "seamlessly integrated with the rest of the photo."
)

# Fallback fill prompt used when no description is available.
_FILL_PROMPT_NAME_ONLY = (
    "Replace only the hair of the person with a {hairstyle_name} hairstyle. "
    "Keep all facial features, skin tone, facial structure, and background "
    "exactly the same. The new hair should look natural, well-lit, and "
    "seamlessly integrated with the rest of the photo."
)


# ---------------------------------------------------------------------------
# Two-image generation  (bfl_standard backend)
# ---------------------------------------------------------------------------

async def submit_generation(selfie_b64: str, hairstyle_b64: str) -> dict:
    """
    Submit a generation request to BFL using the two-image approach
    (bfl_standard backend).  Sends the selfie and hairstyle reference image
    together and asks the model to transfer the hairstyle.

    Returns the raw BFL response dict which must contain:
      - id            (request_id)
      - polling_url
    """
    if not config.BFL_API_KEY:
        raise ValueError("BFL_API_KEY is not configured")

    url = f"{config.BFL_API_BASE}/{config.BFL_MODEL}"
    payload = {
        "prompt": _LEGACY_PROMPT,
        "input_image": selfie_b64,
        "input_image_2": hairstyle_b64,
    }
    headers = {**_HEADERS, "x-key": config.BFL_API_KEY}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Inpainting fill generation  (bfl_fill backend)
# ---------------------------------------------------------------------------

async def submit_fill_generation(
    selfie_b64: str,
    mask_b64: str,
    hairstyle_name: str,
    hairstyle_b64: str | None = None,
    description: str | None = None,
) -> dict:
    """
    Submit an inpainting fill request to BFL using flux-pro-1.0-fill.

    The masked region is replaced with a hairstyle described by `description`
    (when available) or `hairstyle_name` as a fallback.

    Args:
        selfie_b64:     Base64-encoded PNG of the selfie (input image).
        mask_b64:       Base64-encoded PNG of the hair mask (white = inpaint).
        hairstyle_name: Human-readable name, always included in the prompt.
        hairstyle_b64:  Unused — kept for API compatibility.
        description:    Detailed hairstyle description from Claude Haiku; when
                        provided this is used as the primary prompt content.

    Returns:
        Raw BFL response dict containing 'id' and 'polling_url'.
    """
    if not config.BFL_API_KEY:
        raise ValueError("BFL_API_KEY is not configured")

    url = f"{config.BFL_API_BASE}/{config.BFL_FILL_MODEL}"

    if description:
        prompt = _FILL_PROMPT_WITH_DESCRIPTION.format(
            description=description,
            hairstyle_name=hairstyle_name,
        )
    else:
        prompt = _FILL_PROMPT_NAME_ONLY.format(hairstyle_name=hairstyle_name)

    payload: dict = {
        "image": selfie_b64,
        "mask": mask_b64,
        "prompt": prompt,
        "steps": 50,
        "guidance": 30,
        "output_format": "jpeg",
        "safety_tolerance": 2,
    }

    headers = {**_HEADERS, "x-key": config.BFL_API_KEY}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Shared poll / fetch helpers
# ---------------------------------------------------------------------------

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
    params = {"id": request_id}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(polling_url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


async def fetch_image_bytes(image_url: str) -> bytes:
    """Download the generated image from the BFL CDN URL."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(image_url)
        response.raise_for_status()
        return response.content
