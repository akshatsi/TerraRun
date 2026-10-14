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

  static final ValueNotifier<LocationStatus> status =
      ValueNotifier(LocationStatus.unknown);
  static final ValueNotifier<Position?> latest = ValueNotifier(null);

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

      _subscription = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          distanceFilter: 5,
        ),
      ).listen(
        publish,
        onError: (Object error) => debugPrint('Location stream error: $error'),
      );

      // The stream only reports movement, so ask once for the first fix.
      publish(await Geolocator.getCurrentPosition());
    } catch (e) {
      debugPrint('Location start error: $e');
    } finally {
      _starting = false;
    }
  }

  static Future<void> stopPassive() async {
    await _subscription?.cancel();
    _subscription = null;
  }

  /// Records a new position for the whole app.
  static void publish(Position position) {
    RunDataStore.currentLatitude = position.latitude;
    RunDataStore.currentLongitude = position.longitude;
    latest.value = position;
  }

  /// Short note for the run screen while it waits on location, or null.
  static String? get hint {
    switch (status.value) {
      case LocationStatus.serviceOff:
        return 'Turn on location services';
      case LocationStatus.denied:
        return 'Allow location to start';
      case LocationStatus.deniedForever:
        return 'Allow location from settings';
      case LocationStatus.ready:
        return latest.value == null ? 'Finding your location…' : null;
      case LocationStatus.unknown:
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
