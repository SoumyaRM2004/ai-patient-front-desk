import logging
import uuid
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.service import Service
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate
from app.services.availability_service import get_clinic_timezone, validate_working_hours

logger = logging.getLogger(__name__)


async def check_appointment_conflict(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    exclude_appointment_id: uuid.UUID | None = None,
) -> None:
    """Check for overlapping appointments for the given doctor in this clinic.

    Overlapping interval formula:
        existing.start_at < requested_end AND existing.end_at > requested_start

    Only non-cancelled appointments block availability.
    Raises HTTPException(409) if a conflict exists.
    """
    stmt = select(Appointment.id).where(
        Appointment.clinic_id == clinic_id,
        Appointment.doctor_id == doctor_id,
        Appointment.status != AppointmentStatus.CANCELLED.value,
        Appointment.start_at < end_at,
        Appointment.end_at > start_at,
    )
    if exclude_appointment_id is not None:
        stmt = stmt.where(Appointment.id != exclude_appointment_id)

    result = await db.execute(stmt)
    conflict = result.scalar_one_or_none()

    if conflict is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Appointment slot conflicts with an existing appointment for this doctor",
        )


async def create_appointment(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    data: AppointmentCreate,
) -> Appointment:
    """Create a new appointment with full validation, working-hour check, and concurrency lock."""
    # 1. Fetch Clinic
    clinic = (
        await db.execute(select(Clinic).where(Clinic.id == clinic_id))
    ).scalar_one_or_none()
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found",
        )

    # 2. Validate Patient
    patient = (
        await db.execute(
            select(Patient).where(
                Patient.id == data.patient_id,
                Patient.clinic_id == clinic_id,
            )
        )
    ).scalar_one_or_none()
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )
    if not patient.is_active:
        raise HTTPException(
            status_code=422,
            detail="Cannot book an appointment for an inactive patient",
        )

    # 3. Validate Doctor
    doctor = (
        await db.execute(
            select(Doctor).where(
                Doctor.id == data.doctor_id,
                Doctor.clinic_id == clinic_id,
            )
        )
    ).scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )
    if not doctor.is_active:
        raise HTTPException(
            status_code=422,
            detail="Cannot book an appointment for an inactive doctor",
        )

    # 4. Validate Service
    service = (
        await db.execute(
            select(Service).where(
                Service.id == data.service_id,
                Service.clinic_id == clinic_id,
            )
        )
    ).scalar_one_or_none()
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )
    if not service.is_active:
        raise HTTPException(
            status_code=422,
            detail="Cannot book an appointment with an inactive service",
        )

    # 5. Derive end_at from service duration
    duration = timedelta(minutes=service.duration_minutes)
    end_at = data.start_at + duration

    # 6. Validate Doctor working hours
    await validate_working_hours(
        db=db,
        clinic=clinic,
        doctor_id=doctor.id,
        start_at=data.start_at,
        end_at=end_at,
    )

    # 7. Concurrency protection: Lock doctor row to serialize concurrent booking for this doctor
    await db.execute(
        select(Doctor.id)
        .where(Doctor.id == doctor.id, Doctor.clinic_id == clinic_id)
        .with_for_update()
    )

    # 8. Check appointment overlap conflict
    await check_appointment_conflict(
        db=db,
        clinic_id=clinic_id,
        doctor_id=doctor.id,
        start_at=data.start_at,
        end_at=end_at,
    )

    # 9. Insert appointment
    appointment = Appointment(
        clinic_id=clinic_id,
        patient_id=data.patient_id,
        doctor_id=data.doctor_id,
        service_id=data.service_id,
        start_at=data.start_at,
        end_at=end_at,
        status=AppointmentStatus.SCHEDULED.value,
        reason=data.reason,
        notes=data.notes,
    )
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)

    logger.info(
        "Created appointment %s for doctor %s and patient %s (clinic %s)",
        appointment.id,
        appointment.doctor_id,
        appointment.patient_id,
        clinic_id,
    )
    return appointment


