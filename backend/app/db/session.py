from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _make_engine():
    # Deferred import so DATABASE_URL is only resolved when first needed,
    # not at module load time (which breaks tests that override settings).
    from app.core.config import settings  # noqa: PLC0415

    return create_engine(settings.DATABASE_URL)


class _LazySessionFactory:
    """Wraps sessionmaker so the engine is created only on first use."""

    _factory: Optional[sessionmaker] = None

    def __call__(self) -> Session:
        if self._factory is None:
            self._factory = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=_make_engine(),
            )
        return self._factory()

    def reset(self) -> None:
        """Force the factory to re-read settings (useful in tests)."""
        self._factory = None


SessionLocal = _LazySessionFactory()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
