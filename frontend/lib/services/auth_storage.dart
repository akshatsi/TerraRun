// -----------------------------------------------
// TerraRun – Secure Token Storage
// -----------------------------------------------
// Thin wrapper around flutter_secure_storage to
// persist JWT tokens on the device keychain.
// -----------------------------------------------

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthStorage {
  static const _accessKey  = 'access_token';
  static const _refreshKey = 'refresh_token';

  final FlutterSecureStorage _storage;

  AuthStorage({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _accessKey, value: accessToken);
    await _storage.write(key: _refreshKey, value: refreshToken);
  }

  Future<String?> getAccessToken() => _storage.read(key: _accessKey);

  Future<String?> getRefreshToken() => _storage.read(key: _refreshKey);

  Future<void> clear() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }

  Future<bool> hasToken() async {
    final token = await _storage.read(key: _accessKey);
    return token != null && token.isNotEmpty;
  }
}
