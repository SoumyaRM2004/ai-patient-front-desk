import uuid

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    clinic_name: str = Field(..., min_length=1, max_length=255)
    owner_name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    clinic_id: uuid.UUID
    clinic_name: str
    user_id: uuid.UUID
    user_name: str
    email: str
    role: str


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(...)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Current User
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    is_active: bool
    clinic_id: uuid.UUID
    clinic_name: str

    model_config = {"from_attributes": True}
