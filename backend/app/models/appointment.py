from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.clinic import Clinic
    from app.models.doctor import Doctor
    from app.models.patient import Patient
    from app.models.service import Service


class AppointmentStatus(str, enum.Enum):
    """Lifecycle statuses for appointments."""

    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
    )
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AppointmentStatus.SCHEDULED.value,
        server_default=AppointmentStatus.SCHEDULED.value,
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    clinic: Mapped[Clinic] = relationship(back_populates="appointments")
    patient: Mapped[Patient] = relationship(back_populates="appointments")
    doctor: Mapped[Doctor] = relationship(back_populates="appointments")
    service: Mapped[Service] = relationship(back_populates="appointments")

    __table_args__ = (
        Index("ix_appointments_clinic_id", "clinic_id"),
        Index("ix_appointments_patient_id", "patient_id"),
        Index("ix_appointments_doctor_id", "doctor_id"),
        Index("ix_appointments_service_id", "service_id"),
        Index("ix_appointments_start_at", "start_at"),
        Index("ix_appointments_status", "status"),
        Index("ix_appointments_doctor_start_at", "doctor_id", "start_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Appointment id={self.id} doctor_id={self.doctor_id} "
            f"patient_id={self.patient_id} start_at={self.start_at} status={self.status}>"
        )
