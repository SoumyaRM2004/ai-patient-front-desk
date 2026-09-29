import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    duration_minutes: int = Field(..., gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def strip_and_validate_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("Service name cannot be empty")
        return v

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_and_validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            if isinstance(v, str):
                v = v.strip()
            if not v:
                raise ValueError("Service name cannot be empty")
        return v

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class ServiceResponse(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    name: str
    description: str | None
    duration_minutes: int
    price: Decimal | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
