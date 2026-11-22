"""
Hairstyle image description using Claude Haiku vision.

Called once when an admin uploads a hairstyle reference image.  The returned
description is stored in the database and reused on every generation request,
so the vision API is only ever called once per hairstyle rather than once per
generation job.
"""

import base64
import logging

from backend import config

logger = logging.getLogger(__name__)

_DESCRIPTION_PROMPT = (
    "You are analysing a hairstyle reference image for a hair salon application. "
    "Describe the hairstyle shown in the image in precise detail so that a generative "
    "AI image model can reproduce it accurately. Focus on:\n"
    "- Hair colour (primary colour, highlights, ombre, balayage, etc.)\n"
    "- Hair length (e.g. very short, short, ear-length, chin-length, shoulder-length, "
    "mid-back, waist-length)\n"
    "- Hair texture (straight, wavy, curly, coily, kinky)\n"
    "- Hairstyle and cut (e.g. blunt bob, layered, undercut, pixie, curtain bangs, "
    "side-swept, bun, braids, ponytail, etc.)\n"
    "- Volume and density (fine, thick, voluminous, flat)\n"
    "- Any notable styling details (parting direction, face-framing layers, etc.)\n\n"
    "Write a single concise paragraph (3-5 sentences) suitable for use as part of a "
    "text-to-image prompt. Describe only the hairstyle — do not mention the person's "
    "face, clothing, or background."
)


async def describe_hairstyle(image_bytes: bytes) -> str:
    """
    Send a hairstyle image to Claude Haiku and return a text description.

    Args:
        image_bytes: Raw bytes of the hairstyle image (JPEG, PNG, or WebP).

    Returns:
        A description string (3-5 sentences) suitable for use in a FLUX fill
        prompt in place of or alongside the hairstyle name.

    Raises:
        RuntimeError: If ANTHROPIC_API_KEY is not configured or the call fails.
    """
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "anthropic SDK is not installed.  Run:  pip install anthropic"
        ) from exc

    media_type = _detect_media_type(image_bytes)
    image_b64 = base64.standard_b64encode(image_bytes).decode()

    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    message = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": _DESCRIPTION_PROMPT,
                    },
                ],
            }
        ],
    )

    description = message.content[0].text.strip()
    logger.info("[describe] description generated (%d chars)", len(description))
    return description


def _detect_media_type(data: bytes) -> str:
    """Infer an Anthropic-compatible media_type from image magic bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"  # safe default
