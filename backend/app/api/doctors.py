import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.doctor import DoctorCreate, DoctorResponse, DoctorUpdate
from app.schemas.working_hour import (
    WorkingHourCreate,
    WorkingHourResponse,
    WorkingHourUpdate,
)
from app.services import doctor_service, working_hour_service

router = APIRouter(prefix="/api/v1/doctors", tags=["doctors"])


# ===========================================================================
# Doctors CRUD
# ===========================================================================


@router.post("", response_model=DoctorResponse, status_code=status.HTTP_201_CREATED)
async def create_doctor(
    data: DoctorCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new doctor for the authenticated user's clinic."""
    return await doctor_service.create_doctor(
        db,
        clinic_id=current_user.clinic_id,
        data=data,
    )


@router.get("", response_model=list[DoctorResponse])
async def list_doctors(
    is_active: bool | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all doctors belonging to the authenticated user's clinic."""
    return await doctor_service.get_doctors(
        db,
        clinic_id=current_user.clinic_id,
        is_active=is_active,
    )


@router.get("/{doctor_id}", response_model=DoctorResponse)
async def get_doctor(
    doctor_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve an individual doctor belonging to the authenticated user's clinic."""
    return await doctor_service.get_doctor_by_id(
        db,
        clinic_id=current_user.clinic_id,
        doctor_id=doctor_id,
    )


@router.patch("/{doctor_id}", response_model=DoctorResponse)
async def update_doctor(
    doctor_id: uuid.UUID,
    data: DoctorUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a doctor belonging to the authenticated user's clinic."""
    return await doctor_service.update_doctor(
        db,
        clinic_id=current_user.clinic_id,
        doctor_id=doctor_id,
        data=data,
    )


@router.delete("/{doctor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doctor(
    doctor_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a doctor belonging to the authenticated user's clinic."""
    await doctor_service.delete_doctor(
        db,
        clinic_id=current_user.clinic_id,
        doctor_id=doctor_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ===========================================================================
# Doctor Working Hours
# ===========================================================================


@router.post(
    "/{doctor_id}/working-hours",
    response_model=WorkingHourResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_working_hour(
    doctor_id: uuid.UUID,
    data: WorkingHourCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a working-hour slot for a doctor belonging to the authenticated user's clinic."""
    return await working_hour_service.create_working_hour(
        db,
        clinic_id=current_user.clinic_id,
        doctor_id=doctor_id,
        data=data,
    )


@router.get(
    "/{doctor_id}/working-hours",
    response_model=list[WorkingHourResponse],
)
async def list_working_hours(
    doctor_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List working hours for a doctor belonging to the authenticated user's clinic."""
    return await working_hour_service.get_working_hours(
        db,
        clinic_id=current_user.clinic_id,
        doctor_id=doctor_id,
    )


@router.patch(
    "/{doctor_id}/working-hours/{working_hour_id}",
    response_model=WorkingHourResponse,
)
async def update_working_hour(
    doctor_id: uuid.UUID,
    working_hour_id: uuid.UUID,
    data: WorkingHourUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a working-hour slot for a doctor belonging to the authenticated user's clinic."""
    return await working_hour_service.update_working_hour(
        db,
        clinic_id=current_user.clinic_id,
        doctor_id=doctor_id,
        working_hour_id=working_hour_id,
        data=data,
    )


@router.delete(
    "/{doctor_id}/working-hours/{working_hour_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_working_hour(
    doctor_id: uuid.UUID,
    working_hour_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a working-hour slot for a doctor belonging to the authenticated user's clinic."""
    await working_hour_service.delete_working_hour(
        db,
        clinic_id=current_user.clinic_id,
        doctor_id=doctor_id,
        working_hour_id=working_hour_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
