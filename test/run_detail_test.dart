import 'dart:convert';

import 'package:fitness_game_app/models/run_detail.dart';
import 'package:fitness_game_app/services/run_service.dart';
import 'package:fitness_game_app/services/social_service.dart';
import 'package:fitness_game_app/utils/format.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> _full() => {
  'run_id': 41,
  'created_at': '2026-10-21T06:31:40Z',
  'user': {'id': 7, 'name': 'Meera Kapoor'},
  'is_mine': false,
  'distance_km': 4.71,
  'duration_seconds': 1838,
  'moving_time_s': 1801.0,
  'avg_speed_kmh': 9.41,
  'avg_pace_s_per_km': 382,
  'elevation_gain_m': 23.0,
  'max_speed_kmh': 14.2,
  'quality': 'good',
  'territory': {'kind': 'loop', 'awarded_area_sq_m': 3240.0, 'reason': 'x'},
  'route_geojson': {
    'type': 'MultiLineString',
    'coordinates': [
      [
        [77.2, 28.6],
        [77.21, 28.61],
      ],
      [
        [77.22, 28.62],
        [77.23, 28.63],
      ],
    ],
  },
  'awarded_geojson': {
    'type': 'Polygon',
    'coordinates': [
      [
        [77.2, 28.6],
        [77.21, 28.6],
        [77.21, 28.61],
        [77.2, 28.6],
      ],
    ],
  },
  'splits': [
    {
      'km': 1,
      'distance_m': 1000,
      'duration_s': 371,
      'pace_s_per_km': 371,
      'elevation_change_m': 4.0,
    },
    {
      'km': 5,
      'distance_m': 710,
      'duration_s': 270.5,
      'pace_s_per_km': 380,
      'elevation_change_m': null,
    },
  ],
};

