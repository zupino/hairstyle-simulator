"""
Pydantic request/response schemas.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class OperatorCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class OperatorUpdate(BaseModel):
    is_active: bool


class OperatorOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: str


# ---------------------------------------------------------------------------
# Hairstyles
# ---------------------------------------------------------------------------

class HairstyleOut(BaseModel):
    id: int
    name: str
    filename: str
    uploaded_by: int | None
    created_at: str | None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Generation jobs
# ---------------------------------------------------------------------------

class GenerateResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | ready | failed
