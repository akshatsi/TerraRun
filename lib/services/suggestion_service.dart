import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/route_suggestion.dart';
import 'auth_service.dart';
import 'social_service.dart';

/// Route suggestions from `GET /suggestions`.
///
/// Returns `{'success': true, 'data': SuggestionsResult}` or
/// `{'success': false, 'message': ...}`, like the other services.
class SuggestionService {
  /// Replaces the HTTP client; tests set this.
  static http.Client? client;

  static const unavailableMessage =
      'Road data is unavailable right now, try again later';
  static const networkMessage =
      'Could not reach the server. Check your connection and try again.';

  /// Query for one call. Pass at most one of [distanceKm] and [minutes];
  /// with neither, the server uses the runner's usual distance.
  static Map<String, String> query(
    double lat,
    double lng, {
    double? distanceKm,
    int? minutes,
  }) {
    return {
      'lat': '$lat',
      'lng': '$lng',
      if (distanceKm != null) 'distance_km': distanceKm.toStringAsFixed(2),
      if (distanceKm == null && minutes != null) 'minutes': '$minutes',
    };
  }

  /// The text to show for a failed response.
  static String errorFor(int status, dynamic data) {
    switch (status) {
      case 401:
        return 'Your session has ended. Please sign in again.';
      case 422:
        return SocialService.errorMessage(data) ??
            'Those route settings are not valid';
      case 503:
        return unavailableMessage;
    }
    return SocialService.errorMessage(data) ?? 'Could not load suggestions';
  }

  static Future<Map<String, dynamic>> getSuggestions(
    double lat,
    double lng, {
    double? distanceKm,
    int? minutes,
  }) async {
    final http.Client c = client ?? http.Client();
    try {
      final token = await AuthService.getToken();
      final request = SocialService.buildRequest(
        'GET',
        '/suggestions',
        query: query(lat, lng, distanceKm: distanceKm, minutes: minutes),
        token: token,
      );
      final response = await http.Response.fromStream(await c.send(request));

      dynamic data;
      try {
        data = response.body.isNotEmpty ? jsonDecode(response.body) : null;
      } catch (_) {
        data = null;
      }

      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (data is! Map) {
          return {'success': false, 'message': 'Could not load suggestions'};
        }
        return {
          'success': true,
          'data': SuggestionsResult.fromJson(Map<String, dynamic>.from(data)),
        };
      }

      return {'success': false, 'message': errorFor(response.statusCode, data)};
    } catch (_) {
      return {'success': false, 'message': networkMessage};
    } finally {
      if (client == null) c.close();
    }
  }
}
