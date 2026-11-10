import 'dart:convert';

import 'package:fitness_game_app/data/planned_route_store.dart';
import 'package:fitness_game_app/models/route_suggestion.dart';
import 'package:fitness_game_app/services/suggestion_service.dart';
import 'package:fitness_game_app/widgets/suggestion_sheet.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> _full() => {
  'target_distance_km': 2.4,
  'pace_s_per_km': 450,
  'suggestions': [
    {
      'label': 'Most from friends',
      'reason': 'Loops the block north of GH; takes 2,400 m² from friends',
      'distance_km': 2.31,
      'estimated_minutes': 17,
      'new_area_sq_m': 8100.0,
      'stolen_area_sq_m': 2400.0,
      'stolen_from': [
        {'user_id': 7, 'name': 'Meera Kapoor', 'area_sq_m': 2400.0},
      ],
      'gain_sq_m': 10500.0,
      'route_geojson': {
        'type': 'LineString',
        'coordinates': [
          [75.92, 26.93],
          [75.93, 26.93],
          [75.93, 26.94],
          [75.92, 26.93],
        ],
      },
      'area_geojson': {
        'type': 'Polygon',
        'coordinates': [
          [
            [75.92, 26.93],
            [75.93, 26.93],
            [75.93, 26.94],
            [75.92, 26.93],
          ],
        ],
      },
    },
  ],
  'message': null,
};

