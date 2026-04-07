// -----------------------------------------------
// TerraRun – Providers: Run Tracking
// -----------------------------------------------
// Manages live GPS tracking during a run:
//  • Starts / stops the geolocator position stream
//  • Records a GPS point every ~5 seconds
//  • Calculates live distance using Haversine
//  • Submits the completed run to the backend
//
// THE GEOLOCATOR STREAM SETUP IS HEAVILY COMMENTED
// because it's one of the trickiest parts of the app.
// -----------------------------------------------

import 'dart:async';
import 'dart:math';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import '../models/run.dart';
import 'auth_provider.dart';
import 'runs_provider.dart';
import 'user_provider.dart';
import 'territory_provider.dart';

// ── State ────────────────────────────────────────

enum TrackingStatus { idle, tracking, submitting }

class RunTrackingState {
  final TrackingStatus status;
  final List<GpsPoint> recordedPoints;
  final List<LatLng> routeLatLngs;
  final double totalDistanceM;
  final Duration elapsed;
  final String? error;

  const RunTrackingState({
    this.status = TrackingStatus.idle,
    this.recordedPoints = const [],
    this.routeLatLngs = const [],
    this.totalDistanceM = 0,
    this.elapsed = Duration.zero,
    this.error,
  });

  RunTrackingState copyWith({
    TrackingStatus? status,
    List<GpsPoint>? recordedPoints,
    List<LatLng>? routeLatLngs,
    double? totalDistanceM,
    Duration? elapsed,
    String? error,
  }) {
    return RunTrackingState(
      status: status ?? this.status,
      recordedPoints: recordedPoints ?? this.recordedPoints,
      routeLatLngs: routeLatLngs ?? this.routeLatLngs,
      totalDistanceM: totalDistanceM ?? this.totalDistanceM,
      elapsed: elapsed ?? this.elapsed,
      error: error,
    );
  }

  String get distanceDisplay {
    if (totalDistanceM >= 1000) {
      return '${(totalDistanceM / 1000).toStringAsFixed(2)} km';
    }
    return '${totalDistanceM.toStringAsFixed(0)} m';
  }

  String get elapsedDisplay {
    final h = elapsed.inHours;
    final m = elapsed.inMinutes.remainder(60);
    final s = elapsed.inSeconds.remainder(60);
    if (h > 0) {
      return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
    }
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }
}

// ── Notifier ─────────────────────────────────────

class RunTrackingNotifier extends StateNotifier<RunTrackingState> {
  final Ref _ref;

  StreamSubscription<Position>? _positionSub;
  Timer? _timer;
  DateTime? _startedAt;

  // ─────────────────────────────────────────────────
  // GEOLOCATOR STREAM SETUP (HEAVILY COMMENTED)
  // ─────────────────────────────────────────────────
  //
  // We use geolocator's `getPositionStream()` to receive
  // continuous GPS updates while the user is running.
  //
  // Key settings in LocationSettings:
  //   • accuracy: LocationAccuracy.high
  //       → Uses GPS hardware for best precision (~3m).
  //   • distanceFilter: 5
  //       → Only fires a new event when the user moves
  //         at least 5 metres. This prevents excessive
  //         jittery points while standing still.
  //   • timeLimit: (not set)
  //       → Stream stays open indefinitely until we
  //         cancel the subscription.
  //
  // The stream delivers Position objects containing:
  //   position.latitude, position.longitude,
  //   position.altitude, position.timestamp
  //
  // We convert each Position to our GpsPoint model and
  // also to LatLng for the polyline layer on the map.
  //
  // IMPORTANT: We record a point every ~5 seconds to
  // avoid flooding the backend with too many points.
  // We throttle by tracking the timestamp of the last
  // recorded point and skipping any that arrive within
  // 5 seconds of it.
  // ─────────────────────────────────────────────────

  DateTime? _lastRecordedAt;
  static const _recordIntervalSeconds = 5;

  RunTrackingNotifier(this._ref) : super(const RunTrackingState());

