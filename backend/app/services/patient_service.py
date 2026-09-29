import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.schemas.patient import PatientCreate, PatientUpdate

logger = logging.getLogger(__name__)


async def create_patient(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    data: PatientCreate,
) -> Patient:
    """Create a new patient belonging to the specified clinic."""
    # Check phone uniqueness within the clinic
    existing = await db.execute(
        select(Patient).where(
            Patient.clinic_id == clinic_id,
            Patient.phone == data.phone,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with this phone number already exists in this clinic",
        )

    patient = Patient(
        clinic_id=clinic_id,
        full_name=data.full_name,
        phone=data.phone,
        email=data.email,
        date_of_birth=data.date_of_birth,
        gender=data.gender,
        notes=data.notes,
        is_active=data.is_active,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    logger.info("Created patient %s for clinic %s", patient.id, clinic_id)
    return patient


async def get_patients(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    search: str | None = None,
    is_active: bool | None = None,
) -> list[Patient]:
    """Retrieve patients belonging to the specified clinic with optional search and filter."""
    stmt = select(Patient).where(Patient.clinic_id == clinic_id)

    if is_active is not None:
        stmt = stmt.where(Patient.is_active == is_active)

    if search:
        pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Patient.full_name).like(pattern),
                func.lower(Patient.phone).like(pattern),
                func.lower(Patient.email).like(pattern),
            )
        )

    stmt = stmt.order_by(Patient.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_patient_by_id(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> Patient:
    """Retrieve a patient by ID strictly scoped to the specified clinic.

    Returns 404 if not found or belongs to another tenant.
    """
    stmt = select(Patient).where(
        Patient.id == patient_id,
        Patient.clinic_id == clinic_id,
    )
    result = await db.execute(stmt)
    patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    return patient


async def update_patient(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    data: PatientUpdate,
) -> Patient:
    """Update patient fields. Ensures tenant ownership and clinic-scoped phone uniqueness."""
    patient = await get_patient_by_id(db, clinic_id=clinic_id, patient_id=patient_id)

    update_data = data.model_dump(exclude_unset=True)

    # Check phone uniqueness if phone is changing
    new_phone = update_data.get("phone")
    if new_phone and new_phone != patient.phone:
        existing = await db.execute(
            select(Patient).where(
                Patient.clinic_id == clinic_id,
                Patient.phone == new_phone,
                Patient.id != patient_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A patient with this phone number already exists in this clinic",
            )

    for field, value in update_data.items():
        setattr(patient, field, value)

    await db.commit()
    await db.refresh(patient)

    logger.info("Updated patient %s for clinic %s", patient.id, clinic_id)
    return patient


async def deactivate_patient(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
) -> Patient:
    """Soft-deactivate a patient rather than hard-deleting historical records."""
    patient = await get_patient_by_id(db, clinic_id=clinic_id, patient_id=patient_id)
    patient.is_active = False

    await db.commit()
    await db.refresh(patient)

    logger.info("Deactivated patient %s for clinic %s", patient.id, clinic_id)
    return patient
