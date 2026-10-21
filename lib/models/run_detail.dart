import 'package:latlong2/latlong.dart';

/// One kilometre of a run (the last one may be shorter).
class RunSplit {
  final int km;
  final double distanceM;
  final double durationS;
  final int paceSPerKm;
  final double? elevationChangeM;

  const RunSplit({
    required this.km,
    required this.distanceM,
    required this.durationS,
    required this.paceSPerKm,
    this.elevationChangeM,
  });

  factory RunSplit.fromJson(Map<String, dynamic> json) {
    return RunSplit(
      km: (json['km'] as num?)?.toInt() ?? 0,
      distanceM: (json['distance_m'] as num?)?.toDouble() ?? 0,
      durationS: (json['duration_s'] as num?)?.toDouble() ?? 0,
      paceSPerKm: (json['pace_s_per_km'] as num?)?.round() ?? 0,
      elevationChangeM: (json['elevation_change_m'] as num?)?.toDouble(),
    );
  }

  /// Bar length from 0 to 1: the fastest split fills the row, slower splits
  /// are shorter. Never below [min], so every row shows a bar.
  static double barFraction(
    int paceSPerKm,
    int fastestPaceSPerKm, {
    double min = 0.25,
  }) {
    if (paceSPerKm <= 0 || fastestPaceSPerKm <= 0) return min;
    return (fastestPaceSPerKm / paceSPerKm).clamp(min, 1.0);
  }
}

/// The server's answer for `GET /runs/{id}`. Fields the server cannot work
/// out are null.
class RunDetail {
  final int runId;
  final DateTime? createdAt;
  final int userId;
  final String userName;
  final bool isMine;
  final double distanceKm;
  final int durationSeconds;
  final double? movingTimeS;
  final double avgSpeedKmh;
  final int? avgPaceSPerKm;
  final double? elevationGainM;
  final double? maxSpeedKmh;
  final String? quality;
  final String territoryKind;
  final double awardedAreaSqM;
  final Map<String, dynamic>? routeGeoJson;
  final Map<String, dynamic>? awardedGeoJson;
  final List<RunSplit> splits;

  const RunDetail({
    required this.runId,
    required this.createdAt,
    required this.userId,
    required this.userName,
    required this.isMine,
    required this.distanceKm,
    required this.durationSeconds,
    required this.movingTimeS,
    required this.avgSpeedKmh,
    required this.avgPaceSPerKm,
    required this.elevationGainM,
    required this.maxSpeedKmh,
    required this.quality,
    required this.territoryKind,
    required this.awardedAreaSqM,
    required this.routeGeoJson,
    required this.awardedGeoJson,
    required this.splits,
  });

  factory RunDetail.fromJson(Map<String, dynamic> json) {
    final user = json['user'] is Map ? json['user'] as Map : const {};
    final territory = json['territory'] is Map
        ? json['territory'] as Map
        : const {};
    final splits = json['splits'] is List ? json['splits'] as List : const [];

    return RunDetail(
      runId: (json['run_id'] as num?)?.toInt() ?? 0,
      createdAt: DateTime.tryParse('${json['created_at'] ?? ''}'),
      userId: (user['id'] as num?)?.toInt() ?? 0,
      userName: user['name']?.toString() ?? 'Runner',
      isMine: json['is_mine'] == true,
      distanceKm: (json['distance_km'] as num?)?.toDouble() ?? 0,
      durationSeconds: (json['duration_seconds'] as num?)?.toInt() ?? 0,
      movingTimeS: (json['moving_time_s'] as num?)?.toDouble(),
      avgSpeedKmh: (json['avg_speed_kmh'] as num?)?.toDouble() ?? 0,
      avgPaceSPerKm: (json['avg_pace_s_per_km'] as num?)?.round(),
      elevationGainM: (json['elevation_gain_m'] as num?)?.toDouble(),
      maxSpeedKmh: (json['max_speed_kmh'] as num?)?.toDouble(),
      quality: json['quality']?.toString(),
      territoryKind: territory['kind']?.toString() ?? 'none',
      awardedAreaSqM: (territory['awarded_area_sq_m'] as num?)?.toDouble() ?? 0,
      routeGeoJson: _map(json['route_geojson']),
      awardedGeoJson: _map(json['awarded_geojson']),
      splits: splits
          .whereType<Map>()
          .map((e) => RunSplit.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
    );
  }

  static Map<String, dynamic>? _map(dynamic v) =>
      v is Map ? Map<String, dynamic>.from(v) : null;

  /// Route lines: one list of points per line of a LineString or
  /// MultiLineString. Anything else gives none.
  List<List<LatLng>> get routeLines {
    final g = routeGeoJson;
    if (g == null) return [];
    final coords = g['coordinates'];
    if (coords is! List) return [];
    switch (g['type']) {
      case 'LineString':
        return [_line(coords)];
      case 'MultiLineString':
        return coords
            .whereType<List>()
            .map(_line)
            .where((l) => l.length >= 2)
            .toList();
    }
    return [];
  }

  /// Outer rings of the awarded Polygon or MultiPolygon.
  List<List<LatLng>> get awardedRings {
    final g = awardedGeoJson;
    if (g == null) return [];
    final coords = g['coordinates'];
    if (coords is! List) return [];
    switch (g['type']) {
      case 'Polygon':
        return coords.isEmpty || coords.first is! List
            ? []
            : [_line(coords.first as List)];
      case 'MultiPolygon':
        return coords
            .whereType<List>()
            .where((p) => p.isNotEmpty && p.first is List)
            .map((p) => _line(p.first as List))
            .toList();
    }
    return [];
  }

  static List<LatLng> _line(List coords) {
    return coords
        .whereType<List>()
        .where((c) => c.length >= 2 && c[0] is num && c[1] is num)
        .map((c) => LatLng((c[1] as num).toDouble(), (c[0] as num).toDouble()))
        .toList();
  }

  /// The pace of the fastest split, or null with no splits.
  int? get fastestPace {
    final paces = splits.map((s) => s.paceSPerKm).where((p) => p > 0);
    return paces.isEmpty ? null : paces.reduce((a, b) => a < b ? a : b);
  }
}
