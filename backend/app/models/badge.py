"""
Badge model — stores earned achievements / milestones.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# ── Available badge types ──
BADGE_TYPES = { 
    "first_run":         "Completed your first run",
    "distance_10km":     "Ran a total of 10 km",
    "distance_50km":     "Ran a total of 50 km",
    "distance_100km":    "Ran a total of 100 km",
    "territory_1sqkm":   "Claimed 1 km² of territory",
    "territory_5sqkm":   "Claimed 5 km² of territory",
    "streak_7":          "7‑day running streak",
    "streak_30":         "30‑day running streak",
    "top10_city":        "Top 10 in your city",
}


class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    badge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # ── Relationships ──
    user = relationship("User", back_populates="badges")

    def __repr__(self) -> str:
        return f"<Badge {self.badge_type} user={self.user_id}>"
