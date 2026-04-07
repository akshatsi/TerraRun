// -----------------------------------------------
// TerraRun – Data Models: Territory
// -----------------------------------------------
// This file contains the territory model and the
// GeoJSON → LatLng parsing logic, which is the
// trickiest part of the map rendering pipeline.
// -----------------------------------------------

import 'package:latlong2/latlong.dart';

class TerritoryModel {
  final String userId;
  final String username;
  final String color;
  final double areaM2;

  /// Raw GeoJSON geometry object from the backend.
  /// This will be a Polygon or MultiPolygon geometry.
  final Map<String, dynamic>? polygonGeojson;

  const TerritoryModel({
    required this.userId,
    required this.username,
    required this.color,
    this.areaM2 = 0,
    this.polygonGeojson,
  });

  factory TerritoryModel.fromJson(Map<String, dynamic> json) {
    return TerritoryModel(
      userId: json['user_id'] as String,
      username: json['username'] as String,
      color: json['color'] as String? ?? '#9E9E9E',
      areaM2: (json['area_m2'] as num?)?.toDouble() ?? 0,
      polygonGeojson: json['polygon_geojson'] as Map<String, dynamic>?,
    );
  }

  double get areaKm2 => areaM2 / 1e6;

  // ─────────────────────────────────────────────────
  // GeoJSON Polygon Parsing (HEAVILY COMMENTED)
  // ─────────────────────────────────────────────────
  //
  // The backend returns territory geometries as GeoJSON.
  // Two geometry types are possible:
  //
  //   1. "Polygon" — a single polygon.
  //      Its "coordinates" field is an array of LINEAR RINGS.
  //      Each ring is an array of [lng, lat] pairs.
  //      The FIRST ring is the outer boundary; subsequent
  //      rings are holes (which we ignore for rendering).
  //
  //      Example:
  //        { "type": "Polygon",
  //          "coordinates": [
  //            [[75.0, 26.0], [75.1, 26.0], [75.1, 26.1], [75.0, 26.0]]
  //          ] }
  //
  //   2. "MultiPolygon" — a collection of polygons.
  //      Its "coordinates" field wraps each polygon in
  //      an additional array layer.
  //
  //      Example:
  //        { "type": "MultiPolygon",
  //          "coordinates": [
  //            [[[75.0, 26.0], [75.1, 26.0], ...]],  // polygon 1
  //            [[[75.2, 26.2], [75.3, 26.2], ...]]   // polygon 2
  //          ] }
  //
  // IMPORTANT: GeoJSON uses [longitude, latitude] order,
  //            but LatLng() expects (latitude, longitude).
  //            We must swap the coordinates during parsing!
  // ─────────────────────────────────────────────────

  /// Parse the GeoJSON geometry into a list of polygon
  /// rings, where each ring is a List[LatLng].
  ///
  /// Returns an empty list if there is no geometry.
  /// For MultiPolygon, all sub-polygons are flattened
  /// into a single list of rings (outer boundaries only).
  List<List<LatLng>> get parsedPolygons {
    if (polygonGeojson == null) return [];

    final type = polygonGeojson!['type'] as String?;
    final coordinates = polygonGeojson!['coordinates'];

    if (type == null || coordinates == null) return [];

    switch (type) {
      case 'Polygon':
        // "coordinates" is List<List<List<num>>>
        // i.e. List of rings, each ring is a list of [lng, lat] pairs.
        return _parsePolygonCoords(coordinates);

      case 'MultiPolygon':
        // "coordinates" is List<List<List<List<num>>>>
        // i.e. List of polygons, each polygon has its own rings.
        final List<List<LatLng>> result = [];
        for (final polygonCoords in coordinates) {
          // Each polygonCoords has the same structure as
          // a single Polygon's coordinates.
          result.addAll(_parsePolygonCoords(polygonCoords));
        }
        return result;

      default:
        // Unsupported geometry type — return empty.
        return [];
    }
  }

  /// Parse coordinates for a single Polygon geometry.
  ///
  /// Takes the "coordinates" array (list of rings) and
  /// converts only the OUTER RING (index 0) to LatLng.
  /// Interior rings (holes) are skipped for simplicity.
  static List<List<LatLng>> _parsePolygonCoords(dynamic coords) {
    final rings = coords as List<dynamic>;
    if (rings.isEmpty) return [];

    // We only take the outer boundary (first ring).
    // Additional rings are interior holes which we skip.
    final outerRing = rings[0] as List<dynamic>;

    final points = <LatLng>[];
    for (final point in outerRing) {
      final pair = point as List<dynamic>;
      // GeoJSON: [longitude, latitude] — SWAP to LatLng(lat, lng)
      final lng = (pair[0] as num).toDouble();
      final lat = (pair[1] as num).toDouble();
      points.add(LatLng(lat, lng));
    }

    return [points];
  }
}
