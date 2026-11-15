"""
Rebuild every territory from the stored runs with the current rules
(docs/gps-accuracy.md, sections 4, 6 and 7).

Usage:
    python reprocess_territories.py [--dry-run] [--offline]

Reads DATABASE_URL like the app. In one transaction it clears all territories,
then replays every run in created_at/id order: segments come from the accepted
gps_fixes rows (grouped by segment_id, ordered by seq), or from the raw route
for old runs without fixes (one segment, never split). Each run's track is
cleaned against the walkable OpenStreetMap ways around it (fetched from
Overpass and cached in road_ways/road_tiles; --offline uses only what is
cached), then shaped, awarded, and any land enclosed by the runner's own
territory is awarded too.

It prints what it will delete and replace first. Per run it updates
processed_route_geom, clean_method, matched_fraction, territory_kind and the
observed and awarded columns. Distance, raw route and fixes are not touched.
--dry-run does all the work, rolls everything back (no row is written, road
cache included) and prints per-run method and matched share, and the
before/after area per user. Running it twice gives the same result.

On a server:
    docker compose -f docker-compose.prod.yml exec backend \
        python reprocess_territories.py --dry-run
"""

import argparse
import sys

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.routing.roads import overpass_fetch
from app.territory import award_run, clean_segments


def _areas(db: Session) -> dict[int, float]:
    rows = db.execute(text("SELECT user_id, area_sq_m FROM territories")).all()
    return {r[0]: float(r[1] or 0.0) for r in rows}


def _segments_for_run(
    db: Session, run_id: int, has_route: bool
) -> tuple[list[list[tuple[float, float]]], list[list[float | None]] | None, bool]:
    """(segments, accuracies, legacy). Legacy runs are one segment, no accuracies."""
    rows = db.execute(
        text(
            "SELECT segment_id, latitude, longitude, horizontal_accuracy_m FROM gps_fixes "
            "WHERE run_id = :r AND accepted AND segment_id IS NOT NULL "
            "ORDER BY segment_id, seq"
        ),
        {"r": run_id},
    ).all()
    if rows:
        segs: dict[int, list[tuple[float, float]]] = {}
        accs: dict[int, list[float | None]] = {}
        for seg_id, lat, lng, acc in rows:
            segs.setdefault(seg_id, []).append((lat, lng))
            accs.setdefault(seg_id, []).append(acc)
        order = sorted(segs)
        return [segs[k] for k in order], [accs[k] for k in order], False
    if not has_route:
        return [], None, True
    # Old run without fixes: the raw route is one segment.
    pts = db.execute(
        text(
            "SELECT ST_Y(d.geom), ST_X(d.geom) FROM runs, ST_DumpPoints(route_geom) AS d "
            "WHERE runs.id = :r ORDER BY d.path"
        ),
        {"r": run_id},
    ).all()
    return ([[(float(a), float(b)) for a, b in pts]] if len(pts) >= 2 else []), None, True


def reprocess(db: Session, fetcher=None, log=print) -> dict:
    """Rebuild all territories. The caller commits or rolls back."""
    fetcher = fetcher or overpass_fetch
    before = _areas(db)
    runs = db.execute(
        text(
            "SELECT id, user_id, distance_km, quality, uncertain_distance_m, "
            "route_geom IS NOT NULL FROM runs ORDER BY created_at, id"
        )
    ).all()
    log(f"Will delete {len(before)} territories (users {sorted(before)}) and rebuild them "
        f"from {len(runs)} runs.")
    log("Will replace on every run: processed_route_geom, clean_method, matched_fraction, "
        "territory_kind, observed_corridor_geom, awarded_geom, observed_area_sq_m, "
        "awarded_area_sq_m.")
    db.execute(text("DELETE FROM territories"))
    kinds = {"loop": 0, "route": 0, "none": 0}
    methods: dict[str, int] = {}
    for run_id, user_id, distance_km, quality, uncertain, has_route in runs:
        segments, accuracies, legacy = _segments_for_run(db, run_id, bool(has_route))
        clean = clean_segments(db, segments, accuracies, fetcher=fetcher,
                               one_segment=legacy, commit=False)
        res = award_run(
            db,
            user_id,
            clean.segments,
            quality or "unverified",
            (distance_km or 0.0) * 1000.0,
            uncertain or 0.0,
        )
        kinds[res["kind"]] += 1
        methods[clean.method] = methods.get(clean.method, 0) + 1
        log(f"run {run_id:>6} user {user_id:>4} {clean.method:>8} "
            f"matched {clean.matched_fraction:5.0%} {res['kind']:>5} "
            f"awarded {res['awarded_area_sq_m']:>10.1f} m2 "
            f"(enclosed {res['enclosed_area_sq_m']:.1f})")
        db.execute(
            text(
                """
                UPDATE runs SET
                    processed_route_geom = CASE WHEN :route IS NULL THEN NULL
                        ELSE ST_GeomFromEWKT(:route) END,
                    clean_method = :method,
                    matched_fraction = :frac,
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
                "route": res["route_ewkt"],
                "method": clean.method,
                "frac": clean.matched_fraction,
                "kind": res["kind"],
                "corr": res["corridor_hex"],
                "awd": res["awarded_hex"],
                "oa": res["observed_area_sq_m"],
                "aa": res["awarded_area_sq_m"],
                "id": run_id,
            },
        )
    db.flush()
    return {"runs": len(runs), "kinds": kinds, "methods": methods,
            "before": before, "after": _areas(db)}


def _no_network(bbox):
    raise ConnectionError("--offline: using cached road data only")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="roll back and only print the result")
    parser.add_argument("--offline", action="store_true",
                        help="do not call Overpass; use cached road data only")
    args = parser.parse_args(argv)

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        summary = reprocess(db, fetcher=_no_network if args.offline else None)
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
        f"{summary['runs']} runs: {k['loop']} loop, {k['route']} route, {k['none']} none; "
        f"tracks {summary['methods']}. "
        + ("Dry run, nothing saved." if args.dry_run else "Saved.")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