void main() {
  group('RunDetail.fromJson', () {
    test('reads every field', () {
      final run = RunDetail.fromJson(_full());
      expect(run.runId, 41);
      expect(run.userName, 'Meera Kapoor');
      expect(run.userId, 7);
      expect(run.isMine, isFalse);
      expect(run.movingTimeS, 1801.0);
      expect(run.avgPaceSPerKm, 382);
      expect(run.elevationGainM, 23.0);
      expect(run.maxSpeedKmh, 14.2);
      expect(run.territoryKind, 'loop');
      expect(run.awardedAreaSqM, 3240.0);
      expect(run.splits, hasLength(2));
      expect(run.splits[1].elevationChangeM, isNull);
      expect(run.splits[1].durationS, 270.5);
      expect(run.fastestPace, 371);
    });

    test('builds one line per MultiLineString line and the outer ring', () {
      final run = RunDetail.fromJson(_full());
      expect(run.routeLines, hasLength(2));
      expect(run.routeLines.first.first.latitude, 28.6);
      expect(run.routeLines.first.first.longitude, 77.2);
      expect(run.awardedRings, hasLength(1));
      expect(run.awardedRings.first, hasLength(4));
    });

    test('accepts nulls and an empty split list', () {
      final run = RunDetail.fromJson({
        'run_id': 3,
        'created_at': '2026-10-21T06:31:40Z',
        'user': {'id': 1, 'name': 'Me'},
        'is_mine': true,
        'distance_km': 0.0,
        'duration_seconds': 0,
        'moving_time_s': null,
        'avg_speed_kmh': 0.0,
        'avg_pace_s_per_km': null,
        'elevation_gain_m': null,
        'max_speed_kmh': null,
        'quality': null,
        'territory': {'kind': 'none', 'awarded_area_sq_m': 0.0, 'reason': ''},
        'route_geojson': null,
        'awarded_geojson': null,
        'splits': [],
      });
      expect(run.isMine, isTrue);
      expect(run.movingTimeS, isNull);
      expect(run.avgPaceSPerKm, isNull);
      expect(run.elevationGainM, isNull);
      expect(run.maxSpeedKmh, isNull);
      expect(run.quality, isNull);
      expect(run.routeLines, isEmpty);
      expect(run.awardedRings, isEmpty);
      expect(run.splits, isEmpty);
      expect(run.fastestPace, isNull);
    });
  });

  group('formatters', () {
    test('pace reads as m:ss', () {
      expect(Fmt.pace(382), '6:22');
      expect(Fmt.pace(300), '5:00');
      expect(Fmt.pace(65), '1:05');
      expect(Fmt.pace(null), '—');
      expect(Fmt.pace(0), '—');
    });

    test('durationFrom rounds fractional seconds', () {
      expect(Fmt.durationFrom(1801.4), '30:01');
      expect(Fmt.durationFrom(3725), '01:02:05');
      expect(Fmt.durationFrom(0), '00:00');
    });
  });

  group('split bar', () {
    test('the fastest split fills the row, slower ones are shorter', () {
      expect(RunSplit.barFraction(300, 300), 1.0);
      expect(RunSplit.barFraction(400, 300), closeTo(0.75, 1e-9));
    });

    test('never shrinks below the minimum and survives bad input', () {
      expect(RunSplit.barFraction(3000, 300), 0.25);
      expect(RunSplit.barFraction(0, 300), 0.25);
      expect(RunSplit.barFraction(300, 0), 0.25);
    });
  });

  group('share text', () {
    test('names the runner, distance and territory', () {
      expect(
        Fmt.shareText(name: 'Akshat', distanceKm: 25.5, territorySqM: 2720),
        'Follow me on TerraRun — Akshat · 25.5 km run · 2,720 m² territory',
      );
    });

    test('leaves out territory when there is none', () {
      expect(
        Fmt.shareText(name: 'Akshat', distanceKm: 0, territorySqM: 0),
        'Follow me on TerraRun — Akshat · 0.0 km run',
      );
    });
  });

  group('services', () {
    setUp(() => SharedPreferences.setMockInitialValues({'auth_token': 'tok'}));
    tearDown(() {
      SocialService.client = null;
      RunService.client = null;
    });

    test(
      'updateProfile sends a PATCH with name and bio, and stores the name',
      () async {
        late http.Request seen;
        SocialService.client = MockClient((request) async {
          seen = request;
          return http.Response(
            jsonEncode({'id': 1, 'name': 'Akshat S', 'bio': 'Hi'}),
            200,
          );
        });

        final result = await SocialService.updateProfile(' Akshat S ', ' Hi ');

        expect(result['success'], isTrue);
        expect(seen.method, 'PATCH');
        expect(seen.url.path, '/users/me');
        expect(seen.headers['Authorization'], 'Bearer tok');
        expect(jsonDecode(seen.body), {'name': 'Akshat S', 'bio': 'Hi'});
        final prefs = await SharedPreferences.getInstance();
        expect(prefs.getString('user_name'), 'Akshat S');
      },
    );

    test('updateProfile returns the server validation message', () async {
      SocialService.client = MockClient((request) async {
        return http.Response(
          jsonEncode({
            'detail': [
              {'msg': 'Value error, bio must be at most 160 characters'},
            ],
          }),
          422,
        );
      });

      final result = await SocialService.updateProfile('Akshat', 'x');

      expect(result['success'], isFalse);
      expect(result['message'], 'bio must be at most 160 characters');
    });

    test('getMyCard asks for /users/me/card', () async {
      late http.Request seen;
      SocialService.client = MockClient((request) async {
        seen = request;
        return http.Response(jsonEncode({'id': 1, 'bio': null}), 200);
      });

      final result = await SocialService.getMyCard();

      expect(result['success'], isTrue);
      expect(seen.method, 'GET');
      expect(seen.url.path, '/users/me/card');
    });

    test('getRunDetail returns a RunDetail, or the 404 message', () async {
      RunService.client = MockClient((request) async {
        expect(request.url.path, '/runs/41');
        return http.Response(jsonEncode(_full()), 200);
      });
      final ok = await RunService.getRunDetail(41);
      expect(ok['success'], isTrue);
      expect((ok['data'] as RunDetail).runId, 41);

      RunService.client = MockClient((request) async {
        return http.Response(jsonEncode({'detail': 'Run not found'}), 404);
      });
      final missing = await RunService.getRunDetail(99);
      expect(missing['success'], isFalse);
      expect(missing['message'], 'Run not found');
    });
  });
}
