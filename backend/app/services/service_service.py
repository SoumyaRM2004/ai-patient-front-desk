import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceUpdate

logger = logging.getLogger(__name__)


async def create_service(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    data: ServiceCreate,
) -> Service:
    """Create a new service belonging to the specified clinic."""
    service = Service(
        clinic_id=clinic_id,
        name=data.name,
        description=data.description,
        duration_minutes=data.duration_minutes,
        price=data.price,
        is_active=data.is_active,
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)

    logger.info("Created service %s for clinic %s", service.id, clinic_id)
    return service


async def get_services(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    is_active: bool | None = None,
) -> list[Service]:
    """Retrieve all services belonging to the specified clinic."""
    stmt = select(Service).where(Service.clinic_id == clinic_id)
    if is_active is not None:
        stmt = stmt.where(Service.is_active == is_active)
    stmt = stmt.order_by(Service.created_at.asc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_service_by_id(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    service_id: uuid.UUID,
) -> Service:
    """Retrieve a service by ID scoped strictly to the specified clinic.

    Returns 404 if the service does not exist or belongs to another tenant.
    """
    stmt = select(Service).where(
        Service.id == service_id,
        Service.clinic_id == clinic_id,
    )
    result = await db.execute(stmt)
    service = result.scalar_one_or_none()

    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    return service


async def update_service(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    service_id: uuid.UUID,
    data: ServiceUpdate,
) -> Service:
    """Update a service's fields. Ensures tenant ownership and immutability of clinic_id."""
    service = await get_service_by_id(db, clinic_id=clinic_id, service_id=service_id)

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)

    await db.commit()
    await db.refresh(service)

    logger.info("Updated service %s for clinic %s", service.id, clinic_id)
    return service


async def delete_service(
    db: AsyncSession,
    clinic_id: uuid.UUID,
    service_id: uuid.UUID,
) -> None:
    """Delete a service belonging to the specified clinic."""
    service = await get_service_by_id(db, clinic_id=clinic_id, service_id=service_id)

    try:
        await db.delete(service)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete service with existing appointments",
        ) from exc

    logger.info("Deleted service %s for clinic %s", service_id, clinic_id)
