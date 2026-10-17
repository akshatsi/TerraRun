import math

import pytest

from app.gps import ALGORITHM_VERSION, RawFix, TrackConfig, process_track
from app.gps import synthetic as syn
from app.gps.geodesy import distance_m, offset_point


def err(result, ref):
    return abs(result.distance_m - ref) / ref


def reasons(result):
    return [f.rejection_reason for f in result.fixes]


def test_empty_and_single():
    r = process_track([])
    assert r.fixes == [] and r.distance_m == 0 and r.quality == "poor"
    assert r.algorithm_version == ALGORITHM_VERSION == "gps-1.0.0"
    r = process_track([RawFix(26.9, 75.9, 1000.0, 5.0)])
    assert len(r.fixes) == 1 and r.fixes[0].accepted and r.distance_m == 0
    assert r.quality == "poor" and len(r.segments) == 1


def test_stationary_does_not_accumulate():
    fixes, ref = syn.stationary(1, minutes=10, noise_m=5)
    r = process_track(fixes)
    assert r.distance_m < 15
    assert r.raw_distance_m > 500
    assert any(f.rejection_reason == "stationary" for f in r.fixes)
    assert all(f.segment_id is None for f in r.fixes if f.rejection_reason == "stationary")


def test_stationary_several_seeds():
    for seed in range(5):
        fixes, _ = syn.stationary(seed, minutes=10, noise_m=5)
        assert process_track(fixes).distance_m < 15


def test_loop_three_laps():
    for seed in range(3):
        fixes, ref = syn.track_400m_loop(seed)
        assert ref == pytest.approx(1200, abs=5)
        r = process_track(fixes)
        assert err(r, ref) < 0.03
        assert r.raw_distance_m > r.distance_m
        assert r.quality == "good"


def test_sharp_turns():
    for seed in range(3):
        fixes, ref = syn.route_sharp_turns_1km(seed)
        assert err(process_track(fixes), ref) < 0.05


def test_urban_multipath():
    for seed in range(3):
        fixes, ref, outliers = syn.urban_multipath_detail(seed)
        r = process_track(fixes)
        assert err(r, ref) < 0.05
        caught = sum(1 for i in outliers if not r.fixes[i].accepted)
        assert caught >= 0.9 * len(outliers)
        assert r.raw_distance_m > 1.3 * ref


def test_gap_splits_segment():
    fixes, _ = syn.track_400m_loop(3)
    full = process_track(fixes)
    gapped = syn.with_gap(fixes, 100, 60)
    r = process_track(gapped)
    assert r.gap_count == 1
    assert len(r.segments) == 2
    assert r.uncertain_distance_m > 100
    # distance excludes roughly 60 s * 3.5 m/s
    assert full.distance_m - r.distance_m > 150
    assert r.distance_m + r.uncertain_distance_m == pytest.approx(full.distance_m, rel=0.06)
    first, second = r.segments
    assert second.start_t - first.end_t > 15


def test_duplicates():
    fixes, ref = syn.track_400m_loop(4)
    base = process_track(fixes)
    dup = syn.with_duplicates(fixes, 0.2, seed=1)
    assert len(dup) > len(fixes)
    r = process_track(dup)
    n_dup = len(dup) - len(fixes)
    assert sum(1 for x in reasons(r) if x == "duplicate") == n_dup
    assert r.distance_m == pytest.approx(base.distance_m, abs=1e-6)
    assert len(r.fixes) == len(dup)


def test_out_of_order():
    fixes, _ = syn.route_sharp_turns_1km(5)
    base = process_track(fixes)
    shuffled = list(fixes)
    shuffled.insert(50, fixes[20])  # a late old fix with a different position than the anchor
    # make it not an exact duplicate
    old = fixes[20]
    shuffled[50] = RawFix(old.lat + 1e-5, old.lng, old.t, old.accuracy_m, old.speed_mps)
    r = process_track(shuffled)
    assert r.fixes[50].rejection_reason == "out_of_order"
    assert r.distance_m == pytest.approx(base.distance_m, rel=1e-6)


def test_poor_accuracy_rejected():
    fixes, ref = syn.track_400m_loop(6)
    bad = syn.with_poor_accuracy(fixes, 0.15, seed=2)
    r = process_track(bad)
    n_bad = sum(1 for a, b in zip(fixes, bad) if a.accuracy_m != b.accuracy_m)
    assert sum(1 for x in reasons(r) if x == "poor_accuracy") == n_bad
    assert err(r, ref) < 0.04


