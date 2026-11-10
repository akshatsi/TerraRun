import 'package:latlong2/latlong.dart';

/// Land a suggested route would take from one person you follow.
class StolenFrom {
  final int userId;
  final String name;
  final double areaSqM;

  const StolenFrom({
    required this.userId,
    required this.name,
    required this.areaSqM,
  });

  factory StolenFrom.fromJson(Map<String, dynamic> json) {
    return StolenFrom(
      userId: (json['user_id'] as num?)?.toInt() ?? 0,
      name: json['name']?.toString() ?? 'A friend',
      areaSqM: (json['area_sq_m'] as num?)?.toDouble() ?? 0,
    );
  }
}

/// One suggested loop from `GET /suggestions`. Missing fields become zero,
/// empty or null, so a partial answer still parses.
class RouteSuggestion {
  final String label;
  final String reason;
  final double distanceKm;
  final int estimatedMinutes;
  final double newAreaSqM;
  final double stolenAreaSqM;
  final List<StolenFrom> stolenFrom;
  final double gainSqM;

  /// The loop along roads, in order.
  final List<LatLng> route;

  /// Outer ring of each polygon the loop would win.
  final List<List<LatLng>> areaRings;

  const RouteSuggestion({
    required this.label,
    required this.reason,
    required this.distanceKm,
    required this.estimatedMinutes,
    required this.newAreaSqM,
    required this.stolenAreaSqM,
    required this.stolenFrom,
    required this.gainSqM,
    required this.route,
    required this.areaRings,
  });

  factory RouteSuggestion.fromJson(Map<String, dynamic> json) {
    final stolen = json['stolen_from'] is List
        ? json['stolen_from'] as List
        : const [];
    final newArea = (json['new_area_sq_m'] as num?)?.toDouble() ?? 0;
    final stolenArea = (json['stolen_area_sq_m'] as num?)?.toDouble() ?? 0;

    return RouteSuggestion(
      label: json['label']?.toString() ?? 'Suggested route',
      reason: json['reason']?.toString() ?? '',
      distanceKm: (json['distance_km'] as num?)?.toDouble() ?? 0,
      estimatedMinutes: (json['estimated_minutes'] as num?)?.round() ?? 0,
      newAreaSqM: newArea,
      stolenAreaSqM: stolenArea,
      stolenFrom: stolen
          .whereType<Map>()
          .map((e) => StolenFrom.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      gainSqM: (json['gain_sq_m'] as num?)?.toDouble() ?? newArea + stolenArea,
      route: _line(_coordinates(json['route_geojson'], 'LineString')),
      areaRings: _rings(json['area_geojson']),
    );
  }

  /// Where the loop starts, or null with no route.
  LatLng? get start => route.isEmpty ? null : route.first;

  /// The route is worth drawing.
  bool get hasRoute => route.length >= 2;

  /// "Meera Kapoor, Ravi Rao" or an empty string.
  String get friendNames => stolenFrom.map((s) => s.name).join(', ');

  static dynamic _coordinates(dynamic geo, String type) {
    if (geo is! Map || geo['type'] != type) return null;
    return geo['coordinates'];
  }

  /// GeoJSON positions are [lng, lat].
  static List<LatLng> _line(dynamic coords) {
    if (coords is! List) return [];
    return coords
        .whereType<List>()
        .where((c) => c.length >= 2 && c[0] is num && c[1] is num)
        .map((c) => LatLng((c[1] as num).toDouble(), (c[0] as num).toDouble()))
        .toList();
  }

  static List<List<LatLng>> _rings(dynamic geo) {
    if (geo is! Map) return [];
    final coords = geo['coordinates'];
    if (coords is! List) return [];

    List<LatLng>? outer(dynamic polygon) {
      if (polygon is! List || polygon.isEmpty) return null;
      final ring = _line(polygon.first);
      return ring.length >= 3 ? ring : null;
    }

    final rings = <List<LatLng>>[];
    switch (geo['type']) {
      case 'Polygon':
        final ring = outer(coords);
        if (ring != null) rings.add(ring);
      case 'MultiPolygon':
        for (final polygon in coords) {
          final ring = outer(polygon);
          if (ring != null) rings.add(ring);
        }
    }
    return rings;
  }
}

/// The answer for `GET /suggestions`.
class SuggestionsResult {
  /// The loop length the server aimed for, in km.
  final double targetDistanceKm;

  /// The runner's usual pace, in seconds per km.
  final int paceSPerKm;
  final List<RouteSuggestion> suggestions;

  /// Why the list is empty, when it is.
  final String? message;

  const SuggestionsResult({
    required this.targetDistanceKm,
    required this.paceSPerKm,
    required this.suggestions,
    required this.message,
  });

  factory SuggestionsResult.fromJson(Map<String, dynamic> json) {
    final list = json['suggestions'] is List
        ? json['suggestions'] as List
        : const [];
    final message = json['message']?.toString();

    return SuggestionsResult(
      targetDistanceKm: (json['target_distance_km'] as num?)?.toDouble() ?? 0,
      paceSPerKm: (json['pace_s_per_km'] as num?)?.round() ?? 0,
      suggestions: list
          .whereType<Map>()
          .map((e) => RouteSuggestion.fromJson(Map<String, dynamic>.from(e)))
          .where((s) => s.hasRoute)
          .toList(),
      message: message == null || message.isEmpty ? null : message,
    );
  }

  bool get isEmpty => suggestions.isEmpty;
}
