import enum


class UserRole(str, enum.Enum):
    """Roles available for clinic users."""

    OWNER = "owner"
    STAFF = "staff"
