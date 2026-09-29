import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.appointment import AppointmentStatus
from app.models.user import User
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    AvailableSlotsResponse,
)
from app.services import appointment_service, availability_service

router = APIRouter(prefix="/api/v1/appointments", tags=["appointments"])


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    data: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new appointment for the authenticated clinic with deterministic validation."""
    return await appointment_service.create_appointment(
        db,
        clinic_id=current_user.clinic_id,
        data=data,
    )


@router.get("", response_model=list[AppointmentResponse])
async def list_appointments(
    doctor_id: uuid.UUID | None = Query(default=None),
    patient_id: uuid.UUID | None = Query(default=None),
    appointment_status: AppointmentStatus | None = Query(default=None, alias="status"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List appointments belonging to the authenticated clinic with optional filters."""
    return await appointment_service.get_appointments(
        db,
        clinic_id=current_user.clinic_id,
        doctor_id=doctor_id,
        patient_id=patient_id,
        appointment_status=appointment_status,
        start_date=start_date,
        end_date=end_date,
    )


# CRITICAL ROUTE ORDERING: Define /available-slots BEFORE /{appointment_id}
@router.get("/available-slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    doctor_id: uuid.UUID = Query(..., description="Doctor ID"),
    service_id: uuid.UUID = Query(..., description="Service ID"),
    target_date: date = Query(..., alias="date", description="Date in YYYY-MM-DD format"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deterministic slot availability computation for a doctor and service on a date."""
    return await availability_service.get_available_slots(
        db,
        clinic_id=current_user.clinic_id,
        doctor_id=doctor_id,
        service_id=service_id,
        target_date=target_date,
    )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve an individual appointment belonging to the authenticated clinic."""
    return await appointment_service.get_appointment_by_id(
        db,
        clinic_id=current_user.clinic_id,
        appointment_id=appointment_id,
    )


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: uuid.UUID,
    data: AppointmentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update or reschedule an appointment belonging to the authenticated clinic."""
    return await appointment_service.update_appointment(
        db,
        clinic_id=current_user.clinic_id,
        appointment_id=appointment_id,
        data=data,
    )


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_appointment(
    appointment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an appointment without deleting historical records."""
    return await appointment_service.cancel_appointment(
        db,
        clinic_id=current_user.clinic_id,
        appointment_id=appointment_id,
    )
