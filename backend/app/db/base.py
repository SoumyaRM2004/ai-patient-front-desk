from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models.

    All ORM models must inherit from this class so that Alembic
    can detect them via Base.metadata for auto-generating migrations.
    """

    pass
