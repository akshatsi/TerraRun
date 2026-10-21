import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../config.dart';

class AuthService {
  static const _tokenKey = 'auth_token';
  static const _userNameKey = 'user_name';
  static const _userEmailKey = 'user_email';

  static Future<Map<String, dynamic>> login({
    required String email,
    required String password,
  }) async {
    final response = await http.post(
      Uri.parse('${Config.baseUrl}/auth/login'),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({'email': email.trim(), 'password': password}),
    );

    final dynamic data = response.body.isNotEmpty
        ? jsonDecode(response.body)
        : {};

    if (response.statusCode != 200) {
      throw Exception(
        data is Map && data['detail'] != null ? data['detail'] : 'Login failed',
      );
    }

    await saveSession(
      token: data['access_token'],
      userName: data['user_name'],
      userEmail: data['user_email'],
    );

    return Map<String, dynamic>.from(data);
  }

  static Future<Map<String, dynamic>> signup({
    required String name,
    required String email,
    required String password,
  }) async {
    final response = await http.post(
      Uri.parse('${Config.baseUrl}/auth/signup'),
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode({
        'name': name.trim(),
        'email': email.trim(),
        'password': password,
      }),
    );

    final dynamic data = response.body.isNotEmpty
        ? jsonDecode(response.body)
        : {};

    if (response.statusCode != 200) {
      throw Exception(
        data is Map && data['detail'] != null
            ? data['detail']
            : 'Signup failed',
      );
    }

    await saveSession(
      token: data['access_token'],
      userName: data['user_name'],
      userEmail: data['user_email'],
    );

    return Map<String, dynamic>.from(data);
  }

  static Future<void> saveSession({
    required String token,
    required String userName,
    required String userEmail,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
    await prefs.setString(_userNameKey, userName);
    await prefs.setString(_userEmailKey, userEmail);
  }

  /// Stores a new display name after the user edits their profile.
  static Future<void> saveUserName(String name) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_userNameKey, name);
  }

  static Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }

  /// The signed-in user's id. Login returns none, but the token's `sub`
  /// claim holds it, so read it from there (no verification needed here).
  static Future<int?> getUserId() async {
    final token = await getToken();
    return userIdFromToken(token);
  }

  static int? userIdFromToken(String? token) {
    if (token == null) return null;
    final parts = token.split('.');
    if (parts.length != 3) return null;
    try {
      final payload = jsonDecode(
        utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))),
      );
      return int.tryParse('${payload['sub']}');
    } catch (_) {
      return null;
    }
  }

  static Future<String?> getUserName() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_userNameKey);
  }

  static Future<String?> getUserEmail() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_userEmailKey);
  }

  static Future<bool> isLoggedIn() async {
    final token = await getToken();
    return token != null && token.isNotEmpty;
  }

  static Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    await prefs.remove(_userNameKey);
    await prefs.remove(_userEmailKey);
  }
}
