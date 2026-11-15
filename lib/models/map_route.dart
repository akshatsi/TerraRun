import 'package:latlong2/latlong.dart';

/// One recent run drawn as a line on the map.
class MapRoute {
  final int runId;

  /// The runner; 0 when the server did not say.
  final int userId;
  final String name;
  final List<List<LatLng>> lines;

  const MapRoute({
    required this.runId,
    required this.userId,
    required this.name,
    required this.lines,
  });

  /// Where the run ended: the marker that opens the run.
  LatLng get end => lines.last.last;

  /// A `/feed` item. Null when it has no run id or no drawable line.
  static MapRoute? fromFeedItem(dynamic item) {
    if (item is! Map) return null;
    final id = item['run_id'];
    final lines = parseLines(item['route_geojson']);
    if (id is! num || lines.isEmpty) return null;
    final user = item['user'];
    return MapRoute(
      runId: id.toInt(),
      userId: user is Map && user['id'] is num
          ? (user['id'] as num).toInt()
          : 0,
      name: user is Map ? user['name']?.toString() ?? '' : '',
      lines: lines,
    );
  }

  /// One of your own runs from `/runs`. Null when it has no drawable line.
  static MapRoute? fromRun(dynamic run) {
    if (run is! Map) return null;
    final id = run['id'];
    final lines = parseLines(run['route_geojson']);
    if (id is! num || lines.isEmpty) return null;
    return MapRoute(
      runId: id.toInt(),
      userId: run['user_id'] is num ? (run['user_id'] as num).toInt() : 0,
      name: '',
      lines: lines,
    );
  }

  /// The lines of a LineString or MultiLineString, each with at least two
  /// points. Null, empty or any other geometry gives none.
  static List<List<LatLng>> parseLines(dynamic geojson) {
    if (geojson is! Map) return [];
    final coords = geojson['coordinates'];
    if (coords is! List) return [];
    switch (geojson['type']) {
      case 'LineString':
        final line = _line(coords);
        return line.length >= 2 ? [line] : [];
      case 'MultiLineString':
        return coords
            .whereType<List>()
            .map(_line)
            .where((l) => l.length >= 2)
            .toList();
    }
    return [];
  }

  static List<LatLng> _line(List coords) {
    final points = <LatLng>[];
    for (final c in coords) {
      if (c is List && c.length >= 2 && c[0] is num && c[1] is num) {
        points.add(LatLng((c[1] as num).toDouble(), (c[0] as num).toDouble()));
      }
    }
    return points;
  }
}
