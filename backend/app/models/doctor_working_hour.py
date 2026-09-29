from __future__ import annotations

import uuid
from datetime import datetime, time, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.clinic import Clinic
    from app.models.doctor import Doctor


class DoctorWorkingHour(Base):
    __tablename__ = "doctor_working_hours"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
    clinic: Mapped[Clinic] = relationship()
    doctor: Mapped[Doctor] = relationship(back_populates="working_hours")

    __table_args__ = (
        Index("ix_doctor_working_hours_clinic_id", "clinic_id"),
        Index("ix_doctor_working_hours_doctor_id", "doctor_id"),
        Index("ix_doctor_working_hours_doctor_day", "doctor_id", "day_of_week"),
    )

    def __repr__(self) -> str:
        return (
            f"<DoctorWorkingHour id={self.id} doctor_id={self.doctor_id} "
            f"day={self.day_of_week} {self.start_time}-{self.end_time}>"
        )