async def get_appointments(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    appointment_status: AppointmentStatus | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Appointment]:
    """Retrieve appointments for the authenticated clinic with optional filters."""
    stmt = select(Appointment).where(Appointment.clinic_id == clinic_id)

    if doctor_id is not None:
        stmt = stmt.where(Appointment.doctor_id == doctor_id)

    if patient_id is not None:
        stmt = stmt.where(Appointment.patient_id == patient_id)

    if appointment_status is not None:
        stmt = stmt.where(Appointment.status == appointment_status.value)

    if start_date is not None or end_date is not None:
        clinic = (
            await db.execute(select(Clinic).where(Clinic.id == clinic_id))
        ).scalar_one_or_none()
        clinic_tz = get_clinic_timezone(clinic) if clinic else None

        if start_date is not None:
            day_start = (
                datetime.combine(start_date, time.min, tzinfo=clinic_tz)
                if clinic_tz
                else datetime.combine(start_date, time.min)
            )
            stmt = stmt.where(Appointment.start_at >= day_start)

        if end_date is not None:
            day_end = (
                datetime.combine(end_date, time.max, tzinfo=clinic_tz)
                if clinic_tz
                else datetime.combine(end_date, time.max)
            )
            stmt = stmt.where(Appointment.start_at <= day_end)

    stmt = stmt.order_by(Appointment.start_at.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_appointment_by_id(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> Appointment:
    """Retrieve an appointment by ID scoped strictly to the specified clinic."""
    stmt = select(Appointment).where(
        Appointment.id == appointment_id,
        Appointment.clinic_id == clinic_id,
    )
    result = await db.execute(stmt)
    appointment = result.scalar_one_or_none()

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    return appointment


async def update_appointment(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID,
    data: AppointmentUpdate,
) -> Appointment:
    """Update or reschedule an appointment with full validation and conflict detection."""
    appointment = await get_appointment_by_id(
        db,
        clinic_id=clinic_id,
        appointment_id=appointment_id,
    )

    update_dict = data.model_dump(exclude_unset=True)

    # Core scheduling parameters
    is_rescheduling = any(
        k in update_dict for k in ("doctor_id", "service_id", "patient_id", "start_at")
    )

    if is_rescheduling:
        if appointment.status == AppointmentStatus.CANCELLED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reschedule a cancelled appointment",
            )

        eff_doctor_id = update_dict.get("doctor_id", appointment.doctor_id)
        eff_service_id = update_dict.get("service_id", appointment.service_id)
        eff_patient_id = update_dict.get("patient_id", appointment.patient_id)
        eff_start_at = update_dict.get("start_at", appointment.start_at)

        # Validate clinic
        clinic = (
            await db.execute(select(Clinic).where(Clinic.id == clinic_id))
        ).scalar_one_or_none()

        # Validate patient
        patient = (
            await db.execute(
                select(Patient).where(
                    Patient.id == eff_patient_id,
                    Patient.clinic_id == clinic_id,
                )
            )
        ).scalar_one_or_none()
        if patient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found",
            )
        if not patient.is_active:
            raise HTTPException(
                status_code=422,
                detail="Cannot book an appointment for an inactive patient",
            )

        # Validate doctor
        doctor = (
            await db.execute(
                select(Doctor).where(
                    Doctor.id == eff_doctor_id,
                    Doctor.clinic_id == clinic_id,
                )
            )
        ).scalar_one_or_none()
        if doctor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doctor not found",
            )
        if not doctor.is_active:
            raise HTTPException(
                status_code=422,
                detail="Cannot book an appointment for an inactive doctor",
            )

        # Validate service
        service = (
            await db.execute(
                select(Service).where(
                    Service.id == eff_service_id,
                    Service.clinic_id == clinic_id,
                )
            )
        ).scalar_one_or_none()
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found",
            )
        if not service.is_active:
            raise HTTPException(
                status_code=422,
                detail="Cannot book an appointment with an inactive service",
            )

        eff_end_at = eff_start_at + timedelta(minutes=service.duration_minutes)

        # Validate working hours
        await validate_working_hours(
            db=db,
            clinic=clinic,
            doctor_id=doctor.id,
            start_at=eff_start_at,
            end_at=eff_end_at,
        )

        # Lock doctor row
        await db.execute(
            select(Doctor.id)
            .where(Doctor.id == doctor.id, Doctor.clinic_id == clinic_id)
            .with_for_update()
        )

        # Check conflict excluding current appointment
        await check_appointment_conflict(
            db=db,
            clinic_id=clinic_id,
            doctor_id=doctor.id,
            start_at=eff_start_at,
            end_at=eff_end_at,
            exclude_appointment_id=appointment.id,
        )

        appointment.patient_id = eff_patient_id
        appointment.doctor_id = eff_doctor_id
        appointment.service_id = eff_service_id
        appointment.start_at = eff_start_at
        appointment.end_at = eff_end_at

    # Handle remaining non-scheduling fields
    if "status" in update_dict and update_dict["status"] is not None:
        appointment.status = (
            update_dict["status"].value
            if hasattr(update_dict["status"], "value")
            else update_dict["status"]
        )
    if "reason" in update_dict:
        appointment.reason = update_dict["reason"]
    if "notes" in update_dict:
        appointment.notes = update_dict["notes"]

    await db.commit()
    await db.refresh(appointment)

    logger.info("Updated appointment %s for clinic %s", appointment.id, clinic_id)
    return appointment


async def cancel_appointment(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> Appointment:
    """Mark an appointment as CANCELLED."""
    appointment = await get_appointment_by_id(
        db,
        clinic_id=clinic_id,
        appointment_id=appointment_id,
    )
    appointment.status = AppointmentStatus.CANCELLED.value

    await db.commit()
    await db.refresh(appointment)

    logger.info("Cancelled appointment %s for clinic %s", appointment.id, clinic_id)
    return appointment
