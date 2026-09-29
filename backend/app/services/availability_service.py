import logging
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus
from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.doctor_working_hour import DoctorWorkingHour
from app.models.service import Service
from app.schemas.appointment import AvailableSlot, AvailableSlotsResponse

logger = logging.getLogger(__name__)


def get_clinic_timezone(clinic: Clinic) -> ZoneInfo:
    """Retrieve ZoneInfo object for the clinic's configured timezone string."""
    try:
        return ZoneInfo(clinic.timezone)
    except Exception:
        logger.warning(
            "Invalid clinic timezone %r, defaulting to Asia/Kolkata",
            getattr(clinic, "timezone", None),
        )
        return ZoneInfo("Asia/Kolkata")


async def validate_working_hours(
    db: AsyncSession,
    clinic: Clinic,
    doctor_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
) -> None:
    """Ensure the requested appointment fits entirely within one doctor working-hour slot.

    Converts timestamps to the clinic's local timezone.
    Validates that:
    1. The appointment starts and ends on the same calendar day.
    2. The doctor has working hours on that day of week.
    3. The interval [local_start, local_end] is completely enclosed within an active working slot.
    """
    clinic_tz = get_clinic_timezone(clinic)
    local_start = start_at.astimezone(clinic_tz)
    local_end = end_at.astimezone(clinic_tz)

    if local_start.date() != local_end.date():
        raise HTTPException(
            status_code=422,
            detail="Appointment cannot span across multiple calendar days",
        )

    weekday = local_start.weekday()  # Monday=0, Sunday=6

    stmt = select(DoctorWorkingHour).where(
        DoctorWorkingHour.clinic_id == clinic.id,
        DoctorWorkingHour.doctor_id == doctor_id,
        DoctorWorkingHour.day_of_week == weekday,
        DoctorWorkingHour.is_active.is_(True),
    )
    result = await db.execute(stmt)
    slots = result.scalars().all()

    if not slots:
        raise HTTPException(
            status_code=422,
            detail="Appointment is outside doctor working hours (no active hours on this day)",
        )

    req_start_time = local_start.time()
    req_end_time = local_end.time()

    # Must fit completely within AT LEAST ONE working-hour interval
    fits = any(
        wh.start_time <= req_start_time and req_end_time <= wh.end_time
        for wh in slots
    )

    if not fits:
        raise HTTPException(
            status_code=422,
            detail="Appointment is outside doctor working hours",
        )


async def get_available_slots(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    doctor_id: uuid.UUID,
    service_id: uuid.UUID,
    target_date: date,
    slot_step_minutes: int = 15,
) -> AvailableSlotsResponse:
    """Calculate deterministic available appointment slots for a doctor and service on a date."""
    # 1. Verify Clinic
    clinic = (
        await db.execute(select(Clinic).where(Clinic.id == clinic_id))
    ).scalar_one_or_none()
    if clinic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clinic not found",
        )

    # 2. Verify Doctor
    doctor = (
        await db.execute(
            select(Doctor).where(Doctor.id == doctor_id, Doctor.clinic_id == clinic_id)
        )
    ).scalar_one_or_none()
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )
    if not doctor.is_active:
        return AvailableSlotsResponse(
            doctor_id=doctor_id,
            service_id=service_id,
            date=target_date,
            slots=[],
        )

    # 3. Verify Service
    service = (
        await db.execute(
            select(Service).where(Service.id == service_id, Service.clinic_id == clinic_id)
        )
    ).scalar_one_or_none()
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )
    if not service.is_active:
        return AvailableSlotsResponse(
            doctor_id=doctor_id,
            service_id=service_id,
            date=target_date,
            slots=[],
        )

    clinic_tz = get_clinic_timezone(clinic)
    weekday = target_date.weekday()

    # 4. Fetch Doctor working hours for weekday
    wh_stmt = (
        select(DoctorWorkingHour)
        .where(
            DoctorWorkingHour.clinic_id == clinic_id,
            DoctorWorkingHour.doctor_id == doctor_id,
            DoctorWorkingHour.day_of_week == weekday,
            DoctorWorkingHour.is_active.is_(True),
        )
        .order_by(DoctorWorkingHour.start_time.asc())
    )
    working_hours = (await db.execute(wh_stmt)).scalars().all()

    if not working_hours:
        return AvailableSlotsResponse(
            doctor_id=doctor_id,
            service_id=service_id,
            date=target_date,
            slots=[],
        )

    service_duration = timedelta(minutes=service.duration_minutes)
    step = timedelta(minutes=slot_step_minutes)

    # 5. Fetch blocking appointments for this doctor on target_date
    day_start = datetime.combine(target_date, time.min, tzinfo=clinic_tz)
    day_end = datetime.combine(target_date, time.max, tzinfo=clinic_tz)

    appt_stmt = select(Appointment).where(
        Appointment.clinic_id == clinic_id,
        Appointment.doctor_id == doctor_id,
        Appointment.status != AppointmentStatus.CANCELLED.value,
        Appointment.start_at < day_end,
        Appointment.end_at > day_start,
    )
    blocking_appts = (await db.execute(appt_stmt)).scalars().all()

    # 6. Generate candidate slots and filter overlaps
    available_slots: list[AvailableSlot] = []

    for wh in working_hours:
        interval_start_dt = datetime.combine(target_date, wh.start_time, tzinfo=clinic_tz)
        interval_end_dt = datetime.combine(target_date, wh.end_time, tzinfo=clinic_tz)

        current_slot_start = interval_start_dt
        while current_slot_start + service_duration <= interval_end_dt:
            current_slot_end = current_slot_start + service_duration

            # Check overlap with any blocking appointment
            has_conflict = any(
                current_slot_start < appt.end_at and current_slot_end > appt.start_at
                for appt in blocking_appts
            )

            if not has_conflict:
                available_slots.append(
                    AvailableSlot(start_at=current_slot_start, end_at=current_slot_end)
                )

            current_slot_start += step

    return AvailableSlotsResponse(
        doctor_id=doctor_id,
        service_id=service_id,
        date=target_date,
        slots=available_slots,
    )
