import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_service.dart';
import '../config.dart';

class LeaderboardService {
  static const scopes = ['all', 'friends'];
  static const periods = ['all', 'week'];

  static Uri uriFor({String scope = 'all', String period = 'all'}) {
    return Uri.parse('${Config.baseUrl}/leaderboard').replace(
      queryParameters: {
        'scope': scopes.contains(scope) ? scope : 'all',
        'period': periods.contains(period) ? period : 'all',
      },
    );
  }

  static Future<Map<String, dynamic>> getLeaderboard({
    String scope = 'all',
    String period = 'all',
  }) async {
    try {
      final token = await AuthService.getToken();

      final response = await http.get(
        uriFor(scope: scope, period: period),
        headers: {
          'Accept': 'application/json',
          if (token != null && token.isNotEmpty)
            'Authorization': 'Bearer $token',
        },
      );

      final dynamic data = response.body.isNotEmpty
          ? jsonDecode(response.body)
          : [];

      if (response.statusCode == 200) {
        return {'success': true, 'data': data};
      } else {
        return {
          'success': false,
          'message': data is Map && data['detail'] != null
              ? data['detail'].toString()
              : 'Failed to fetch leaderboard',
        };
      }
    } catch (e) {
      return {'success': false, 'message': e.toString()};
    }
  }
}
