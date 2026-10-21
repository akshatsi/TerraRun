import 'dart:math' as math;
import 'run_fix.dart';

/// Thresholds for the live filter. The defaults match the server's
/// `TrackConfig` (docs/gps-accuracy.md, section 2).
class TrackConfig {
  final double preferredAccuracyM;
  final double maxAccuracyM;
  final double minDisplacementM;
  final double accuracyDisplacementFactor;
  final double stationarySpeedMps;
  final double maxSpeedMps;
  final double longGapS;

  /// A run that ends within this distance of its start, after at least
  /// [minLoopPerimeterM] of path, and whose end-to-start gap is at most
  /// [maxClosureFraction] of the path, is a loop. These mirror the server's
  /// `ShapeConfig` (`closure_radius_m`, `min_loop_perimeter_m`,
  /// `max_closure_fraction`).
  final double closureRadiusM;
  final double minLoopPerimeterM;
  final double maxClosureFraction;

  /// Phone only: how near the start a runner must be to see the loop hint.
  final double loopHintRadiusM;

  const TrackConfig({
    this.preferredAccuracyM = 10,
    this.maxAccuracyM = 20,
    this.minDisplacementM = 4,
    this.accuracyDisplacementFactor = 0.5,
    this.stationarySpeedMps = 0.5,
    this.maxSpeedMps = 12.0,
    this.longGapS = 15,
    this.closureRadiusM = 200,
    this.minLoopPerimeterM = 100,
    this.maxClosureFraction = 0.25,
    this.loopHintRadiusM = 300,
  });
}

/// Why a fix did not count. Same names as the server's rejection reasons.
enum RejectReason {
  duplicate,
  outOfOrder,
  poorAccuracy,
  implausibleSpeed,
  stationary,
  invalidCoordinates,
}

class FilterDecision {
  /// The fix moved the anchor and joined a segment. A stationary fix is not
  /// accepted here: the server keeps it, but it adds nothing to the route.
  final bool accepted;
  final RejectReason? reason;

  /// Metres added to the distance by this fix.
  final double addedM;

  const FilterDecision(this.accepted, this.reason, this.addedM);
}

/// Distance between two points in metres (haversine). Only used for the live
/// display; the server's geodesic value replaces it.
double haversineM(double lat1, double lng1, double lat2, double lng2) {
  const r = 6371008.8;
  double rad(double d) => d * math.pi / 180;
  final dLat = rad(lat2 - lat1);
  final dLng = rad(lng2 - lng1);
  final a =
      math.pow(math.sin(dLat / 2), 2) +
      math.cos(rad(lat1)) *
          math.cos(rad(lat2)) *
          math.pow(math.sin(dLng / 2), 2);
  return 2 * r * math.asin(math.min(1.0, math.sqrt(a)));
}

/// Incremental port of the server's distance checks. Feed it every fix in
/// order with [add].
class TrackFilter {
  final TrackConfig config;

  TrackFilter({this.config = const TrackConfig()});

  /// Fixes in a row that must agree before the anchor moves to a new place.
  static const _reanchorAfter = 3;

  final List<List<RunFix>> _segments = [];
  RunFix? _anchor;
  DateTime? _lastT;

  // Time of the last kept fix, stationary ones included; gaps and speed are
  // measured from it while the anchor keeps the position.
  DateTime? _keptT;
  final List<RunFix> _implausible = [];

  double distanceM = 0;

  /// Straight-line distance across gaps and re-anchors, never counted.
  double uncertainM = 0;
  int gapCount = 0;
  int acceptedCount = 0;
  int rejectedCount = 0;

  double get distanceKm => distanceM / 1000;

  /// Metres from the first accepted fix to the latest one; null before two
  /// fixes are accepted.
  double? get startDistanceM {
    if (acceptedCount < 2) return null;
    final first = _segments.first.first;
    final last = _segments.last.last;
    return haversineM(first.lat, first.lng, last.lat, last.lng);
  }

  /// The path is long enough for a loop, whether or not it has closed.
  bool get loopLongEnough => distanceM >= config.minLoopPerimeterM;

