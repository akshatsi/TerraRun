import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_service.dart';
import '../config.dart';
import '../models/run_detail.dart';
import '../utils/format.dart';

class RunService {
  /// Uploads a run payload (see `buildRunPayload`). The result has `network:
  /// true` when the request never got an answer.
  static Future<Map<String, dynamic>> saveRun(
    Map<String, dynamic> payload,
  ) async {
    try {
      final token = await AuthService.getToken();

      if (token == null || token.isEmpty) {
        return {
          'success': false,
          'message': 'No auth token found. Please log in again.',
        };
      }

      final uri = Uri.parse('${Config.baseUrl}/runs');

      final response = await http
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json',
              'Authorization': 'Bearer $token',
            },
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 60));

      dynamic data = {};
      try {
        if (response.body.isNotEmpty) data = jsonDecode(response.body);
      } catch (_) {}

      if (response.statusCode == 200) {
        return {'success': true, 'message': 'Run saved', 'data': data};
      }

      return {
        'success': false,
        'message':
            (data is Map ? data['detail'] : null) ?? 'Failed to save run',
      };
    } catch (e) {
      return {
        'success': false,
        'network': true,
        'message': 'Save run error: $e',
      };
    }
  }

  /// "Loop claimed · 3,240 m²" or "Route claimed · 840 m²" from the
  /// response's `territory` block. Null for kind "none", or when the server
  /// sent no `kind` (an older server).
  static String? territoryHeadline(dynamic data) {
    if (data is! Map || data['territory'] is! Map) return null;
    final territory = data['territory'] as Map;
    final label = switch (territory['kind']) {
      'loop' => 'Loop',
      'route' => 'Route',
      _ => null,
    };
    if (label == null) return null;

    final sqm = (territory['awarded_area_sq_m'] as num?)?.toDouble() ?? 0;
    final a = Fmt.area(sqm);
    final value = a.unit == 'M²'
        ? a.value.replaceAllMapped(RegExp(r'\B(?=(\d{3})+(?!\d))'), (_) => ',')
        : a.value;
    return '$label claimed · $value ${a.unit.toLowerCase()}';
  }

  /// One line on a saved run from the server's answer, such as
  /// "Saved 4.71 km · 1 GPS gap not counted". For a loop or route the first
  /// part is the territory headline instead. Null when the server sent no
  /// `processing` block (an older server).
  static String? saveSummary(dynamic data) {
    if (data is! Map || data['processing'] is! Map) return null;
    final processing = data['processing'] as Map;

    final km = (data['distance_km'] as num?)?.toDouble();
    final parts = <String>[
      territoryHeadline(data) ??
          (km == null ? 'Saved' : 'Saved ${km.toStringAsFixed(2)} km'),
    ];

    final gaps = (processing['gap_count'] as num?)?.toInt() ?? 0;
    if (gaps > 0) {
      parts.add('$gaps GPS gap${gaps == 1 ? '' : 's'} not counted');
    }

    switch (processing['quality']) {
      case 'poor':
        parts.add('poor GPS quality');
      case 'unverified':
        parts.add('route not verified');
    }
    return parts.join(' · ');
  }

  static Future<Map<String, dynamic>> getRuns() async {
    try {
      final token = await AuthService.getToken();

      if (token == null || token.isEmpty) {
        return {
          'success': false,
          'message': 'No auth token found. Please log in again.',
        };
      }

      final uri = Uri.parse('${Config.baseUrl}/runs');

      final response = await http.get(
        uri,
        headers: {
          'Accept': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final data = response.body.isNotEmpty ? jsonDecode(response.body) : [];

      if (response.statusCode == 200) {
        return {'success': true, 'runs': data};
      }

      return {
        'success': false,
        'message': data['detail'] ?? 'Failed to fetch runs',
      };
    } catch (e) {
      return {'success': false, 'message': 'Fetch runs error: $e'};
    }
  }

  /// One run in full, for any runner. On success `data` is a [RunDetail].
  static Future<Map<String, dynamic>> getRunDetail(int id) async {
    try {
      final token = await AuthService.getToken();
      if (token == null || token.isEmpty) {
        return {
          'success': false,
          'message': 'No auth token found. Please log in again.',
        };
      }

      final response = await (client ?? http.Client())
          .get(
            Uri.parse('${Config.baseUrl}/runs/$id'),
            headers: {
              'Accept': 'application/json',
              'Authorization': 'Bearer $token',
            },
          )
          .timeout(const Duration(seconds: 30));

      dynamic data;
      try {
        data = response.body.isNotEmpty ? jsonDecode(response.body) : null;
      } catch (_) {
        data = null;
      }

      if (response.statusCode == 200 && data is Map) {
        return {
          'success': true,
          'data': RunDetail.fromJson(Map<String, dynamic>.from(data)),
        };
      }
      return {
        'success': false,
        'message': data is Map && data['detail'] != null
            ? data['detail'].toString()
            : 'Failed to load run',
      };
    } catch (e) {
      return {'success': false, 'message': 'Load run error: $e'};
    }
  }

  /// Replaces the HTTP client; tests set this.
  static http.Client? client;
}
