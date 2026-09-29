import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.service import ServiceCreate, ServiceResponse, ServiceUpdate
from app.services import service_service

router = APIRouter(prefix="/api/v1/services", tags=["services"])


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    data: ServiceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new service for the authenticated user's clinic."""
    return await service_service.create_service(
        db,
        clinic_id=current_user.clinic_id,
        data=data,
    )


@router.get("", response_model=list[ServiceResponse])
async def list_services(
    is_active: bool | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all services belonging to the authenticated user's clinic."""
    return await service_service.get_services(
        db,
        clinic_id=current_user.clinic_id,
        is_active=is_active,
    )


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve an individual service belonging to the authenticated user's clinic."""
    return await service_service.get_service_by_id(
        db,
        clinic_id=current_user.clinic_id,
        service_id=service_id,
    )


@router.patch("/{service_id}", response_model=ServiceResponse)
async def update_service(
    service_id: uuid.UUID,
    data: ServiceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a service belonging to the authenticated user's clinic."""
    return await service_service.update_service(
        db,
        clinic_id=current_user.clinic_id,
        service_id=service_id,
        data=data,
    )


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a service belonging to the authenticated user's clinic."""
    await service_service.delete_service(
        db,
        clinic_id=current_user.clinic_id,
        service_id=service_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
