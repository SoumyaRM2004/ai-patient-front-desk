import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DoctorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    specialty: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def strip_and_validate_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("Doctor name cannot be empty")
        return v

    @field_validator("specialty", "phone", "email", mode="before")
    @classmethod
    def strip_optional_strings(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class DoctorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    specialty: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_and_validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            if isinstance(v, str):
                v = v.strip()
            if not v:
                raise ValueError("Doctor name cannot be empty")
        return v

    @field_validator("specialty", "phone", "email", mode="before")
    @classmethod
    def strip_optional_strings(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class DoctorResponse(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    name: str
    specialty: str | None
    phone: str | None
    email: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
