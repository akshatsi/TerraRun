// -----------------------------------------------
// TerraRun – API Service
// -----------------------------------------------
// Centralised Dio HTTP client with:
//  • Bearer‑token auth interceptor
//  • 401 auto‑redirect to login
//  • Typed methods for every backend endpoint
// -----------------------------------------------

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import '../core/constants.dart';
import '../models/user.dart';
import '../models/run.dart';
import '../models/territory.dart';
import '../models/leaderboard.dart';
import 'auth_storage.dart';

class ApiService {
  late final Dio _dio;
  final AuthStorage _authStorage;

  /// Callback the router can set so the service can
  /// trigger a redirect to login on 401.
  VoidCallback? onUnauthorised;

  ApiService({AuthStorage? authStorage})
      : _authStorage = authStorage ?? AuthStorage() {
    _dio = Dio(
      BaseOptions(
        baseUrl: kApiBaseUrl,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 10),
        headers: {'Content-Type': 'application/json'},
      ),
    );

    // ── Auth Interceptor ──────────────────────────
    // Attaches "Authorization: Bearer <token>" to every
    // outgoing request. On a 401 response it clears stored
    // tokens and invokes the redirect callback.
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _authStorage.getAccessToken();
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) async {
          if (error.response?.statusCode == 401) {
            // Token expired or invalid – clear and redirect
            await _authStorage.clear();
            onUnauthorised?.call();
          }
          handler.next(error);
        },
      ),
    );
  }

  // ── Auth ──────────────────────────────────────────

  /// Register a new account. Returns { access_token, refresh_token }.
  Future<Map<String, String>> register({
    required String email,
    required String username,
    required String password,
  }) async {
    final res = await _dio.post('/auth/register', data: {
      'email': email,
      'username': username,
      'password': password,
    });
    final tokens = _extractTokens(res.data);
    await _authStorage.saveTokens(
      accessToken: tokens['access_token']!,
      refreshToken: tokens['refresh_token']!,
    );
    return tokens;
  }

  /// Login with email + password.
  Future<Map<String, String>> login({
    required String email,
    required String password,
  }) async {
    final res = await _dio.post('/auth/login', data: {
      'email': email,
      'password': password,
    });
    final tokens = _extractTokens(res.data);
    await _authStorage.saveTokens(
      accessToken: tokens['access_token']!,
      refreshToken: tokens['refresh_token']!,
    );
    return tokens;
  }

  /// Fetch the current user's profile.
  Future<UserModel> getMe() async {
    final res = await _dio.get('/auth/me');
    return UserModel.fromJson(res.data as Map<String, dynamic>);
  }

  /// Clear stored tokens (logout).
  Future<void> logout() async {
    await _authStorage.clear();
  }

  // ── Runs ──────────────────────────────────────────

  /// Submit a completed run with GPS track.
  Future<RunModel> submitRun({
    required List<GpsPoint> gpsPoints,
    required DateTime startedAt,
    required DateTime endedAt,
  }) async {
    final res = await _dio.post('/runs', data: {
      'started_at': startedAt.toUtc().toIso8601String(),
      'ended_at': endedAt.toUtc().toIso8601String(),
      'gps_points': gpsPoints.map((p) => p.toJson()).toList(),
    });
    return RunModel.fromJson(res.data as Map<String, dynamic>);
  }

  /// Fetch the user's run history.
  Future<List<RunModel>> getRuns({int limit = 20, int offset = 0}) async {
    final res = await _dio.get('/runs', queryParameters: {
      'limit': limit,
      'offset': offset,
    });
    final data = res.data as Map<String, dynamic>;
    final runs = (data['runs'] as List<dynamic>)
        .map((e) => RunModel.fromJson(e as Map<String, dynamic>))
        .toList();
    return runs;
  }

  // ── Territory ─────────────────────────────────────

  /// Get the current user's territory polygon.
  Future<TerritoryModel> getMyTerritory() async {
    final res = await _dio.get('/territory/me');
    return TerritoryModel.fromJson(res.data as Map<String, dynamic>);
  }

  /// Fetch all territories within a bounding box for map rendering.
  Future<List<TerritoryModel>> getTerritoryMap({
    required double minLat,
    required double minLng,
    required double maxLat,
    required double maxLng,
  }) async {
    final res = await _dio.get('/territory/map', queryParameters: {
      'min_lat': minLat,
      'min_lng': minLng,
      'max_lat': maxLat,
      'max_lng': maxLng,
    });
    final data = res.data as Map<String, dynamic>;
    return (data['territories'] as List<dynamic>)
        .map((e) => TerritoryModel.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ── Leaderboard ───────────────────────────────────

  /// Global leaderboard — top users by territory area.
  Future<List<LeaderboardEntry>> getLeaderboard({
    int limit = 50,
    int offset = 0,
  }) async {
    final res = await _dio.get('/leaderboard/global', queryParameters: {
      'limit': limit,
      'offset': offset,
    });
    final data = res.data as Map<String, dynamic>;
    return (data['entries'] as List<dynamic>)
        .map((e) => LeaderboardEntry.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ── Helpers ───────────────────────────────────────

  Map<String, String> _extractTokens(dynamic data) {
    final map = data as Map<String, dynamic>;
    return {
      'access_token': map['access_token'] as String,
      'refresh_token': map['refresh_token'] as String,
    };
  }
}
