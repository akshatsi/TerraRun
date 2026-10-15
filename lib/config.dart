import 'package:flutter/foundation.dart';

class Config {
  /// Set at build time: `--dart-define=API_URL=https://api.example.com`.
  static const String _apiUrl = String.fromEnvironment('API_URL');

  static String get baseUrl {
    if (_apiUrl.isNotEmpty) {
      return _apiUrl.endsWith('/')
          ? _apiUrl.substring(0, _apiUrl.length - 1)
          : _apiUrl;
    }
    // Development fallbacks.
    if (kIsWeb) {
      return 'http://localhost:8000';
    }
    return 'http://172.22.195.160:8000';
  }
}
