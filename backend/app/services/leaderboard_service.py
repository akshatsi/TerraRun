"""
Leaderboard service — rank users by territory area.
"""

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_global_leaderboard(db: AsyncSession, limit: int = 50, offset: int = 0):
    """Top users globally by territory area."""
    query = (
        select(User)
        .where(User.is_active == True)  # noqa: E712
        .order_by(desc(User.territory_area_m2))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    users = result.scalars().all()

    count_query = select(func.count()).select_from(User).where(User.is_active == True)  # noqa: E712
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    entries = []
    for rank, user in enumerate(users, start=offset + 1):
        entries.append({
            "rank": rank,
            "user_id": user.id,
            "username": user.username,
            "avatar_url": user.avatar_url,
            "territory_area_m2": user.territory_area_m2,
            "total_distance_m": user.total_distance_m,
        })

    return entries, total


async def get_local_leaderboard(
    db: AsyncSession,
    city: str,
    limit: int = 50,
    offset: int = 0,
):
    """Top users in a specific city."""
    query = (
        select(User)
        .where(User.is_active == True, User.city == city)  # noqa: E712
        .order_by(desc(User.territory_area_m2))
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    users = result.scalars().all()

    count_query = (
        select(func.count())
        .select_from(User)
        .where(User.is_active == True, User.city == city)  # noqa: E712
    )
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    entries = []
    for rank, user in enumerate(users, start=offset + 1):
        entries.append({
            "rank": rank,
            "user_id": user.id,
            "username": user.username,
            "avatar_url": user.avatar_url,
            "territory_area_m2": user.territory_area_m2,
            "total_distance_m": user.total_distance_m,
        })

    return entries, total
