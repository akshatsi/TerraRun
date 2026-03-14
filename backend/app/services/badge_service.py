"""
Badge service — check and award milestone badges after a run.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.badge import BADGE_TYPES, Badge
from app.models.user import User


async def _has_badge(db: AsyncSession, user_id, badge_type: str) -> bool:
    result = await db.execute(
        select(Badge).where(Badge.user_id == user_id, Badge.badge_type == badge_type)
    )
    return result.scalar_one_or_none() is not None


async def _award(db: AsyncSession, user_id, badge_type: str) -> Badge | None:
    if await _has_badge(db, user_id, badge_type):
        return None
    badge = Badge(user_id=user_id, badge_type=badge_type)
    db.add(badge)
    await db.flush()
    return badge


async def check_badges_after_run(db: AsyncSession, user: User) -> list[str]:
    """
    Check all milestone conditions and award any newly‑earned badges.
    Returns a list of newly awarded badge_type strings.
    """
    awarded = []

    # First run
    b = await _award(db, user.id, "first_run")
    if b:
        awarded.append(b.badge_type)

    # Distance milestones (cumulative, in metres)
    dist_km = user.total_distance_m / 1000
    if dist_km >= 10:
        b = await _award(db, user.id, "distance_10km")
        if b:
            awarded.append(b.badge_type)
    if dist_km >= 50:
        b = await _award(db, user.id, "distance_50km")
        if b:
            awarded.append(b.badge_type)
    if dist_km >= 100:
        b = await _award(db, user.id, "distance_100km")
        if b:
            awarded.append(b.badge_type)

    # Territory milestones (in m²)
    area_km2 = user.territory_area_m2 / 1_000_000
    if area_km2 >= 1:
        b = await _award(db, user.id, "territory_1sqkm")
        if b:
            awarded.append(b.badge_type)
    if area_km2 >= 5:
        b = await _award(db, user.id, "territory_5sqkm")
        if b:
            awarded.append(b.badge_type)

    # Streak milestones
    if user.streak_days >= 7:
        b = await _award(db, user.id, "streak_7")
        if b:
            awarded.append(b.badge_type)
    if user.streak_days >= 30:
        b = await _award(db, user.id, "streak_30")
        if b:
            awarded.append(b.badge_type)

    return awarded
