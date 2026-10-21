# GPS accuracy and territory geometry

How TerraRun turns raw GPS fixes into a trusted distance and an awarded
territory. The phone collects fixes and shows a live estimate; the backend
decides the recorded distance and the territory.

Distance and territory are separate systems:

- **Distance engine** (`backend/app/gps/`): pure Python, no database. Takes
  raw fixes, returns accepted fixes, segments, distance and quality.
- **Geometry engine** (`backend/app/territory.py`): PostGIS. Takes the
  accepted segments, builds the observed corridor and the awarded territory.

## 1. Upload contract: `POST /runs`

```json
{
  "client_run_id": "3f2a…",          // random 32-hex id made on the phone; idempotency key
  "started_at": "2026-10-17T06:01:02.000Z",
  "ended_at":   "2026-10-17T06:31:40.000Z",
  "duration_seconds": 1838,          // the phone's timer, informational
  "client_distance_km": 4.92,        // the phone's live estimate, informational only
  "fixes": [
    {
      "lat": 26.93421, "lng": 75.92411,
      "t": "2026-10-17T06:01:03.000Z",   // the fix's own GPS timestamp, ISO 8601 UTC
      "accuracy_m": 6.5,                 // horizontal accuracy, may be null
      "speed_mps": 2.9,                  // reported speed, may be null
      "heading_deg": 81.0,               // may be null
      "altitude_m": 431.0                // may be null
    }
  ]
}
```

- Send every fix the phone received during the run, in order, including ones
  the phone's live filter ignored. The server re-validates everything.
- Legacy payloads (`distance_km`, `avg_speed`, `route_coordinates` as
  `[[lat, lng], …]`, no timestamps) stay accepted. They are processed with
  spatial-only checks and marked `quality = "unverified"`.
- The same `(user, client_run_id)` sent twice returns the first run's result
  with HTTP 200 and awards nothing again.

Response (extends the old `RunResponse`; old fields keep their meaning):

```json
{
  "id": 41, "user_id": 3, "created_at": "…",
  "distance_km": 4.71,               // server-accepted distance, authoritative
  "duration_seconds": 1838,
  "avg_speed": 9.2,                  // km/h, from accepted distance and moving time
  "route_geojson": {…},              // processed route (MultiLineString of accepted segments)
  "territory_geojson": {…},          // the user's whole territory after this run
  "processing": {
    "algorithm_version": "gps-1.0.0",
    "quality": "good",               // good | fair | poor | unverified
    "accepted_fixes": 1790, "rejected_fixes": 41,
    "gap_count": 1, "uncertain_distance_m": 120.4,
    "raw_distance_km": 5.03,         // naive sum of all fixes, for diagnostics
    "client_distance_km": 4.92,
    "moving_time_s": 1801
  },
  "territory": {
    "observed_area_sq_m": 61234.0,   // corridor around accepted segments
    "awarded_area_sq_m": 58800.0,    // what this run actually added after rules
    "total_area_sq_m": 530120.0
  },
  "duplicate": false                 // true when this client_run_id was already saved
}
```

## 2. Distance engine interface (`backend/app/gps/`)

```python
from app.gps import RawFix, TrackConfig, process_track, ALGORITHM_VERSION

RawFix(lat: float, lng: float, t: float,           # t = unix seconds (float)
       accuracy_m: float | None = None, speed_mps: float | None = None,
       heading_deg: float | None = None, altitude_m: float | None = None)

result = process_track(fixes: list[RawFix], config: TrackConfig = TrackConfig())
result.algorithm_version   # str, e.g. "gps-1.0.0"
result.fixes               # list[ProcessedFix], same length and order as input
result.segments            # list[Segment]
result.distance_m          # accepted distance, sum of accepted segment lengths
result.raw_distance_m      # naive geodesic sum over all fixes in order
result.uncertain_distance_m  # straight-line distance across gaps, NOT counted
result.moving_time_s
result.accepted_count, result.rejected_count, result.gap_count
result.quality             # "good" | "fair" | "poor"

ProcessedFix(index, lat, lng, t, accepted: bool,
             rejection_reason: str | None,   # see reasons below
             segment_id: int | None,         # None when rejected
             filtered_lat: float | None, filtered_lng: float | None)  # set when a filter is on

Segment(id, fix_indices: list[int],          # accepted fixes in this segment, in order
        distance_m: float, start_t: float, end_t: float)
```

Rejection reasons: `duplicate`, `out_of_order`, `poor_accuracy`,
`implausible_speed`, `stationary`, `invalid_coordinates`.
A `stationary` fix is not an error: it is kept, but adds no distance.

Gaps: when two consecutive accepted fixes are more than
`long_gap_s` apart, the second starts a new segment. The straight line across
the gap goes into `uncertain_distance_m`, not into `distance_m`, and the
geometry engine does not build territory across it.

### Default `TrackConfig`

| Field | Default | Meaning |
|---|---|---|
| `preferred_accuracy_m` | 10 | Fixes at or below this are full quality |
| `max_accuracy_m` | 20 | Fixes worse than this are rejected for distance |
| `min_displacement_m` | 4 | Smaller moves from the last accepted fix are stationary |
| `accuracy_displacement_factor` | 0.5 | Also stationary if the move is under this × combined accuracy |
| `stationary_speed_mps` | 0.5 | Reported speed under this, with a small move, is stationary |
| `max_speed_mps` | 12.0 | Faster implied speed is implausible for a runner |
| `long_gap_s` | 15 | Larger time gaps split segments and are not bridged |
| `use_kalman` | False | Constant-velocity Kalman smoothing before distance; off until benchmarked |
| `reanchor_after` | 5 | Consistent far fixes in a row that move the anchor (counted as a gap) |
| `kalman_accel_std`, `kalman_default_accuracy_m` | 1.0, 15 | Kalman tuning |