  /// Same test as the server's start-to-end join: back within the closure
  /// radius of the start, after enough path, with the join a small part of
  /// the loop. Gaps do not count toward the path. (The server also counts
  /// loops where the path crosses or nearly meets itself; the phone only
  /// hints at the start-to-end case.)
  bool get isLoopClosed {
    final d = startDistanceM;
    return d != null &&
        loopLongEnough &&
        d <= config.closureRadiusM &&
        d <= config.maxClosureFraction * distanceM;
  }

  /// Accepted fixes, one list per segment. Draw one line per list so no line
  /// crosses a gap.
  List<List<RunFix>> get segments => _segments;

  FilterDecision add(RunFix fix) {
    final decision = _decide(fix);
    if (decision.accepted) {
      acceptedCount++;
    } else if (decision.reason != RejectReason.stationary) {
      rejectedCount++;
    }
    return decision;
  }

  FilterDecision _reject(RejectReason reason) =>
      FilterDecision(false, reason, 0);

  FilterDecision _decide(RunFix fix) {
    if (!fix.lat.isFinite ||
        !fix.lng.isFinite ||
        fix.lat.abs() > 90 ||
        fix.lng.abs() > 180 ||
        (fix.lat == 0 && fix.lng == 0)) {
      return _reject(RejectReason.invalidCoordinates);
    }

    final last = _lastT;
    if (last != null) {
      if (fix.t == last) return _reject(RejectReason.duplicate);
      if (fix.t.isBefore(last)) return _reject(RejectReason.outOfOrder);
    }
    _lastT = fix.t;

    final accuracy = fix.accuracyM;
    if (accuracy != null && accuracy > config.maxAccuracyM) {
      return _reject(RejectReason.poorAccuracy);
    }

    final anchor = _anchor;
    if (anchor == null) return _startSegment(fix);

    final dt = fix.t.difference(_keptT ?? anchor.t).inMicroseconds / 1e6;
    if (dt > config.longGapS) {
      // Not bridged: the line across the gap is not counted.
      gapCount++;
      uncertainM += haversineM(anchor.lat, anchor.lng, fix.lat, fix.lng);
      return _startSegment(fix);
    }

    final d = haversineM(anchor.lat, anchor.lng, fix.lat, fix.lng);
    final combined = _combinedAccuracy(anchor, fix);

    final smallMove =
        d < config.minDisplacementM ||
        d < config.accuracyDisplacementFactor * combined;
    final slowSmallMove =
        (fix.speedMps ?? double.infinity) < config.stationarySpeedMps &&
        d < 2 * config.minDisplacementM;
    if (smallMove || slowSmallMove) {
      _implausible.clear();
      _keptT = fix.t;
      return _reject(RejectReason.stationary);
    }

    // A jump the fixes' own error can explain is forgiven.
    final speed = math.max(0.0, d - combined) / dt;
    if (speed > config.maxSpeedMps) {
      return _implausibleFix(fix);
    }

    _implausible.clear();
    _anchor = fix;
    _keptT = fix.t;
    _segments.last.add(fix);
    distanceM += d;
    return FilterDecision(true, null, d);
  }

  FilterDecision _startSegment(RunFix fix) {
    _implausible.clear();
    _anchor = fix;
    _keptT = fix.t;
    _segments.add([fix]);
    return FilterDecision(true, null, 0);
  }

  /// A fix far from the anchor. When several in a row agree with each other
  /// the anchor itself was wrong, so move it there and start a new segment
  /// without counting the jump.
  FilterDecision _implausibleFix(RunFix fix) {
    if (_implausible.isNotEmpty) {
      final prev = _implausible.last;
      final dt = fix.t.difference(prev.t).inMicroseconds / 1e6;
      final d = haversineM(prev.lat, prev.lng, fix.lat, fix.lng);
      final combined = _combinedAccuracy(prev, fix);
      final consistent =
          dt > 0 && math.max(0.0, d - combined) / dt <= config.maxSpeedMps;
      if (!consistent) _implausible.clear();
    }
    _implausible.add(fix);

    if (_implausible.length >= _reanchorAfter) {
      return _startSegment(fix);
    }
    return _reject(RejectReason.implausibleSpeed);
  }

  double _combinedAccuracy(RunFix a, RunFix b) {
    final x = a.accuracyM ?? config.preferredAccuracyM;
    final y = b.accuracyM ?? config.preferredAccuracyM;
    return math.sqrt(x * x + y * y);
  }
}
