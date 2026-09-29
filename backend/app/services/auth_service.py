import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password, create_access_token
from app.models import UserRole
from app.models.clinic import Clinic
from app.models.user import User
from app.schemas.auth import RegisterRequest, RegisterResponse, LoginRequest, TokenResponse

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    """Trim whitespace and lowercase an email address."""
    return email.strip().lower()


async def register_clinic(db: AsyncSession, data: RegisterRequest) -> RegisterResponse:
    """Register a new clinic with its owner user.

    Creates both clinic and owner user in a single transaction.
    Rolls back entirely if any step fails.
    """
    email = normalize_email(data.email)

    # Check email uniqueness
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Create clinic
    clinic = Clinic(name=data.clinic_name)
    db.add(clinic)
    await db.flush()  # Populate clinic.id without committing

    # Create owner user
    user = User(
        clinic_id=clinic.id,
        name=data.owner_name,
        email=email,
        password_hash=hash_password(data.password),
        role=UserRole.OWNER.value,
        is_active=True,
    )
    db.add(user)

    await db.commit()
    await db.refresh(clinic)
    await db.refresh(user)

    logger.info("Registered clinic %s with owner %s", clinic.id, user.id)

    return RegisterResponse(
        clinic_id=clinic.id,
        clinic_name=clinic.name,
        user_id=user.id,
        user_name=user.name,
        email=user.email,
        role=user.role,
    )


async def authenticate_user(db: AsyncSession, data: LoginRequest) -> TokenResponse:
    """Authenticate a user and return a JWT access token.

    Returns a generic error for all failure cases to avoid leaking
    whether an email exists or an account is active.
    """
    email = normalize_email(data.email)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Generic credential error — same message for all failure paths
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None:
        raise credentials_error

    if not verify_password(data.password, user.password_hash):
        raise credentials_error

    if not user.is_active:
        raise credentials_error

    access_token = create_access_token(user.id)

    logger.info("User %s logged in", user.id)

    return TokenResponse(access_token=access_token)
