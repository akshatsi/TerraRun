import 'package:fitness_game_app/models/map_route.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses LineString and MultiLineString', () {
    expect(
      MapRoute.parseLines({
        'type': 'LineString',
        'coordinates': [
          [77.2, 28.6],
          [77.3, 28.7],
        ],
      }).single.length,
      2,
    );
    final multi = MapRoute.parseLines({
      'type': 'MultiLineString',
      'coordinates': [
        [
          [77.2, 28.6],
          [77.3, 28.7],
        ],
        [
          [77.4, 28.8],
        ],
      ],
    });
    expect(multi.length, 1);
    expect(multi.first.first.latitude, 28.6);
    expect(multi.first.first.longitude, 77.2);
  });

  test('null, empty and odd geometry give no lines', () {
    expect(MapRoute.parseLines(null), isEmpty);
    expect(
      MapRoute.parseLines({'type': 'LineString', 'coordinates': []}),
      isEmpty,
    );
    expect(
      MapRoute.parseLines({
        'type': 'Point',
        'coordinates': [1, 2],
      }),
      isEmpty,
    );
    expect(MapRoute.parseLines({'type': 'LineString'}), isEmpty);
  });

  test('feed item and own run', () {
    final geo = {
      'type': 'LineString',
      'coordinates': [
        [77.2, 28.6],
        [77.3, 28.7],
      ],
    };
    final f = MapRoute.fromFeedItem({
      'run_id': 41,
      'user': {'id': 7, 'name': 'Meera'},
      'route_geojson': geo,
    })!;
    expect((f.runId, f.userId, f.name), (41, 7, 'Meera'));
    expect(f.end.latitude, 28.7);
    expect(MapRoute.fromFeedItem({'run_id': 1, 'route_geojson': null}), isNull);
    expect(
      MapRoute.fromRun({'id': 5, 'user_id': 2, 'route_geojson': geo})!.runId,
      5,
    );
  });
}
