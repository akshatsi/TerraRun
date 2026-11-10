# Route suggestions

TerraRun suggests a loop for the runner to run next: one that grows their
territory and takes land from the people they follow, sized to how far and how
fast they usually run, and kept to proper roads.

No machine learning and no training data: suggestions come from the road map,
the territories already stored, and the runner's own past runs.

## Scope

- **Friends only.** The only rival land a suggestion targets is held by people
  the runner follows. Everyone else's territory is ignored, as if it were empty
  land the runner cannot "steal" (it still earns nothing extra).
- **Close to home.** Suggestions stay within reach of the runner's position
  (see *Search area*), so the system never sends someone to a part of the map
  far beyond their usual range.
- **Main roads only.** Routes use proper roads, not footpaths, tracks, steps,
  alleys, driveways or parking aisles (see *Roads*).

## Pieces

| Piece | Where | What it does |
|---|---|---|
| Road data | `backend/app/routing/roads.py` | Fetches roads from OpenStreetMap (Overpass API), keeps only the allowed classes, caches them in PostGIS by map tile. |
| Route finder | `backend/app/routing/planner.py` (+ helpers) | Pure Python. Builds the road graph, scores city blocks, searches for the best loops, checks each one with the real territory rules. |
| Endpoint | `GET /suggestions` | Gathers inputs (roads, territories, the runner's pace and usual distance), calls the route finder, returns up to 3 suggestions. |
| App | Map tab | "Suggest a route" button, a sheet with the options, the chosen route drawn on the map and shown during the run. |

## Roads

Allowed OpenStreetMap `highway` values ("main roads"):

`trunk, primary, secondary, tertiary, unclassified, residential, living_street`
and their `_link` variants, plus `service` **only** when it has no `service=*`
sub-tag (a plain service road, as on a campus). Never: `footway, path, track,
steps, cycleway, bridleway, pedestrian, corridor, construction, proposed`,
`service` with `service=driveway|parking_aisle|alley|drive-through|emergency_access`,
anything with `access=private|no`, and `area=yes` ways.

Each kept way becomes a `RoadWay`: OSM id, highway class, and its points in
order. Bigger roads are preferred slightly (see *Scoring*), but every allowed
class can be used.

## Route finder interface (`backend/app/routing/`)

```python
from app.routing import (
    RoadWay, OwnedArea, PlannerInput, PlannerConfig, Suggestion, plan_routes,
)

RoadWay(osm_id: int, highway: str, points: list[tuple[float, float]])   # (lat, lng)

OwnedArea(user_id: int, geometry)        # shapely Polygon | MultiPolygon, WGS-84, x=lng y=lat

PlannerInput(
    start: tuple[float, float],          # runner's position (lat, lng)
    roads: list[RoadWay],
    my_user_id: int,
    my_territory: OwnedArea | None,
    friend_territories: list[OwnedArea], # people the runner follows only
    target_distance_m: float,            # how long the loop should be
    popularity: dict[int, int] = {},     # osm_id -> how many friends' runs used it (optional)
)

suggestions: list[Suggestion] = plan_routes(inp, PlannerConfig())

Suggestion(
    route: list[tuple[float, float]],    # closed route along roads (leg out, loop, leg back), (lat, lng), first == last
    distance_m: float,                   # along the roads
    enclosed,                            # shapely Polygon/MultiPolygon the runner would win
    new_area_sq_m: float,                # land no one held
    stolen_area_sq_m: float,             # land taken from friends (sum)
    stolen_by_user: dict[int, float],    # friend user_id -> m² taken
    already_mine_sq_m: float,            # land inside that is already theirs (no gain)
    gain_sq_m: float,                    # new + stolen
    score: float,                        # what the finder ranked by
    label: str,                          # "Most from friends" | "Most new land" | "Closest to your usual run" | "Another option"
    reason: str,                         # one plain sentence, e.g. "Loops the block north of GH; takes 2,400 m² from friends"
    approach_m: float = 0.0,             # one-way road leg from the runner to the loop (0: the loop passes them)
)
```

`PlannerConfig()` defaults are listed in `planner.py`; the ones this doc
refers to are `start_radius_m=150`, `distance_tolerance=0.25`,
`steal_weight=1.5`, `section_size_m=250`, `max_access_fraction=0.35` and
`max_access_m=1500`.

`plan_routes` returns 0–3 suggestions, best first, that differ from each
other (not the same loop with a small change). Labels are true among the
suggestions shown: "Most new land" goes only to the one with the most new
land, and so on; one that leads on nothing is "Another option". It returns `[]` when the roads
near the runner form no usable loop; the endpoint then says why.

Every suggestion is checked with `build_territory_shape` on its own route
(as if the runner ran it with perfect GPS): it must come out as `kind ==
"loop"`, and the gains are computed from that real shape, so the app never
promises land the rules would not award.

## Search area and distance

- **Target distance:** if the request gives `distance_km` or `minutes`, use it
  (`minutes` is turned into metres with the runner's pace). Otherwise use the
  runner's usual distance: the median accepted distance of their last 10 runs,
  clamped to 0.8–8 km; with no runs yet, 2 km.
- **Pace:** the runner's average pace over the last 10 runs (seconds per km);
  with none, 6:30 /km. A slower runner therefore gets a shorter loop for the
  same `minutes`, and estimated times use their own pace.
- **Search area:** roads within `target_distance_m / 2` of the start (a route of
  length L can't go further than L/2 away), capped at 3 km. Routes must start and
  end within `start_radius_m` (default 150 m) of the runner; if no allowed road
  is that close, there is no suggestion.
- **Approach leg:** runners often start where no loop passes nearby (a campus or
  hostel on dead-end service roads). The route then starts at the road point
  nearest the runner, takes the shortest road path to the loop, goes round it
  and comes back the same way. The territory rules award the loop's land plus
  the leg's 3 m strip. The leg is at most `max_access_fraction` (35%) of the
  target and at most `max_access_m` (1.5 km) one way, and shorter legs score
  higher. When a loop passes within `start_radius_m` of the runner there is no
  leg.
- **Accepted length:** a suggestion's distance (loop + 2 × leg) must be within
  ±25% of the target.

## Scoring (summary — the finder documents the details)

- Land inside the loop that **no one** holds counts fully.
- Land held by a **followed friend** counts with a steal bonus (`steal_weight`,
  default 1.5): taking land is worth more than claiming empty land.
- Land the runner **already holds** counts as zero.
- A small preference for bigger roads and for roads friends run often
  (busy, known routes), never strong enough to beat area.
- **Section focus:** the map is cut into square sections (`section_size_m`,
  default 250 m). A loop scores a little more when it lies in a section where
  the runner already holds some land but not most of it (e.g. 1,000 m² of a
  10,000 m² section): consolidate and expand near their existing ground rather
  than scatter.

## Endpoint

`GET /suggestions?lat=26.93&lng=75.92[&distance_km=3][&minutes=25]` — token
required. `distance_km` and `minutes` are optional and exclusive.

```json
{
  "target_distance_km": 2.4,
  "pace_s_per_km": 450,
  "suggestions": [
    {
      "label": "Most from friends",
      "reason": "Loops the block north of GH; takes 2,400 m² from friends",
      "distance_km": 2.31,
      "estimated_minutes": 17,
      "new_area_sq_m": 8100.0,
      "stolen_area_sq_m": 2400.0,
      "stolen_from": [{"user_id": 7, "name": "Meera Kapoor", "area_sq_m": 2400.0}],
      "gain_sq_m": 10500.0,
      "route_geojson": {"type": "LineString", "coordinates": [[75.92, 26.93]]},
      "area_geojson": {"type": "Polygon", "coordinates": []}
    }
  ],
  "message": null
}
```

`message` explains an empty list (for example "No road loops near you yet").
Errors: 401 without a token, 422 for bad parameters, 503 with a clear message
when road data can't be fetched and nothing is cached.

## Road cache

Table `road_ways`: `osm_id` (primary key), `highway`, `geom` (LINESTRING 4326),
`tile_key` (indexed), `fetched_at`. Table `road_tiles`: `tile_key` (primary
key), `fetched_at`. Tiles are fixed squares (0.01° lat × 0.01° lng, about
1.1 km); a tile is refetched after 30 days. Tests never touch the network: the
Overpass client is injectable and tests use a synthetic grid of streets.
