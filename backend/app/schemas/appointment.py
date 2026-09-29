import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.models.appointment import AppointmentStatus


class AppointmentCreate(BaseModel):
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    service_id: uuid.UUID
    start_at: datetime
    reason: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @field_validator("start_at")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError(
                "Timestamp must be timezone-aware (e.g. including UTC 'Z' or offset '+05:30')"
            )
        return v

    @field_validator("reason", "notes", mode="before")
    @classmethod
    def strip_optional_strings(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class AppointmentUpdate(BaseModel):
    patient_id: uuid.UUID | None = None
    doctor_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    start_at: datetime | None = None
    status: AppointmentStatus | None = None
    reason: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @field_validator("start_at")
    @classmethod
    def validate_timezone_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None:
            if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
                raise ValueError(
                    "Timestamp must be timezone-aware (e.g. including UTC 'Z' or offset '+05:30')"
                )
        return v

    @field_validator("reason", "notes", mode="before")
    @classmethod
    def strip_optional_strings(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    clinic_id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID
    service_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    status: str
    reason: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AvailableSlot(BaseModel):
    start_at: datetime
    end_at: datetime


class AvailableSlotsResponse(BaseModel):
    doctor_id: uuid.UUID
    service_id: uuid.UUID
    date: date
    slots: list[AvailableSlot]
