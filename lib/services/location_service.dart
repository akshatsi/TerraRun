import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import '../data/run_data.dart';

enum LocationStatus { unknown, serviceOff, denied, deniedForever, ready }

/// App-wide access to the device position.
///
/// Passive tracking starts once the user is signed in, so the map and run
/// screens follow the user before a run starts. A run adds its own stream
/// (see [runSettings]) and publishes into the same place.
class LocationService {
  LocationService._();

  static StreamSubscription<Position>? _subscription;
  static bool _starting = false;

  static final ValueNotifier<LocationStatus> status = ValueNotifier(
    LocationStatus.unknown,
  );
  static final ValueNotifier<Position?> latest = ValueNotifier(null);

  /// The last error from the device or browser, cleared by the next fix.
  static final ValueNotifier<Object?> error = ValueNotifier(null);

  /// Checks that location is on and allowed, asking the user if needed.
  static Future<LocationStatus> ensurePermission() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      return _setStatus(LocationStatus.serviceOff);
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied) {
      return _setStatus(LocationStatus.denied);
    }
    if (permission == LocationPermission.deniedForever) {
      return _setStatus(LocationStatus.deniedForever);
    }
    return _setStatus(LocationStatus.ready);
  }

  static LocationStatus _setStatus(LocationStatus value) {
    status.value = value;
    return value;
  }

  /// Follows the user while the app is open. Safe to call more than once.
  static Future<void> startPassive() async {
    if (_subscription != null || _starting) return;
    _starting = true;

    try {
      final result = await ensurePermission();
      if (result != LocationStatus.ready) return;

      _ensureStream();
      // The stream only reports movement, so ask once for the first fix.
      await _fetchPosition();
    } catch (e) {
      report(e);
    } finally {
      _starting = false;
    }
  }

  /// Tries again for a position, for the "find me" button, and makes sure
  /// live tracking is running. Returns whether a position was found.
  static Future<bool> requestFix() async {
    final access = await ensurePermission();
    if (access != LocationStatus.ready) return false;

    _ensureStream();
    return _fetchPosition();
  }

  /// Called when the app comes back to the front: if tracking never started
  /// because location was off or blocked, try again now that it may be fixed.
  static Future<void> resume() async {
    if (_subscription != null) return;
    // A dismissed permission prompt is not asked again on every return.
    if (status.value == LocationStatus.denied) return;
    await startPassive();
  }

  static void _ensureStream() {
    if (_subscription != null) return;

    _subscription = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 5,
      ),
    ).listen(publish, onError: report);
  }

  static Future<bool> _fetchPosition() async {
    try {
      publish(await Geolocator.getCurrentPosition());
      return true;
    } catch (e) {
      report(e);
      return false;
    }
  }

  static void report(Object problem) {
    debugPrint('Location error: $problem');
    error.value = problem;
  }

  static Future<void> stopPassive() async {
    await _subscription?.cancel();
    _subscription = null;
  }

  /// Records a new position for the whole app.
  static void publish(Position position) {
    RunDataStore.currentLatitude = position.latitude;
    RunDataStore.currentLongitude = position.longitude;
    if (kDebugMode) {
      debugPrint(
        'Location fix: ${position.latitude.toStringAsFixed(4)}, '
        '${position.longitude.toStringAsFixed(4)} '
        '(+/-${position.accuracy.round()} m)',
      );
    }
    error.value = null;
    latest.value = position;
  }

  /// Short note for the run and map screens while location is not working,
  /// or null once a position is known.
  static String? get hint {
    switch (status.value) {
      case LocationStatus.serviceOff:
        return 'Turn on location services';
      case LocationStatus.denied:
        return 'Allow location to start';
      case LocationStatus.deniedForever:
        return kIsWeb ? 'Location is blocked' : 'Allow location from settings';
      case LocationStatus.ready:
        if (latest.value != null) return null;
        return error.value == null
            ? 'Finding your location…'
            : "Can't find your location";
      case LocationStatus.unknown:
        return null;
    }
  }

  /// A line on what to try, shown under [hint].
  static String? get hintDetail {
    switch (status.value) {
      case LocationStatus.deniedForever:
        return kIsWeb
            ? 'Allow location for this site (lock icon in the address bar) '
                  'and turn on Location Services for your browser.'
            : null;
      case LocationStatus.ready:
        if (latest.value != null || error.value == null) return null;
        return kIsWeb
            ? 'Turn on Location Services for your browser in System '
                  'Settings, then tap the target icon.'
            : 'Check that location is on and you have a clear view of the '
                  'sky, then tap the target icon.';
      default:
        return null;
    }
  }

  /// Settings for the stream that records a run. On phones this keeps the
  /// stream alive with the screen off: a foreground notification on Android
  /// and background updates on iOS.
  static LocationSettings runSettings() {
    const accuracy = LocationAccuracy.best;
    const distanceFilter = 3;

    if (kIsWeb) {
      return const LocationSettings(
        accuracy: accuracy,
        distanceFilter: distanceFilter,
      );
    }

    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return AndroidSettings(
          accuracy: accuracy,
          distanceFilter: distanceFilter,
          foregroundNotificationConfig: const ForegroundNotificationConfig(
            notificationTitle: 'TerraRun is tracking your run',
            notificationText: 'Your route is being recorded.',
            enableWakeLock: true,
            setOngoing: true,
          ),
        );
      case TargetPlatform.iOS:
        return AppleSettings(
          accuracy: accuracy,
          distanceFilter: distanceFilter,
          activityType: ActivityType.fitness,
          pauseLocationUpdatesAutomatically: false,
          showBackgroundLocationIndicator: true,
          allowBackgroundLocationUpdates: true,
        );
      default:
        return const LocationSettings(
          accuracy: accuracy,
          distanceFilter: distanceFilter,
        );
    }
  }
}
