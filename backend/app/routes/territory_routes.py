import json

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from geoalchemy2 import functions as gfunc

from app.database import get_db
from app.models import Territory, User
from app.schemas import TerritoryResponse, TerritoryListResponse
from app.deps import friend_ids_subquery, get_current_user, get_optional_user

router = APIRouter(prefix="/territories", tags=["territories"])


@router.get("", response_model=TerritoryListResponse)
def get_all_territories(
    scope: Literal["all", "friends", "mine"] = Query(default="all"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    """Return territories as GeoJSON (for rendering on the map).

    scope=all is public. friends (people you follow plus you) and mine need a token.
    """
    query = db.query(Territory, User.name).join(User, User.id == Territory.user_id)
    if scope != "all":
        if current_user is None:
            raise HTTPException(status_code=401, detail="Missing token")
        if scope == "mine":
            query = query.filter(Territory.user_id == current_user.id)
        else:
            query = query.filter(Territory.user_id.in_(friend_ids_subquery(current_user)))
    territories = query.all()

    items = []
    for terr, user_name in territories:
        geojson_str = db.execute(gfunc.ST_AsGeoJSON(terr.geom)).scalar()
        geojson = json.loads(geojson_str) if geojson_str else None

        items.append(TerritoryResponse(
            user_id=terr.user_id,
            user_name=user_name,
            area_sq_m=round(terr.area_sq_m, 2),
            geojson=geojson,
        ))

    return TerritoryListResponse(territories=items)


@router.get("/me", response_model=TerritoryResponse)
def get_my_territory(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the authenticated user's territory."""
    terr = (
        db.query(Territory)
        .filter(Territory.user_id == current_user.id)
        .first()
    )

    if terr is None:
        return TerritoryResponse(
            user_id=current_user.id,
            user_name=current_user.name,
            area_sq_m=0.0,
            geojson=None,
        )

    geojson_str = db.execute(gfunc.ST_AsGeoJSON(terr.geom)).scalar()
    geojson = json.loads(geojson_str) if geojson_str else None

    return TerritoryResponse(
        user_id=current_user.id,
        user_name=current_user.name,
        area_sq_m=round(terr.area_sq_m, 2),
        geojson=geojson,
    )
