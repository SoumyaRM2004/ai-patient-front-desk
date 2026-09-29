from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.doctor import Doctor
    from app.models.patient import Patient
    from app.models.service import Service
    from app.models.user import User


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Asia/Kolkata",
        server_default="Asia/Kolkata",
    )
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
    users: Mapped[list[User]] = relationship(back_populates="clinic")
    doctors: Mapped[list[Doctor]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    services: Mapped[list[Service]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    patients: Mapped[list[Patient]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="clinic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Clinic id={self.id} name={self.name!r} timezone={self.timezone!r}>"
