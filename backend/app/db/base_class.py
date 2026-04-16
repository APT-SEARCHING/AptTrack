from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Shared metadata instance so Alembic can discover all tables.
metadata = MetaData()


class Base(DeclarativeBase):
    """Declarative base for all ORM models (SQLAlchemy 2.0 style)."""
    metadata = metadata
