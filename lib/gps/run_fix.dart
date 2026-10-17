import 'package:geolocator/geolocator.dart';

/// One raw GPS reading, as the server expects it (see docs/gps-accuracy.md).
class RunFix {
  final double lat;
  final double lng;

  /// The fix's own GPS time, in UTC.
  final DateTime t;
  final double? accuracyM;
  final double? speedMps;
  final double? headingDeg;
  final double? altitudeM;

  const RunFix({
    required this.lat,
    required this.lng,
    required this.t,
    this.accuracyM,
    this.speedMps,
    this.headingDeg,
    this.altitudeM,
  });

  /// Geolocator reports "unavailable" as 0 accuracy or a negative speed or
  /// heading; those become null.
  factory RunFix.fromPosition(Position p) {
    return RunFix(
      lat: p.latitude,
      lng: p.longitude,
      t: p.timestamp.toUtc(),
      accuracyM: p.accuracy > 0 ? p.accuracy : null,
      speedMps: p.speed >= 0 ? p.speed : null,
      headingDeg: p.heading >= 0 ? p.heading : null,
      altitudeM: p.altitude,
    );
  }

  factory RunFix.fromJson(Map<String, dynamic> json) {
    double? num_(String key) => (json[key] as num?)?.toDouble();
    return RunFix(
      lat: (json['lat'] as num).toDouble(),
      lng: (json['lng'] as num).toDouble(),
      t: DateTime.parse(json['t'] as String).toUtc(),
      accuracyM: num_('accuracy_m'),
      speedMps: num_('speed_mps'),
      headingDeg: num_('heading_deg'),
      altitudeM: num_('altitude_m'),
    );
  }

  Map<String, dynamic> toJson() => {
    'lat': lat,
    'lng': lng,
    't': t.toUtc().toIso8601String(),
    'accuracy_m': accuracyM,
    'speed_mps': speedMps,
    'heading_deg': headingDeg,
    'altitude_m': altitudeM,
  };
}
