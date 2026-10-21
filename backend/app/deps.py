from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.database import get_db
from app.models import User


def _user_from_header(authorization: str, db: Session) -> User:
    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    return _user_from_header(authorization, db)


def get_optional_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    """None when no token is sent. A bad token is still a 401."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return _user_from_header(authorization, db)


def friend_ids_subquery(me: User):
    """User ids of the people `me` follows, plus `me` (as a SELECT)."""
    from sqlalchemy import literal, select, union

    from app.models import Follow

    return union(
        select(Follow.followee_id).where(Follow.follower_id == me.id),
        select(literal(me.id)),
    )