When the phone reports a speed under `stationary_speed_mps` (or the average
speed since the anchor is that low), a move up to
`max(8 m, 2 × combined accuracy) + 0.5 m/s × dt` still counts as standing
still. The plain rule above let 5 m jitter add distance over a 10-minute stop.

Distances are geodesic on the WGS-84 ellipsoid (`pyproj.Geod`), never planar
degrees.

## 3. Storage

- `runs`: new columns `client_run_id` (unique with `user_id`), `started_at`,
  `ended_at`, `raw_distance_km`, `client_distance_km`, `uncertain_distance_m`,
  `moving_time_s`, `accepted_fix_count`, `rejected_fix_count`, `gap_count`,
  `quality`, `algorithm_version`, `status`, `processed_at`,
  `processed_route_geom` (MULTILINESTRING), `observed_corridor_geom`,
  `awarded_geom`, `observed_area_sq_m`, `awarded_area_sq_m`.
  `route_geom` keeps the raw route as received.
- `gps_fixes`: one row per received fix: `run_id`, `seq`, `latitude`,
  `longitude`, `recorded_at`, `horizontal_accuracy_m`, `reported_speed_mps`,
  `heading_deg`, `altitude_m`, `accepted`, `rejection_reason`, `segment_id`.
- Raw fixes are kept so old runs can be reprocessed when the algorithm
  changes.
- There is no migration tool: `setup_postgis.py` adds new columns with
  `ALTER TABLE … ADD COLUMN IF NOT EXISTS` so existing databases upgrade in
  place.

## 4. Territory rules (v2)

A run earns one of three shapes, decided by `build_territory_shape` in
`backend/app/gps/territory_shape.py` (pure Python, no database):

- **Loop** — the path encloses at least `min_loop_area_sq_m` (200 m²). The
  award is the enclosed area plus a route strip along any tails or spurs
  outside it; the loop's own edge gets no corridor. Land is enclosed when:
  - **the end is near the start.** A straight line joins the last accepted fix
    to the first when they are within `closure_radius_m` (200 m), the path is
    at least `min_loop_perimeter_m` (100 m), gaps are at most
    `max_gap_fraction_for_loop` (10%) of it, and the join is at most
    `max_closure_fraction` (25%) of the path, so at least 80% of the ring was
    walked. Gaps are bridged only when this join is made.
  - **the path crosses itself**, anywhere in the run: every face the path walls
    off counts, so a loop with a tail before or after it, a figure-8 or a loop
    run twice all earn the area inside, counted once.
  - **the path comes back near itself.** GPS rarely crosses exactly, so a
    return within `self_snap_m` (15 m, about twice a good fix's accuracy) of a
    part of the path at least `self_snap_min_separation_m` (100 m) back along
    it is joined by a short connector.

  The join and the connectors are guesses, so a face that needs one counts only
  if it is wider than 30 m somewhere (holds a disc of radius `self_snap_m`).
  Two legs of an out-and-back 15 m apart earn nothing; a straight or gently
  curving path never comes back near itself. All faces then lose any part
  narrower than the 6 m route strip, and each part needs a perimeter of at
  least 100 m. Under 200 m² in all, the run is a route. `reason` says what
  happened, for example "Loop closed 25 m from start; 18,400 m² enclosed" or
  "Path crossed itself; 10,000 m² enclosed + 211 m of route".
- **Route** — any other run (A to B). The award is the road travelled: a thin
  strip `route_half_width_m` (3 m) each side of each accepted segment, with
  flat ends (no round caps) and never across a gap.
- **None** — fewer than 2 accepted fixes, quality `poor`, or accepted distance
  under 50 m. The run is saved but earns nothing.

```python
from app.gps.territory_shape import ShapeConfig, TerritoryShape, build_territory_shape

shape = build_territory_shape(
    segments: list[list[tuple[float, float]]],  # accepted fixes per segment, (lat, lng), in order
    uncertain_distance_m: float = 0.0,          # from the distance engine
    config: ShapeConfig = ShapeConfig(),
)
shape.kind                # "loop" | "route" | "none"
shape.geometry            # shapely Polygon/MultiPolygon in WGS-84 (x=lng, y=lat), valid; None for "none"
shape.area_sq_m           # geodesic area in square metres (0.0 for "none")
shape.closure_distance_m  # metres from last to first accepted fix; None if < 2 fixes
shape.reason              # short human-readable explanation
```

`ShapeConfig` defaults: `closure_radius_m=200`, `max_closure_fraction=0.25`,
`min_loop_perimeter_m=100`, `min_loop_area_sq_m=200`, `route_half_width_m=3`,
`max_gap_fraction_for_loop=0.1`, `simplify_tolerance_m=1.5`, `self_snap_m=15`,
`self_snap_min_separation_m=100`.

The database side (`backend/app/territory.py`) applies the quality and
distance rules, then subtracts the awarded shape from rivals and unions it
into the runner's territory, with `ST_MakeValid` and `ST_Area(geom::geography)`.
The run stores `territory_kind`, `observed_corridor_geom` (the shape before
rival handling) and `awarded_geom`.

`backend/reprocess_territories.py` rebuilds every user's territory from the
stored runs, in the order they were recorded, using the current rules.

## 5. Phone

- Records every fix with its timestamp, accuracy, speed, heading and
  altitude; asks for updates about once a second with no distance filter.
- Shows a live distance from a Dart port of the same checks
  (`lib/gps/track_filter.dart`), then replaces it with the server's value.
- Saves the run in progress to local storage, and keeps finished runs in an
  upload queue that retries with the same `client_run_id` until the server
  accepts it.