  /// Start GPS tracking for a new run.
  Future<void> startTracking() async {
    // 1. Check & request location permission
    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        state = state.copyWith(error: 'Location permission denied');
        return;
      }
    }
    if (permission == LocationPermission.deniedForever) {
      state = state.copyWith(
        error: 'Location permission permanently denied. '
            'Please enable it in settings.',
      );
      return;
    }

    // 2. Check that location services are enabled
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      state = state.copyWith(error: 'Please enable location services');
      return;
    }

    // 3. Reset state
    _startedAt = DateTime.now();
    _lastRecordedAt = null;
    state = RunTrackingState(status: TrackingStatus.tracking);

    // 4. Start elapsed‑time timer (ticks every second)
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_startedAt != null) {
        state = state.copyWith(
          elapsed: DateTime.now().difference(_startedAt!),
        );
      }
    });

    // 5. Start the GPS position stream
    //    See the big comment block above for details.
    const locationSettings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 5, // metres – minimum movement to trigger update
    );

    _positionSub = Geolocator.getPositionStream(
      locationSettings: locationSettings,
    ).listen(
      _onPositionUpdate,
      onError: (error) {
        state = state.copyWith(error: 'GPS error: $error');
      },
    );
  }

  /// Called for each GPS position update from the stream.
  void _onPositionUpdate(Position position) {
    final now = DateTime.now();

    // ── Throttle: only record every 5 seconds ──
    // This keeps the data size manageable and avoids
    // spamming the backend with hundreds of near-identical
    // points when the user is moving slowly.
    if (_lastRecordedAt != null &&
        now.difference(_lastRecordedAt!).inSeconds < _recordIntervalSeconds) {
      return;
    }
    _lastRecordedAt = now;

    // Create our GPS point model
    final point = GpsPoint(
      lat: position.latitude,
      lng: position.longitude,
      altitude: position.altitude,
      timestamp: position.timestamp,
    );

    final latLng = LatLng(position.latitude, position.longitude);

    // Calculate incremental distance from the last point
    double newDistance = state.totalDistanceM;
    if (state.routeLatLngs.isNotEmpty) {
      final prev = state.routeLatLngs.last;
      newDistance += _haversineDistance(prev, latLng);
    }

    state = state.copyWith(
      recordedPoints: [...state.recordedPoints, point],
      routeLatLngs: [...state.routeLatLngs, latLng],
      totalDistanceM: newDistance,
    );
  }

  /// Stop tracking and submit the run to the backend.
  Future<RunModel?> finishRun() async {
    // Stop the GPS stream and timer
    await _positionSub?.cancel();
    _timer?.cancel();
    _positionSub = null;
    _timer = null;

    if (state.recordedPoints.length < 2) {
      state = state.copyWith(
        status: TrackingStatus.idle,
        error: 'Need at least 2 GPS points to record a run',
      );
      return null;
    }

    state = state.copyWith(status: TrackingStatus.submitting);

    try {
      final api = _ref.read(apiServiceProvider);
      final run = await api.submitRun(
        gpsPoints: state.recordedPoints,
        startedAt: _startedAt!,
        endedAt: DateTime.now(),
      );

      // Invalidate cached data so dashboard/map refresh
      _ref.invalidate(runsProvider);
      _ref.invalidate(userProvider);
      _ref.invalidate(myTerritoryProvider);

      state = const RunTrackingState(status: TrackingStatus.idle);
      return run;
    } catch (e) {
      state = state.copyWith(
        status: TrackingStatus.idle,
        error: 'Failed to submit run: $e',
      );
      return null;
    }
  }

  /// Cancel tracking without submitting.
  Future<void> cancelTracking() async {
    await _positionSub?.cancel();
    _timer?.cancel();
    _positionSub = null;
    _timer = null;
    state = const RunTrackingState(status: TrackingStatus.idle);
  }

  @override
  void dispose() {
    _positionSub?.cancel();
    _timer?.cancel();
    super.dispose();
  }

  // ── Haversine distance (metres) ────────────────

  static double _haversineDistance(LatLng a, LatLng b) {
    const R = 6371000.0; // Earth radius in metres
    final dLat = _toRad(b.latitude - a.latitude);
    final dLng = _toRad(b.longitude - a.longitude);
    final sinLat = sin(dLat / 2);
    final sinLng = sin(dLng / 2);
    final h = sinLat * sinLat +
        cos(_toRad(a.latitude)) * cos(_toRad(b.latitude)) * sinLng * sinLng;
    return R * 2 * atan2(sqrt(h), sqrt(1 - h));
  }

  static double _toRad(double deg) => deg * pi / 180;
}

// ── Provider ─────────────────────────────────────

final runTrackingProvider =
    StateNotifierProvider<RunTrackingNotifier, RunTrackingState>((ref) {
  return RunTrackingNotifier(ref);
});
