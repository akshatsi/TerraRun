"""
Rebuild every territory from the stored runs with the current rules
(docs/gps-accuracy.md, section 4).

Usage:
    python reprocess_territories.py [--dry-run]

Reads DATABASE_URL like the app. In one transaction it clears all territories,
then replays every run in created_at/id order: segments come from the accepted
gps_fixes rows (grouped by segment_id, ordered by seq), or from the raw route
for old runs without fixes (one segment). Each run's territory_kind and its
observed and awarded columns are updated. Distance and fixes are not touched.
--dry-run rolls everything back and prints the before/after areas per user.
Running it twice gives the same result.

On a server:
    docker compose -f docker-compose.prod.yml exec backend \
        python reprocess_territories.py --dry-run
"""

import argparse
import sys

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.territory import award_run


def _areas(db: Session) -> dict[int, float]:
    rows = db.execute(text("SELECT user_id, area_sq_m FROM territories")).all()
    return {r[0]: float(r[1] or 0.0) for r in rows}


def _segments_for_run(db: Session, run_id: int, has_route: bool) -> list[list[tuple[float, float]]]:
    rows = db.execute(
        text(
            "SELECT segment_id, latitude, longitude FROM gps_fixes "
            "WHERE run_id = :r AND accepted AND segment_id IS NOT NULL "
            "ORDER BY segment_id, seq"
        ),
        {"r": run_id},
    ).all()
    if rows:
        segs: dict[int, list[tuple[float, float]]] = {}
        for seg_id, lat, lng in rows:
            segs.setdefault(seg_id, []).append((lat, lng))
        return [segs[k] for k in sorted(segs)]
    if not has_route:
        return []
    # Old run without fixes: the raw route is one segment.
    pts = db.execute(
        text(
            "SELECT ST_Y(d.geom), ST_X(d.geom) FROM runs, ST_DumpPoints(route_geom) AS d "
            "WHERE runs.id = :r ORDER BY d.path"
        ),
        {"r": run_id},
    ).all()
    return [[(float(a), float(b)) for a, b in pts]] if len(pts) >= 2 else []


def reprocess(db: Session) -> dict:
    """Rebuild all territories. The caller commits or rolls back."""
    before = _areas(db)
    db.execute(text("DELETE FROM territories"))
    runs = db.execute(
        text(
            "SELECT id, user_id, distance_km, quality, uncertain_distance_m, "
            "route_geom IS NOT NULL FROM runs ORDER BY created_at, id"
        )
    ).all()
    kinds = {"loop": 0, "route": 0, "none": 0}
    for run_id, user_id, distance_km, quality, uncertain, has_route in runs:
        segments = _segments_for_run(db, run_id, bool(has_route))
        res = award_run(
            db,
            user_id,
            segments,
            quality or "unverified",
            (distance_km or 0.0) * 1000.0,
            uncertain or 0.0,
        )
        kinds[res["kind"]] += 1
        db.execute(
            text(
                """
                UPDATE runs SET
                    territory_kind = :kind,
                    observed_corridor_geom = CASE WHEN :corr IS NULL THEN NULL
                        ELSE ST_GeomFromEWKB(decode(:corr, 'hex')) END,
                    awarded_geom = CASE WHEN :awd IS NULL THEN NULL
                        ELSE ST_GeomFromEWKB(decode(:awd, 'hex')) END,
                    observed_area_sq_m = :oa,
                    awarded_area_sq_m = :aa
                WHERE id = :id
                """
            ),
            {
                "kind": res["kind"],
                "corr": res["corridor_hex"],
                "awd": res["awarded_hex"],
                "oa": res["observed_area_sq_m"],
                "aa": res["awarded_area_sq_m"],
                "id": run_id,
            },
        )
    db.flush()
    return {"runs": len(runs), "kinds": kinds, "before": before, "after": _areas(db)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="roll back and only print the result")
    args = parser.parse_args(argv)

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        summary = reprocess(db)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    users = sorted(set(summary["before"]) | set(summary["after"]))
    print(f"{'user':>6} {'before m2':>14} {'after m2':>14}")
    for u in users:
        print(f"{u:>6} {summary['before'].get(u, 0.0):>14.1f} {summary['after'].get(u, 0.0):>14.1f}")
    k = summary["kinds"]
    print(
        f"{summary['runs']} runs: {k['loop']} loop, {k['route']} route, {k['none']} none. "
        + ("Dry run, nothing saved." if args.dry_run else "Saved.")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
