import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor import Doctor
from app.schemas.doctor import DoctorCreate, DoctorUpdate

logger = logging.getLogger(__name__)


async def create_doctor(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    data: DoctorCreate,
) -> Doctor:
    """Create a new doctor belonging to the specified clinic."""
    doctor = Doctor(
        clinic_id=clinic_id,
        name=data.name,
        specialty=data.specialty,
        phone=data.phone,
        email=data.email,
        is_active=data.is_active,
    )
    db.add(doctor)
    await db.commit()
    await db.refresh(doctor)

    logger.info("Created doctor %s for clinic %s", doctor.id, clinic_id)
    return doctor


async def get_doctors(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    is_active: bool | None = None,
) -> list[Doctor]:
    """Retrieve all doctors belonging to the specified clinic."""
    stmt = select(Doctor).where(Doctor.clinic_id == clinic_id)
    if is_active is not None:
        stmt = stmt.where(Doctor.is_active == is_active)
    stmt = stmt.order_by(Doctor.created_at.asc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_doctor_by_id(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
) -> Doctor:
    """Retrieve a doctor by ID scoped strictly to the specified clinic.

    Returns 404 if the doctor does not exist or belongs to another tenant.
    """
    stmt = select(Doctor).where(
        Doctor.id == doctor_id,
        Doctor.clinic_id == clinic_id,
    )
    result = await db.execute(stmt)
    doctor = result.scalar_one_or_none()

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    return doctor


async def update_doctor(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
    data: DoctorUpdate,
) -> Doctor:
    """Update a doctor's fields. Ensures tenant ownership and immutability of clinic_id."""
    doctor = await get_doctor_by_id(db, clinic_id=clinic_id, doctor_id=doctor_id)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(doctor, field, value)

    await db.commit()
    await db.refresh(doctor)

    logger.info("Updated doctor %s for clinic %s", doctor.id, clinic_id)
    return doctor


async def delete_doctor(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
) -> None:
    """Delete a doctor. Dependent working hours cascade at the database level."""
    doctor = await get_doctor_by_id(db, clinic_id=clinic_id, doctor_id=doctor_id)

    await db.delete(doctor)
    await db.commit()

    logger.info("Deleted doctor %s for clinic %s", doctor_id, clinic_id)
