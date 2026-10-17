import 'dart:math' as math;
import 'package:fitness_game_app/gps/run_fix.dart';
import 'package:fitness_game_app/gps/track_filter.dart';
import 'package:flutter_test/flutter_test.dart';

final _t0 = DateTime.utc(2026, 10, 17, 6);

// Metres per degree of latitude; longitude is scaled near the equator.
const _mPerDeg = 111195.0;

RunFix fix(
  double northM,
  double eastM,
  int sec, {
  double? acc = 5,
  double? speed,
}) {
  return RunFix(
    lat: 10 + northM / _mPerDeg,
    lng: 20 + eastM / _mPerDeg / math.cos(10 * math.pi / 180),
    t: _t0.add(Duration(seconds: sec)),
    accuracyM: acc,
    speedMps: speed,
  );
}

void main() {
  loopTests();
  test('stationary jitter adds almost nothing', () {
    final f = TrackFilter();
    final rng = math.Random(1);
    for (var i = 0; i < 120; i++) {
      f.add(fix(rng.nextDouble() * 2 - 1, rng.nextDouble() * 2 - 1, i));
    }
    expect(f.distanceM, lessThan(5));
    expect(f.gapCount, 0);
  });

  test('straight run accumulates within a few percent', () {
    final f = TrackFilter();
    final rng = math.Random(2);
    for (var i = 0; i <= 300; i++) {
      f.add(
        fix(i * 3.0 + rng.nextDouble() * 2 - 1, rng.nextDouble() * 2 - 1, i),
      );
    }
    expect(f.distanceM, closeTo(900, 900 * 0.05));
    expect(f.segments.length, 1);
  });

  test('a jump is rejected and does not move the anchor', () {
    final f = TrackFilter();
    f.add(fix(0, 0, 0));
    f.add(fix(3, 0, 1));
    final d = f.add(fix(500, 0, 2));
    expect(d.accepted, isFalse);
    expect(d.reason, RejectReason.implausibleSpeed);
    f.add(fix(6, 0, 3));
    expect(f.distanceM, closeTo(6, 0.5));
  });

  test('a poor-accuracy fix is rejected', () {
    final f = TrackFilter();
    f.add(fix(0, 0, 0));
    final d = f.add(fix(10, 0, 1, acc: 50));
    expect(d.reason, RejectReason.poorAccuracy);
  });

  test('a jump explained by accuracy is forgiven', () {
    final f = TrackFilter();
    f.add(fix(0, 0, 0, acc: 20));
    // 30 m in 1 s is 30 m/s, but two 20 m fixes can explain 28 m of it.
    final d = f.add(fix(30, 0, 1, acc: 20));
    expect(d.accepted, isTrue);
  });

  test('stationary fixes add no distance and keep the anchor', () {
    final f = TrackFilter();
    f.add(fix(0, 0, 0));
    expect(f.add(fix(1, 0, 1)).reason, RejectReason.stationary);
    expect(f.add(fix(2, 0, 2)).reason, RejectReason.stationary);
    f.add(fix(8, 0, 3));
    expect(f.distanceM, closeTo(8, 0.5));
  });

  test('a gap splits the segment and is not bridged', () {
    final f = TrackFilter();
    for (var i = 0; i < 5; i++) {
      f.add(fix(i * 3.0, 0, i));
    }
    for (var i = 0; i < 5; i++) {
      f.add(fix(500 + i * 3.0, 0, 60 + i));
    }
    expect(f.gapCount, 1);
    expect(f.segments.length, 2);
    expect(f.distanceM, closeTo(24, 1));
    expect(f.uncertainM, greaterThan(400));
  });

  test('three consistent far fixes re-anchor without counting the jump', () {
    final f = TrackFilter();
    f.add(fix(0, 0, 0));
    f.add(fix(6, 0, 1));
    expect(f.add(fix(1000, 0, 2)).accepted, isFalse);
    expect(f.add(fix(1003, 0, 3)).accepted, isFalse);
    final d = f.add(fix(1006, 0, 4));
    expect(d.accepted, isTrue);
    expect(d.addedM, 0);
    expect(f.segments.length, 2);
    f.add(fix(1011, 0, 5));
    expect(f.distanceM, closeTo(6 + 5, 1));
  });

  test('duplicate and out-of-order fixes are rejected', () {
    final f = TrackFilter();
    f.add(fix(0, 0, 5));
    expect(f.add(fix(10, 0, 5)).reason, RejectReason.duplicate);
    expect(f.add(fix(10, 0, 3)).reason, RejectReason.outOfOrder);
    expect(f.distanceM, 0);
  });

  test('invalid coordinates are rejected', () {
    final f = TrackFilter();
    final bad = RunFix(lat: 95, lng: 0, t: _t0);
    expect(f.add(bad).reason, RejectReason.invalidCoordinates);
  });
}

/// Walks a square of [side] metres at 5 m/s, then heads back toward the
/// start and stops [endGap] metres short of it.
TrackFilter _squareRun(double side, double endGap) {
  final f = TrackFilter();
  var sec = 0;
  void walk(double n0, double e0, double n1, double e1) {
    final len = math.sqrt(math.pow(n1 - n0, 2) + math.pow(e1 - e0, 2));
    final steps = (len / 5).round();
    for (var i = 1; i <= steps; i++) {
      final k = i / steps;
      f.add(fix(n0 + (n1 - n0) * k, e0 + (e1 - e0) * k, sec++, speed: 5));
    }
  }

  f.add(fix(0, 0, sec++, speed: 5));
  walk(0, 0, 0, side);
  walk(0, side, side, side);
  walk(side, side, side, 0);
  walk(side, 0, endGap, 0);
  return f;
}

void loopTests() {
  test('square ending 15 m from the start is a closed loop', () {
    final f = _squareRun(60, 15);
    expect(f.startDistanceM, closeTo(15, 1));
    expect(f.isLoopClosed, isTrue);
  });

  test('square ending 30 m from the start is not closed', () {
    final f = _squareRun(60, 30);
    expect(f.startDistanceM, closeTo(30, 1));
    expect(f.isLoopClosed, isFalse);
    expect(f.loopLongEnough, isTrue);
  });

  test('an 80 m path ending at the start is too short', () {
    final f = TrackFilter();
    var sec = 0;
    for (var i = 0; i <= 8; i++) {
      f.add(fix(i * 5.0, 0, sec++, speed: 5));
    }
    for (var i = 7; i >= 0; i--) {
      f.add(fix(i * 5.0, 0, sec++, speed: 5));
    }
    expect(f.distanceM, lessThan(100));
    expect(f.startDistanceM, lessThan(20));
    expect(f.isLoopClosed, isFalse);
  });
}