void main() {
  group('SuggestionsResult.fromJson', () {
    test('parses a full answer', () {
      final r = SuggestionsResult.fromJson(_full());

      expect(r.targetDistanceKm, 2.4);
      expect(r.paceSPerKm, 450);
      expect(r.message, isNull);
      final s = r.suggestions.single;
      expect(s.label, 'Most from friends');
      expect(s.distanceKm, 2.31);
      expect(s.estimatedMinutes, 17);
      expect(s.gainSqM, 10500);
      expect(s.friendNames, 'Meera Kapoor');
      expect(s.stolenFrom.single.userId, 7);
      // GeoJSON is [lng, lat].
      expect(s.route.first.latitude, 26.93);
      expect(s.route.first.longitude, 75.92);
      expect(s.route, hasLength(4));
      expect(s.start, s.route.first);
      expect(s.areaRings.single, hasLength(4));
    });

    test('an empty answer keeps the message', () {
      final r = SuggestionsResult.fromJson({
        'target_distance_km': 2.0,
        'pace_s_per_km': 390,
        'suggestions': [],
        'message': 'No road loops near you yet',
      });

      expect(r.isEmpty, isTrue);
      expect(r.message, 'No road loops near you yet');
    });

    test('tolerates nulls and missing fields', () {
      final r = SuggestionsResult.fromJson({
        'target_distance_km': null,
        'suggestions': [
          {
            'label': null,
            'stolen_from': null,
            'route_geojson': null,
            'area_geojson': null,
            'new_area_sq_m': 100,
            'stolen_area_sq_m': 50,
          },
          {
            'route_geojson': {
              'type': 'LineString',
              'coordinates': [
                [75.9, 26.9],
                [75.91, 26.91],
                ['x', null],
                [1],
              ],
            },
            'area_geojson': {
              'type': 'MultiPolygon',
              'coordinates': [
                [[]],
                [
                  [
                    [75.9, 26.9],
                    [75.91, 26.9],
                    [75.91, 26.91],
                  ],
                ],
              ],
            },
          },
        ],
      });

      expect(r.targetDistanceKm, 0);
      expect(r.paceSPerKm, 0);
      expect(r.message, isNull);
      // The first has no route, so it is dropped.
      expect(r.suggestions, hasLength(1));
      final s = r.suggestions.single;
      expect(s.label, 'Suggested route');
      expect(s.reason, '');
      expect(s.route, hasLength(2));
      expect(s.areaRings, hasLength(1));
      expect(s.gainSqM, 0);
      expect(s.stolenFrom, isEmpty);
    });

    test('gain falls back to new plus stolen', () {
      final s = RouteSuggestion.fromJson({
        'new_area_sq_m': 100,
        'stolen_area_sq_m': 50,
      });
      expect(s.gainSqM, 150);
      expect(s.start, isNull);
      expect(s.hasRoute, isFalse);
    });

    test('an empty message string counts as none', () {
      expect(SuggestionsResult.fromJson({'message': ''}).message, isNull);
    });
  });

  group('SuggestionSheet.distanceFor', () {
    test('usual sends nothing; short and long scale the target', () {
      expect(SuggestionSheet.distanceFor(0, 2.4), isNull);
      expect(SuggestionSheet.distanceFor(1, 2.4), 1.4);
      expect(SuggestionSheet.distanceFor(2, 2.4), 3.6);
    });

    test('uses 2 km with no target, and never goes below 0.5', () {
      expect(SuggestionSheet.distanceFor(2, null), 3.0);
      expect(SuggestionSheet.distanceFor(1, 0.4), 0.5);
    });
  });

  group('SuggestionService', () {
    late List<http.Request> seen;

    setUp(() {
      SharedPreferences.setMockInitialValues({'auth_token': 'tok'});
      seen = [];
    });

    tearDown(() => SuggestionService.client = null);

    void reply(int status, Object body) {
      SuggestionService.client = MockClient((request) async {
        seen.add(request);
        return http.Response(jsonEncode(body), status);
      });
    }

    test('usual sends only the position and the token', () async {
      reply(200, _full());

      final result = await SuggestionService.getSuggestions(26.93, 75.92);

      expect(result['success'], isTrue);
      expect(
        (result['data'] as SuggestionsResult).suggestions.single.label,
        'Most from friends',
      );
      expect(seen.single.method, 'GET');
      expect(seen.single.url.path, '/suggestions');
      expect(seen.single.url.queryParameters, {'lat': '26.93', 'lng': '75.92'});
      expect(seen.single.headers['Authorization'], 'Bearer tok');
    });

    test('short and long send distance_km', () async {
      reply(200, _full());

      await SuggestionService.getSuggestions(
        26.93,
        75.92,
        distanceKm: SuggestionSheet.distanceFor(1, 2.4),
      );
      await SuggestionService.getSuggestions(
        26.93,
        75.92,
        distanceKm: SuggestionSheet.distanceFor(2, 2.4),
      );

      expect(seen[0].url.queryParameters['distance_km'], '1.40');
      expect(seen[1].url.queryParameters['distance_km'], '3.60');
      expect(seen[0].url.queryParameters.containsKey('minutes'), isFalse);
    });

    test('minutes are sent alone', () async {
      reply(200, _full());

      await SuggestionService.getSuggestions(26.93, 75.92, minutes: 25);
      await SuggestionService.getSuggestions(
        26.93,
        75.92,
        distanceKm: 3,
        minutes: 25,
      );

      expect(seen[0].url.queryParameters['minutes'], '25');
      expect(seen[0].url.queryParameters.containsKey('distance_km'), isFalse);
      // Distance wins, because the two are exclusive.
      expect(seen[1].url.queryParameters.containsKey('minutes'), isFalse);
      expect(seen[1].url.queryParameters['distance_km'], '3.00');
    });

    test('maps 401, 422 and 503 to clear messages', () async {
      reply(401, {'detail': 'Not authenticated'});
      var r = await SuggestionService.getSuggestions(1, 2);
      expect(r['success'], isFalse);
      expect(r['message'], contains('sign in'));

      reply(422, {
        'detail': [
          {'msg': 'Value error, distance_km must be positive'},
        ],
      });
      r = await SuggestionService.getSuggestions(1, 2);
      expect(r['message'], 'distance_km must be positive');

      reply(503, {'detail': 'Overpass down'});
      r = await SuggestionService.getSuggestions(1, 2);
      expect(r['message'], SuggestionService.unavailableMessage);
    });

    test('other failures use the server detail or a fallback', () async {
      reply(500, {'detail': 'Boom'});
      var r = await SuggestionService.getSuggestions(1, 2);
      expect(r['message'], 'Boom');

      reply(500, {});
      r = await SuggestionService.getSuggestions(1, 2);
      expect(r['message'], 'Could not load suggestions');
    });

    test('a network error gives the connection message', () async {
      SuggestionService.client = MockClient((_) async {
        throw http.ClientException('offline');
      });

      final r = await SuggestionService.getSuggestions(1, 2);

      expect(r['success'], isFalse);
      expect(r['message'], SuggestionService.networkMessage);
    });

    test('a body that is not an object is a failure', () async {
      reply(200, [1, 2]);
      final r = await SuggestionService.getSuggestions(1, 2);
      expect(r['success'], isFalse);
    });
  });

  group('PlannedRouteStore', () {
    final route = SuggestionsResult.fromJson(_full()).suggestions.single;

    setUp(PlannedRouteStore.clear);
    tearDown(PlannedRouteStore.clear);

    test('starts empty', () {
      expect(PlannedRouteStore.hasRoute, isFalse);
      expect(PlannedRouteStore.followingText, isNull);
    });

    test('set, read and clear notify listeners', () {
      var calls = 0;
      void listener() => calls++;
      PlannedRouteStore.current.addListener(listener);

      PlannedRouteStore.set(route);
      expect(PlannedRouteStore.hasRoute, isTrue);
      expect(PlannedRouteStore.current.value, same(route));
      expect(
        PlannedRouteStore.followingText,
        'Following: Most from friends · 2.3 km',
      );

      PlannedRouteStore.clear();
      expect(PlannedRouteStore.hasRoute, isFalse);
      expect(calls, 2);

      PlannedRouteStore.current.removeListener(listener);
    });

    test('requestRunTab notifies each time', () {
      var calls = 0;
      void listener() => calls++;
      PlannedRouteStore.runTabRequests.addListener(listener);

      PlannedRouteStore.requestRunTab();
      PlannedRouteStore.requestRunTab();

      expect(calls, 2);
      PlannedRouteStore.runTabRequests.removeListener(listener);
    });
  });
}
