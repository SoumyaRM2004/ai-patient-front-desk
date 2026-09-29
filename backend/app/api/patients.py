import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate
from app.services import patient_service

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(
    data: PatientCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new patient for the authenticated user's clinic."""
    return await patient_service.create_patient(
        db,
        clinic_id=current_user.clinic_id,
        data=data,
    )


@router.get("", response_model=list[PatientResponse])
async def list_patients(
    search: str | None = Query(default=None, description="Search by name, phone, or email"),
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all patients belonging to the authenticated user's clinic with optional search."""
    return await patient_service.get_patients(
        db,
        clinic_id=current_user.clinic_id,
        search=search,
        is_active=is_active,
    )


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve an individual patient belonging to the authenticated user's clinic."""
    return await patient_service.get_patient_by_id(
        db,
        clinic_id=current_user.clinic_id,
        patient_id=patient_id,
    )


@router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: uuid.UUID,
    data: PatientUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a patient belonging to the authenticated user's clinic."""
    return await patient_service.update_patient(
        db,
        clinic_id=current_user.clinic_id,
        patient_id=patient_id,
        data=data,
    )


@router.delete("/{patient_id}", response_model=PatientResponse)
async def delete_patient(
    patient_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a patient (soft delete) to preserve historical data."""
    return await patient_service.deactivate_patient(
        db,
        clinic_id=current_user.clinic_id,
        patient_id=patient_id,
    )