def test_invalid_coordinates():
    fixes = [
        RawFix(26.9, 75.9, 0.0, 5), RawFix(float("nan"), 75.9, 1.0, 5), RawFix(95.0, 75.9, 2.0, 5),
        RawFix(0.0, 0.0, 3.0, 5), RawFix(26.9, 200.0, 4.0, 5),
    ]
    r = process_track(fixes)
    assert reasons(r)[1:] == ["invalid_coordinates"] * 4


def test_unknown_accuracy_accepted():
    lat, lng = 26.9, 75.9
    fixes = []
    for k in range(20):
        la, ln = offset_point(lat, lng, 3.5 * k, 0)
        fixes.append(RawFix(la, ln, float(k)))
    r = process_track(fixes)
    assert r.distance_m == pytest.approx(3.5 * 19, rel=0.1)
    assert r.quality == "fair"  # unknown accuracy is never "good"


def test_bad_first_fix_reanchors():
    fixes, ref = syn.route_sharp_turns_1km(7)
    far_lat, far_lng = offset_point(fixes[0].lat, fixes[0].lng, 0, 3000)
    first = RawFix(far_lat, far_lng, fixes[0].t - 1, 8.0, 3.0)
    r = process_track([first] + fixes)
    assert r.fixes[0].accepted
    assert r.gap_count == 1
    assert r.uncertain_distance_m > 2500
    assert err(r, ref) < 0.06  # loses only the first few seconds
    # not left rejecting everything
    assert r.accepted_count > 0.45 * len(fixes)


def test_isolated_jump_not_reanchored():
    fixes, ref = syn.route_sharp_turns_1km(8)
    la, ln = offset_point(fixes[100].lat, fixes[100].lng, 400, 0)
    fixes = list(fixes)
    fixes[100] = RawFix(la, ln, fixes[100].t, 5.0, 3.0)
    r = process_track(fixes)
    assert r.fixes[100].rejection_reason == "implausible_speed"
    assert r.gap_count == 0
    assert err(r, ref) < 0.03


def test_slow_walking_accumulates():
    rng_fixes = []
    import random
    rng = random.Random(11)
    from app.gps.geodesy import offset_point as op
    for k in range(600):
        east = 0.8 * k + rng.gauss(0, 1.0)
        north = rng.gauss(0, 1.0)
        la, ln = op(26.9342, 75.9241, east, north)
        rng_fixes.append(RawFix(la, ln, 1e9 + k, 4.0, max(0.0, 0.8 + rng.gauss(0, 0.2))))
    truth = 0.8 * 599
    r = process_track(rng_fixes)
    assert r.distance_m >= 0.9 * truth
    assert r.distance_m <= 1.1 * truth


def test_kalman_on():
    for seed in range(3):
        fixes, ref = syn.track_400m_loop(seed)
        r = process_track(fixes, TrackConfig(use_kalman=True))
        assert err(r, ref) < 0.05
        acc = [f for f in r.fixes if f.accepted]
        assert all(f.filtered_lat is not None and f.filtered_lng is not None for f in acc)
        assert all(f.filtered_lat is None for f in r.fixes if not f.accepted)
        assert len(r.fixes) == len(fixes)


def test_kalman_off_by_default_and_no_mutation():
    fixes, _ = syn.track_400m_loop(0)
    snapshot = [(f.lat, f.lng, f.t, f.accuracy_m) for f in fixes]
    r = process_track(fixes)
    assert [(f.lat, f.lng, f.t, f.accuracy_m) for f in fixes] == snapshot
    assert all(f.filtered_lat is None for f in r.fixes)
    assert len(r.fixes) == len(fixes)
    assert [f.index for f in r.fixes] == list(range(len(fixes)))


def test_quality_poor_when_many_rejected():
    fixes, _ = syn.track_400m_loop(2)
    bad = syn.with_poor_accuracy(fixes, 0.9, seed=3)
    assert process_track(bad).quality == "poor"


def test_segment_consistency():
    fixes, _ = syn.urban_multipath(1)
    gapped = syn.with_gap(fixes, 300, 40)
    r = process_track(gapped)
    assert r.distance_m == pytest.approx(sum(s.distance_m for s in r.segments))
    for s in r.segments:
        assert all(r.fixes[i].accepted and r.fixes[i].segment_id == s.id for i in s.fix_indices)
    assert r.accepted_count == sum(len(s.fix_indices) for s in r.segments)
    assert r.accepted_count + r.rejected_count == len(gapped)
    assert r.moving_time_s <= gapped[-1].t - gapped[0].t
