import 'dart:convert';

import 'package:fitness_game_app/services/auth_service.dart';
import 'package:fitness_game_app/services/leaderboard_service.dart';
import 'package:fitness_game_app/services/social_service.dart';
import 'package:fitness_game_app/services/territory_service.dart';
import 'package:fitness_game_app/utils/format.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

String _fakeToken(int id) {
  String part(Map<String, dynamic> m) =>
      base64Url.encode(utf8.encode(jsonEncode(m))).replaceAll('=', '');
  return '${part({'alg': 'HS256'})}.${part({'sub': '$id'})}.sig';
}

void main() {
  late List<http.Request> seen;

  setUp(() {
    SharedPreferences.setMockInitialValues({'auth_token': 'tok'});
    seen = [];
  });

  tearDown(() => SocialService.client = null);

  void reply(int status, Object body) {
    SocialService.client = MockClient((request) async {
      seen.add(request);
      return http.Response(jsonEncode(body), status);
    });
  }

  group('SocialService', () {
    test('search sends query, limit and the token', () async {
      reply(200, [
        {'id': 7, 'name': 'Meera Kapoor', 'is_following': false},
      ]);

      final result = await SocialService.search(' ak ');

      expect(result['success'], isTrue);
      expect((result['data'] as List).single['name'], 'Meera Kapoor');
      expect(seen.single.method, 'GET');
      expect(seen.single.url.path, '/users/search');
      expect(seen.single.url.queryParameters, {'q': 'ak', 'limit': '20'});
      expect(seen.single.headers['Authorization'], 'Bearer tok');
    });

    test('follow and unfollow use POST and DELETE', () async {
      reply(200, {'id': 7, 'is_following': true});
      await SocialService.follow(7);
      await SocialService.unfollow(7);

      expect(seen.map((r) => r.method), ['POST', 'DELETE']);
      expect(seen.every((r) => r.url.path == '/users/7/follow'), isTrue);
    });

    test('lists and feed hit the right paths', () async {
      reply(200, []);
      await SocialService.following();
      await SocialService.followers();
      await SocialService.feed(limit: 5, beforeId: 41);

      expect(seen[0].url.path, '/me/following');
      expect(seen[1].url.path, '/me/followers');
      expect(seen[2].url.path, '/feed');
      expect(seen[2].url.queryParameters, {'limit': '5', 'before_id': '41'});
    });

    test('feed omits before_id when not given', () async {
      reply(200, []);
      await SocialService.feed();
      expect(seen.single.url.queryParameters, {'limit': '20'});
    });

    test('getUser returns the card with recent runs', () async {
      reply(200, {
        'id': 7,
        'name': 'Meera',
        'recent_runs': [
          {'run_id': 41},
        ],
      });
      final result = await SocialService.getUser(7);
      expect(result['data']['recent_runs'], hasLength(1));
      expect(seen.single.url.path, '/users/7');
    });

    test('errors return the server message', () async {
      reply(404, {'detail': 'User not found'});
      final result = await SocialService.follow(99);
      expect(result, {'success': false, 'message': 'User not found'});
    });

    test('errors without detail use the fallback', () async {
      reply(500, 'oops');
      final result = await SocialService.search('ab');
      expect(result['success'], isFalse);
      expect(result['message'], 'Search failed');
    });

    test('network failure becomes a failed result', () async {
      SocialService.client = MockClient((_) async => throw Exception('down'));
      final result = await SocialService.following();
      expect(result['success'], isFalse);
      expect(result['message'], contains('down'));
    });
  });

  group('scope query strings', () {
    test('territories', () {
      expect(TerritoryService.uriFor('friends').queryParameters, {
        'scope': 'friends',
      });
      expect(TerritoryService.uriFor('mine').queryParameters['scope'], 'mine');
      expect(TerritoryService.uriFor('bogus').queryParameters['scope'], 'all');
      expect(TerritoryService.scopes, ['all', 'friends', 'mine']);
    });

    test('leaderboard', () {
      expect(
        LeaderboardService.uriFor(
          scope: 'friends',
          period: 'week',
        ).queryParameters,
        {'scope': 'friends', 'period': 'week'},
      );
      expect(LeaderboardService.uriFor().queryParameters, {
        'scope': 'all',
        'period': 'all',
      });
      expect(
        LeaderboardService.uriFor(scope: 'x', period: 'y').queryParameters,
        {'scope': 'all', 'period': 'all'},
      );
    });
  });

  group('Fmt.timeAgo', () {
    final now = DateTime.utc(2026, 10, 21, 12);

    test('buckets', () {
      expect(
        Fmt.timeAgo(now.subtract(const Duration(seconds: 20)), now: now),
        'just now',
      );
      expect(
        Fmt.timeAgo(now.subtract(const Duration(minutes: 5)), now: now),
        '5m ago',
      );
      expect(
        Fmt.timeAgo(
          now.subtract(const Duration(hours: 2, minutes: 30)),
          now: now,
        ),
        '2h ago',
      );
      expect(
        Fmt.timeAgo(now.subtract(const Duration(days: 3)), now: now),
        '3d ago',
      );
      expect(
        Fmt.timeAgo(now.subtract(const Duration(days: 30)), now: now),
        '2026-09-21',
      );
    });

    test('parses ISO strings and tolerates junk', () {
      expect(Fmt.timeAgoFrom('2026-10-21T10:00:00Z', now: now), '2h ago');
      expect(Fmt.timeAgoFrom('nope'), '');
      expect(Fmt.timeAgoFrom(null), '');
    });
  });

  group('Fmt.runSummary', () {
    test('loop with area', () {
      expect(
        Fmt.runSummary({
          'distance_km': 4.71,
          'territory_kind': 'loop',
          'awarded_area_sq_m': 3240.0,
        }),
        '4.71 km · Loop +3,240 m²',
      );
    });

    test('no area awarded', () {
      expect(
        Fmt.runSummary({'distance_km': 2, 'awarded_area_sq_m': 0}),
        '2.00 km',
      );
    });

    test('large area reads in km²', () {
      expect(
        Fmt.runSummary({
          'distance_km': 10,
          'territory_kind': 'loop',
          'awarded_area_sq_m': 530000,
        }),
        '10.00 km · Loop +0.53 km²',
      );
    });
  });

  test('user id comes from the token subject', () {
    expect(AuthService.userIdFromToken(_fakeToken(12)), 12);
    expect(AuthService.userIdFromToken('garbage'), isNull);
    expect(AuthService.userIdFromToken(null), isNull);
  });
}
