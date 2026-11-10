"""Road filter, element conversion and tile maths. No database, no network."""
import pytest

from app.routing.roads import (
    element_to_road, filter_roads, is_allowed_way, overpass_query, parse_tile_key,
    tile_bbox, tile_key_for, tiles_covering,
)


def way(tags, osm_id=1, n=3):
    return {
        "type": "way", "id": osm_id, "tags": tags,
        "geometry": [{"lat": 26.93 + i * 0.0005, "lon": 75.92} for i in range(n)],
    }


@pytest.mark.parametrize("highway", [
    "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
    "living_street", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
])
def test_allowed_classes(highway):
    assert is_allowed_way({"highway": highway})


@pytest.mark.parametrize("highway", [
    "footway", "path", "track", "steps", "cycleway", "bridleway", "pedestrian",
    "corridor", "construction", "proposed", "motorway", "service_road", "",
])
def test_forbidden_classes(highway):
    assert not is_allowed_way({"highway": highway})


def test_missing_highway_tag():
    assert not is_allowed_way({})


def test_plain_service_allowed():
    assert is_allowed_way({"highway": "service"})


@pytest.mark.parametrize("sub", [
    "driveway", "parking_aisle", "alley", "drive-through", "emergency_access", "other",
])
def test_service_with_subtag_forbidden(sub):
    assert not is_allowed_way({"highway": "service", "service": sub})


@pytest.mark.parametrize("access", ["private", "no"])
def test_blocked_access(access):
    assert not is_allowed_way({"highway": "residential", "access": access})


def test_other_access_values_allowed():
    for value in ("yes", "permissive", "destination", "customers"):
        assert is_allowed_way({"highway": "residential", "access": value})


def test_area_yes_forbidden_area_no_allowed():
    assert not is_allowed_way({"highway": "residential", "area": "yes"})
    assert is_allowed_way({"highway": "residential", "area": "no"})


def test_element_to_road_keeps_order_and_lat_lng():
    road = element_to_road(way({"highway": "residential"}, osm_id=42))
    assert road.osm_id == 42 and road.highway == "residential"
    assert road.points[0] == (26.93, 75.92)
    assert [p[0] for p in road.points] == sorted(p[0] for p in road.points)


def test_element_to_road_drops_bad_elements():
    assert element_to_road(way({"highway": "footway"})) is None
    assert element_to_road(way({"highway": "residential"}, n=1)) is None
    assert element_to_road({"type": "node", "id": 1, "tags": {"highway": "residential"}}) is None
    assert element_to_road({"type": "way", "id": 1, "tags": {"highway": "residential"}}) is None


def test_filter_roads_mixed():
    elements = [
        way({"highway": "residential"}, 1),
        way({"highway": "footway"}, 2),
        way({"highway": "service", "service": "driveway"}, 3),
        way({"highway": "primary"}, 4),
        way({"highway": "tertiary", "access": "private"}, 5),
    ]
    assert [r.osm_id for r in filter_roads(elements)] == [1, 4]


def test_tile_key_format_and_bbox():
    assert tile_key_for(26.935, 75.925) == "2693_7592"
    south, west, north, east = tile_bbox("2693_7592")
    assert (south, west) == pytest.approx((26.93, 75.92))
    assert (north, east) == pytest.approx((26.94, 75.93))
    assert parse_tile_key("2693_7592") == (2693, 7592)


def test_tile_edges_and_negative_coordinates():
    assert tile_key_for(26.93, 75.92) == "2693_7592"
    assert tile_key_for(26.9399, 75.9299) == "2693_7592"
    assert tile_key_for(-0.005, -0.005) == "-1_-1"


def test_tiles_covering_small_circle_is_one_tile():
    assert tiles_covering((26.935, 75.925), 100) == ["2693_7592"]


def test_tiles_covering_crossing_a_corner():
    keys = tiles_covering((26.9399, 75.9299), 200)
    assert sorted(keys) == ["2693_7592", "2693_7593", "2694_7592", "2694_7593"]


def test_tiles_covering_large_circle():
    keys = tiles_covering((26.935, 75.925), 1500)
    assert "2693_7592" in keys and len(keys) == len(set(keys)) and 9 <= len(keys) <= 16


def test_overpass_query_text():
    q = overpass_query((26.93, 75.92, 26.94, 75.93))
    assert q == "[out:json][timeout:25];way[highway](26.930000,75.920000,26.940000,75.930000);out tags geom;"


# --- Overpass server fallback ------------------------------------------------

def test_overpass_urls_default_and_env(monkeypatch):
    from app.routing import roads
    monkeypatch.delenv("OVERPASS_URL", raising=False)
    assert roads.overpass_urls() == list(roads.DEFAULT_OVERPASS_URLS)
    monkeypatch.setenv("OVERPASS_URL", "https://a.example/api, https://b.example/api")
    assert roads.overpass_urls() == ["https://a.example/api", "https://b.example/api"]


def test_overpass_fetch_falls_back_to_the_next_server(monkeypatch):
    import httpx
    from app.routing import roads
    monkeypatch.setenv("OVERPASS_URL", "https://down.example/api,https://up.example/api")
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if "down" in url:
            raise httpx.ConnectTimeout("timed out")
        return httpx.Response(200, json={"elements": [{"type": "way", "id": 1}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(roads.httpx, "post", fake_post)
    assert roads.overpass_fetch((0, 0, 0.01, 0.01)) == [{"type": "way", "id": 1}]
    assert calls == ["https://down.example/api", "https://up.example/api"]


def test_overpass_fetch_raises_when_every_server_fails(monkeypatch):
    import httpx
    import pytest
    from app.routing import roads
    monkeypatch.setenv("OVERPASS_URL", "https://a.example/api,https://b.example/api")

    def fake_post(url, **kwargs):
        return httpx.Response(502, request=httpx.Request("POST", url))

    monkeypatch.setattr(roads.httpx, "post", fake_post)
    with pytest.raises(httpx.HTTPError):
        roads.overpass_fetch((0, 0, 0.01, 0.01))
