from sqlalchemy import Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base_class import Base


class ApartmentFavorite(Base):
    __tablename__ = "apartment_favorites"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    apartment_id = Column(
        Integer, ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "apartment_id", name="uq_favorites_user_apt"),)
