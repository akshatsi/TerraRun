# Following and competing with friends

Like Strava: following is one-way and needs no approval. "Friends" in the app
means **the people you follow**. You can see their territory, their recent
runs, and a leaderboard of you against them.

## Data

- New table `follows`: `follower_id` and `followee_id` (both `users.id`),
  `created_at`. Primary key `(follower_id, followee_id)`; you cannot follow
  yourself. Index on `followee_id` for the followers list.

## API

All routes need `Authorization: Bearer <token>` unless marked public.

| Method | Path | Result |
|---|---|---|
| `GET` | `/users/search?q=ak&limit=20` | Users whose name or email starts with or contains `q` (min 2 characters), excluding you. Each item is a **UserCard**. |
| `GET` | `/users/{id}` | One **UserCard** plus `recent_runs` (latest 5, see **FeedItem** without `user`). |
| `POST` | `/users/{id}/follow` | Follow. Idempotent: following twice is still 200. 404 for unknown user, 400 for yourself. Returns the **UserCard**. |
| `DELETE` | `/users/{id}/follow` | Unfollow. Idempotent. Returns the **UserCard**. |
| `GET` | `/me/following` | List of **UserCard**, newest follow first. |
| `GET` | `/me/followers` | List of **UserCard**, newest first. |
| `GET` | `/feed?limit=20&before_id=` | Recent runs by people you follow, newest first, as **FeedItem**. `before_id` pages back. |
| `GET` | `/territories?scope=all\|friends\|mine` | Same response as today. `all` is the default and stays public without a token. `friends` (token required) = people you follow **plus you**. `mine` = only you. |
| `GET` | `/leaderboard?scope=all\|friends&period=all\|week` | Same item fields as today plus `user_id` and `is_me`. `friends` (token required) = people you follow plus you. `week` counts runs since Monday 00:00 UTC. Default `scope=all&period=all`, public, so the current app keeps working. |

**UserCard**

```json
{
  "id": 7, "name": "Meera Kapoor",
  "total_distance_km": 142.6, "total_runs": 31, "territory_area_sq_m": 9100.0,
  "followers_count": 12, "following_count": 8,
  "is_following": true,        // you follow them
  "follows_you": false
}
```

Email is never returned for other users.

**FeedItem**

```json
{
  "run_id": 41, "created_at": "2026-10-21T06:31:40Z",
  "user": {"id": 7, "name": "Meera Kapoor"},
  "distance_km": 4.71, "duration_seconds": 1838, "avg_speed": 9.2,
  "territory_kind": "loop", "awarded_area_sq_m": 3240.0,
  "route_geojson": {...}       // processed route, may be null
}
```

## App

- **Map tab:** the segmented control has three options:
  **All players · Friends · Mine**, backed by `/territories?scope=…`.
  The refresh button on the map is replaced by a **friends icon** that opens
  the Friends screen. The map reloads when the tab opens and when the scope
  changes, so the refresh button is no longer needed.
- **Friends screen:** search for runners and follow or unfollow them; tabs for
  Following and Followers; tapping a runner opens their profile card with
  stats and recent runs.
- **Ranks tab:** an **Everyone · Friends** switch and a **This week · All
  time** switch, backed by `/leaderboard?scope=…&period=…`. Your row is
  highlighted.
- **Home tab:** a "Friends' activity" section showing the latest runs from
  `/feed`, with an empty state that points to the Friends screen.

## Run detail and profile editing (v2)

| Method | Path | Result |
|---|---|---|
| `GET` | `/runs/{id}` | **RunDetail** for any run (territory is public). 404 if unknown. Token required. |
| `PATCH` | `/users/me` | Body `{"name"?: str (2–40), "bio"?: str (≤160)}`. Returns your **UserCard** plus `bio`. |
| `GET` | `/users/me/card` | Your own **UserCard** plus `bio`, for the profile header. |

`UserCard` gains `bio` (string, may be null) everywhere it appears.

**RunDetail**

```json
{
  "run_id": 41, "created_at": "2026-10-21T06:31:40Z",
  "user": {"id": 7, "name": "Meera Kapoor"}, "is_mine": false,
  "distance_km": 4.71, "duration_seconds": 1838, "moving_time_s": 1801,
  "avg_speed_kmh": 9.41, "avg_pace_s_per_km": 382,      // null if no distance
  "elevation_gain_m": 23.0,                               // from altitudes of accepted fixes, null if none
  "max_speed_kmh": 14.2,                                  // null if unknown
  "quality": "good",
  "territory": {"kind": "loop", "awarded_area_sq_m": 3240.0, "reason": "…"},
  "route_geojson": {...},          // processed route (MultiLineString), may be null
  "awarded_geojson": {...},        // the shape this run earned, may be null
  "splits": [                      // one per full km, plus a final partial split
    {"km": 1, "distance_m": 1000, "duration_s": 371, "pace_s_per_km": 371, "elevation_change_m": 4.0},
    {"km": 5, "distance_m": 710,  "duration_s": 270, "pace_s_per_km": 380, "elevation_change_m": -2.0}
  ]
}
```

Splits are computed on the server from accepted fixes (geodesic distance,
time interpolated at each km boundary). Runs saved without fixes return an
empty `splits` list.

## App (v2)

- Map filter labels: **All players · Friends · My territory**.
- Map: a **search icon in the top-left corner** opens people search.
  The friends icon stays on the right.
- Profile tab: two buttons under the header, **Edit profile** (name and bio,
  `PATCH /users/me`) and **Share profile** (system share sheet with your name,
  stats and the app name).
- Tapping any run (friends' activity on Home, a runner's recent runs, your own
  run history) opens a Strava-style **Run detail** screen: map with the route
  and the territory it earned, a stat grid (distance, moving time, pace,
  average speed, elevation gain, territory), and a splits table.
