import 'package:fitness_game_app/gps/run_fix.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';

void main() {
  test('toJson matches the upload contract', () {
    final fix = RunFix(
      lat: 26.93421,
      lng: 75.92411,
      t: DateTime.utc(2026, 10, 17, 6, 1, 3),
      accuracyM: 6.5,
      speedMps: 2.9,
      headingDeg: 81,
      altitudeM: 431,
    );
    expect(fix.toJson(), {
      'lat': 26.93421,
      'lng': 75.92411,
      't': '2026-10-17T06:01:03.000Z',
      'accuracy_m': 6.5,
      'speed_mps': 2.9,
      'heading_deg': 81.0,
      'altitude_m': 431.0,
    });
  });

  test('round trip through json', () {
    final fix = RunFix(lat: 1, lng: 2, t: DateTime.utc(2026), accuracyM: 3);
    final back = RunFix.fromJson(fix.toJson());
    expect(back.t, fix.t);
    expect(back.accuracyM, 3);
    expect(back.speedMps, isNull);
  });

  test('unavailable geolocator values become null', () {
    final fix = RunFix.fromPosition(
      Position(
        latitude: 1,
        longitude: 2,
        timestamp: DateTime.utc(2026),
        accuracy: 0,
        altitude: 5,
        altitudeAccuracy: 0,
        heading: -1,
        headingAccuracy: 0,
        speed: -1,
        speedAccuracy: 0,
      ),
    );
    expect(fix.accuracyM, isNull);
    expect(fix.speedMps, isNull);
    expect(fix.headingDeg, isNull);
    expect(fix.altitudeM, 5);
  });
}
