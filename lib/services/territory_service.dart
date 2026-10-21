import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_service.dart';
import '../config.dart';

class TerritoryService {
  /// Map scopes in the order the map's switch shows them.
  static const scopes = ['all', 'friends', 'mine'];

  static Uri uriFor(String scope) {
    final valid = scopes.contains(scope) ? scope : 'all';
    return Uri.parse(
      '${Config.baseUrl}/territories',
    ).replace(queryParameters: {'scope': valid});
  }

  /// Fetch territories for rendering on the map: `all`, `friends` or `mine`.
  static Future<Map<String, dynamic>> getAllTerritories({
    String scope = 'all',
  }) async {
    try {
      final token = await AuthService.getToken();

      final response = await http.get(
        uriFor(scope),
        headers: {
          'Accept': 'application/json',
          if (token != null && token.isNotEmpty)
            'Authorization': 'Bearer $token',
        },
      );

      final dynamic data = response.body.isNotEmpty
          ? jsonDecode(response.body)
          : {};

      if (response.statusCode == 200) {
        return {'success': true, 'data': data};
      }

      return {
        'success': false,
        'message': data is Map && data['detail'] != null
            ? data['detail'].toString()
            : 'Failed to fetch territories',
      };
    } catch (e) {
      return {'success': false, 'message': 'Territories error: $e'};
    }
  }

  /// Fetch the current user's territory.
  static Future<Map<String, dynamic>> getMyTerritory() async {
    try {
      final token = await AuthService.getToken();

      if (token == null || token.isEmpty) {
        return {
          'success': false,
          'message': 'No auth token found. Please log in again.',
        };
      }

      final response = await http.get(
        Uri.parse('${Config.baseUrl}/territories/me'),
        headers: {
          'Accept': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final dynamic data = response.body.isNotEmpty
          ? jsonDecode(response.body)
          : {};

      if (response.statusCode == 200) {
        return {'success': true, 'data': data};
      }

      return {
        'success': false,
        'message': data is Map && data['detail'] != null
            ? data['detail'].toString()
            : 'Failed to fetch territory',
      };
    } catch (e) {
      return {'success': false, 'message': 'Territory error: $e'};
    }
  }
}
