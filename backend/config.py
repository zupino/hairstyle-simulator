"""
Application settings loaded from environment variables.

Required:
  BFL_API_KEY   — Black Forest Labs API key
  SECRET_KEY    — JWT signing secret (generate once: python -c "import secrets; print(secrets.token_hex(32))")

Generation backend (GENERATION_BACKEND):
  Selects which image generation pipeline to use.  Default: bfl_fill

  bfl_fill      — BFL inpainting fill (flux-pro-1.0-fill).
                  Generates a hair mask from the selfie, then calls the BFL fill
                  model to inpaint only the masked region.  The hairstyle is
                  described via a text prompt (derived from the hairstyle name
                  and optional Claude Haiku description).  Controlled by:
                    BFL_FILL_MODEL  — model ID (default: flux-pro-1.0-fill)
                    MASK_STRATEGY   — mask generation strategy (see below)

  bfl_standard  — BFL two-image approach (flux-2-pro / flux-1.1-pro / etc.).
                  Sends the selfie and the hairstyle reference image together to
                  the BFL FLUX model and asks it to transfer the hairstyle.
                  No mask is generated.  Controlled by:
                    BFL_MODEL       — model ID (default: flux-2-pro)
                                      Alternatives: flux-1.1-pro (~30% cheaper),
                                      flux-1-schnell (cheapest, lower quality)

Optional:
  BFL_MODEL         — BFL model for the bfl_standard backend (default: flux-2-pro)
  BFL_FILL_MODEL    — BFL model for the bfl_fill backend (default: flux-pro-1.0-fill)
  ACCESS_TOKEN_TTL  — JWT lifetime in seconds (default: 3600)
  STORAGE_PATH      — Directory for persisted hairstyle images (default: ./storage/hairstyles)
  DB_PATH           — SQLite database file path (default: ./hairstyle_simulator.db)
  MASK_STRATEGY     — Mask generation strategy for the bfl_fill backend (default: hair)
                        hair         — inpaint only the detected hair region; cannot extend hair
                                       beyond the original boundaries (short→long will be clipped)
                        head_region  — inpaint an expanded bounding box around the head while
                                       preserving face-skin pixels; allows any hairstyle length;
                                       background and clothing outside the box are also preserved
                        face_only    — inpaint the entire image except face-skin pixels; maximum
                                       freedom for the model (any length/shape hairstyle); only
                                       facial identity is guaranteed, background may change
  DEBUG_MASK_DIR    — If set, diagnostic PNG images (selfie, segmentation map, raw mask, final
                      mask) are saved to this directory for every generation request.
                      Only used by the bfl_fill backend.
                      Empty string (default) disables debug image saving.
  ANTHROPIC_API_KEY — Anthropic API key used to generate hairstyle descriptions via Claude
                      Haiku at upload time.  Required for the description feature; if absent
                      the upload still succeeds but no description is stored.
                      Only used by the bfl_fill backend (prompt-based generation).
"""

import os

BFL_API_KEY: str = os.environ.get("BFL_API_KEY", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
GENERATION_BACKEND: str = os.environ.get("GENERATION_BACKEND", "bfl_fill")
BFL_MODEL: str = os.environ.get("BFL_MODEL", "flux-2-max")
BFL_FILL_MODEL: str = os.environ.get("BFL_FILL_MODEL", "flux-pro-1.0-fill")
ACCESS_TOKEN_TTL: int = int(os.environ.get("ACCESS_TOKEN_TTL", "3600"))
STORAGE_PATH: str = os.environ.get("STORAGE_PATH", "./storage/hairstyles")
DB_PATH: str = os.environ.get("DB_PATH", "./hairstyle_simulator.db")
MASK_STRATEGY: str = os.environ.get("MASK_STRATEGY", "hair")   # "hair" | "head_region" | "face_only"
DEBUG_MASK_DIR: str = os.environ.get("DEBUG_MASK_DIR", "")      # empty = disabled

BFL_API_BASE = "https://api.bfl.ai/v1"

ALGORITHM = "HS256"

_VALID_BACKENDS = {"bfl_fill", "bfl_standard"}

def validate() -> list[str]:
    """Return a list of configuration error strings (empty = OK)."""
    errors: list[str] = []
    if not BFL_API_KEY:
        errors.append("BFL_API_KEY is not set")
    if not SECRET_KEY:
        errors.append("SECRET_KEY is not set")
    if GENERATION_BACKEND not in _VALID_BACKENDS:
        errors.append(
            f"GENERATION_BACKEND={GENERATION_BACKEND!r} is not valid; "
            f"choose one of: {', '.join(sorted(_VALID_BACKENDS))}"
        )
    return errors
