import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor_working_hour import DoctorWorkingHour
from app.schemas.working_hour import WorkingHourCreate, WorkingHourUpdate
from app.services.doctor_service import get_doctor_by_id

logger = logging.getLogger(__name__)


async def create_working_hour(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
    data: WorkingHourCreate,
) -> DoctorWorkingHour:
    """Create a working-hour slot for a doctor.

    Validates that the doctor exists and belongs to the authenticated clinic.
    """
    # Ensure doctor belongs to this clinic (raises 404 if not found)
    await get_doctor_by_id(db, clinic_id=clinic_id, doctor_id=doctor_id)

    working_hour = DoctorWorkingHour(
        clinic_id=clinic_id,
        doctor_id=doctor_id,
        day_of_week=data.day_of_week,
        start_time=data.start_time,
        end_time=data.end_time,
        is_active=data.is_active,
    )
    db.add(working_hour)
    await db.commit()
    await db.refresh(working_hour)

    logger.info(
        "Created working hour %s for doctor %s (clinic %s)",
        working_hour.id,
        doctor_id,
        clinic_id,
    )
    return working_hour


async def get_working_hours(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
) -> list[DoctorWorkingHour]:
    """Retrieve working hours for a doctor belonging to the specified clinic."""
    # Ensure doctor belongs to this clinic (raises 404 if not found)
    await get_doctor_by_id(db, clinic_id=clinic_id, doctor_id=doctor_id)

    stmt = (
        select(DoctorWorkingHour)
        .where(
            DoctorWorkingHour.doctor_id == doctor_id,
            DoctorWorkingHour.clinic_id == clinic_id,
        )
        .order_by(DoctorWorkingHour.day_of_week.asc(), DoctorWorkingHour.start_time.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_working_hour_by_id(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
    working_hour_id: uuid.UUID,
) -> DoctorWorkingHour:
    """Retrieve a single working-hour record.

    Validates doctor ownership and working-hour record ownership by tenant.
    """
    # Ensure doctor belongs to this clinic
    await get_doctor_by_id(db, clinic_id=clinic_id, doctor_id=doctor_id)

    stmt = select(DoctorWorkingHour).where(
        DoctorWorkingHour.id == working_hour_id,
        DoctorWorkingHour.doctor_id == doctor_id,
        DoctorWorkingHour.clinic_id == clinic_id,
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Working hour record not found",
        )

    return record


async def update_working_hour(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
    working_hour_id: uuid.UUID,
    data: WorkingHourUpdate,
) -> DoctorWorkingHour:
    """Update a working-hour record.

    Ensures doctor ownership, tenant ownership, and that start_time < end_time
    even across partial updates.
    """
    record = await get_working_hour_by_id(
        db,
        clinic_id=clinic_id,
        doctor_id=doctor_id,
        working_hour_id=working_hour_id,
    )

    update_data = data.model_dump(exclude_unset=True)

    # Validate resulting start_time < end_time for partial updates
    new_start = update_data.get("start_time", record.start_time)
    new_end = update_data.get("end_time", record.end_time)
    if new_start >= new_end:
        raise HTTPException(
            status_code=422,
            detail="start_time must be earlier than end_time",
        )

    for field, value in update_data.items():
        setattr(record, field, value)

    await db.commit()
    await db.refresh(record)

    logger.info(
        "Updated working hour %s for doctor %s (clinic %s)",
        record.id,
        doctor_id,
        clinic_id,
    )
    return record


async def delete_working_hour(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
    working_hour_id: uuid.UUID,
) -> None:
    """Delete a working-hour record after validating all tenant and doctor relationships."""
    record = await get_working_hour_by_id(
        db,
        clinic_id=clinic_id,
        doctor_id=doctor_id,
        working_hour_id=working_hour_id,
    )

    await db.delete(record)
    await db.commit()

    logger.info(
        "Deleted working hour %s for doctor %s (clinic %s)",
        working_hour_id,
        doctor_id,
        clinic_id,
    )
