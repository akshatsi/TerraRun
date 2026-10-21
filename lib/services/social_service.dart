import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_service.dart';
import '../config.dart';

/// Following, search, profiles and the friends feed.
///
/// Every call returns `{'success': true, 'data': ...}` or
/// `{'success': false, 'message': ...}`, like the other services.
class SocialService {
  /// Replaces the HTTP client; tests set this.
  static http.Client? client;

  static Future<Map<String, dynamic>> search(String query, {int limit = 20}) {
    return _send(
      'GET',
      '/users/search',
      query: {'q': query.trim(), 'limit': '$limit'},
      fallback: 'Search failed',
    );
  }

  static Future<Map<String, dynamic>> getUser(int id) {
    return _send('GET', '/users/$id', fallback: 'Failed to load runner');
  }

  static Future<Map<String, dynamic>> follow(int id) {
    return _send('POST', '/users/$id/follow', fallback: 'Could not follow');
  }

  static Future<Map<String, dynamic>> unfollow(int id) {
    return _send('DELETE', '/users/$id/follow', fallback: 'Could not unfollow');
  }

  static Future<Map<String, dynamic>> following() {
    return _send('GET', '/me/following', fallback: 'Failed to load following');
  }

  static Future<Map<String, dynamic>> followers() {
    return _send('GET', '/me/followers', fallback: 'Failed to load followers');
  }

  static Future<Map<String, dynamic>> feed({int limit = 20, int? beforeId}) {
    return _send(
      'GET',
      '/feed',
      query: {
        'limit': '$limit',
        if (beforeId != null) 'before_id': '$beforeId',
      },
      fallback: 'Failed to load activity',
    );
  }

  /// Your own card (with bio and follower counts) for the profile screen.
  static Future<Map<String, dynamic>> getMyCard() {
    return _send('GET', '/users/me/card', fallback: 'Failed to load profile');
  }

  /// The JSON body of [updateProfile].
  static Map<String, dynamic> profileBody(String name, String bio) {
    return {'name': name.trim(), 'bio': bio.trim()};
  }

  /// Saves your name and bio. On success, also stores the new name so the
  /// rest of the app shows it.
  static Future<Map<String, dynamic>> updateProfile(
    String name,
    String bio,
  ) async {
    final result = await _send(
      'PATCH',
      '/users/me',
      body: profileBody(name, bio),
      fallback: 'Could not save profile',
    );
    final data = result['data'];
    if (result['success'] == true && data is Map && data['name'] is String) {
      await AuthService.saveUserName(data['name'] as String);
    }
    return result;
  }

  /// The text of a server error: a plain `detail`, or the messages of a
  /// validation list.
  static String? errorMessage(dynamic data) {
    if (data is! Map || data['detail'] == null) return null;
    final detail = data['detail'];
    if (detail is List) {
      final messages = detail
          .map((e) => e is Map ? e['msg']?.toString() : e?.toString())
          .whereType<String>()
          .map((m) => m.replaceFirst('Value error, ', ''))
          .toList();
      return messages.isEmpty ? null : messages.join('\n');
    }
    return detail.toString();
  }

  /// The request for one call, without sending it.
  static http.Request buildRequest(
    String method,
    String path, {
    Map<String, String>? query,
    String? token,
    Map<String, dynamic>? body,
  }) {
    final uri = Uri.parse(
      '${Config.baseUrl}$path',
    ).replace(queryParameters: query == null || query.isEmpty ? null : query);
    final request = http.Request(method, uri);
    request.headers['Accept'] = 'application/json';
    if (token != null && token.isNotEmpty) {
      request.headers['Authorization'] = 'Bearer $token';
    }
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    return request;
  }

  static Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, String>? query,
    Map<String, dynamic>? body,
    required String fallback,
  }) async {
    final http.Client c = client ?? http.Client();
    try {
      final token = await AuthService.getToken();
      final request = buildRequest(
        method,
        path,
        query: query,
        token: token,
        body: body,
      );
      final response = await http.Response.fromStream(await c.send(request));

      dynamic data;
      try {
        data = response.body.isNotEmpty ? jsonDecode(response.body) : null;
      } catch (_) {
        data = null;
      }

      if (response.statusCode >= 200 && response.statusCode < 300) {
        return {'success': true, 'data': data};
      }

      return {'success': false, 'message': errorMessage(data) ?? fallback};
    } catch (e) {
      return {'success': false, 'message': '$fallback: $e'};
    } finally {
      if (client == null) c.close();
    }
  }
}
