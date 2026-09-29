import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class PatientCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str = Field(..., min_length=1, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=20)
    notes: str | None = None
    is_active: bool = True

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_and_validate_full_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("Patient full_name cannot be empty")
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def strip_and_validate_phone(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("Patient phone cannot be empty")
        return v

    @field_validator("email", "gender", "notes", mode="before")
    @classmethod
    def strip_optional_strings(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class PatientUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, min_length=1, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=20)
    notes: str | None = None
    is_active: bool | None = None

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_and_validate_full_name(cls, v: str | None) -> str | None:
        if v is not None:
            if isinstance(v, str):
                v = v.strip()
            if not v:
                raise ValueError("Patient full_name cannot be empty")
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def strip_and_validate_phone(cls, v: str | None) -> str | None:
        if v is not None:
            if isinstance(v, str):
                v = v.strip()
            if not v:
                raise ValueError("Patient phone cannot be empty")
        return v

    @field_validator("email", "gender", "notes", mode="before")
    @classmethod
    def strip_optional_strings(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class PatientResponse(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    full_name: str
    phone: str
    email: str | None
    date_of_birth: date | None
    gender: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
