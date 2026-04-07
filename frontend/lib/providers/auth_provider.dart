// -----------------------------------------------
// TerraRun – Providers: Auth
// -----------------------------------------------
// Manages authentication state across the app.
// Exposes login / register / logout actions and
// an [AuthState] that the router listens to.
//
// FIX: AuthNotifier now extends ChangeNotifier so
// GoRouter's refreshListenable can listen for
// auth changes without recreating the router.
//
// FIX: ApiService.onUnauthorised is wired up to
// trigger logout when a 401 is received.
// -----------------------------------------------

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import '../services/auth_storage.dart';

// ── Singletons ───────────────────────────────────

final authStorageProvider = Provider<AuthStorage>((_) => AuthStorage());

final apiServiceProvider = Provider<ApiService>((ref) {
  final storage = ref.watch(authStorageProvider);
  return ApiService(authStorage: storage);
});

// ── Auth State ───────────────────────────────────

enum AuthStatus { unknown, authenticated, unauthenticated }

class AuthState {
  final AuthStatus status;
  final bool isLoading;
  final String? error;

  const AuthState({
    this.status = AuthStatus.unknown,
    this.isLoading = false,
    this.error,
  });

  AuthState copyWith({AuthStatus? status, bool? isLoading, String? error}) {
    return AuthState(
      status: status ?? this.status,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

// ── Notifier ─────────────────────────────────────
// StateNotifier handles Riverpod state; a separate
// ChangeNotifier (AuthRefreshNotifier) is used for
// GoRouter's refreshListenable to avoid the
// addListener signature conflict.

class AuthNotifier extends StateNotifier<AuthState> {
  final ApiService _api;
  final AuthStorage _storage;

  /// External listener called on every auth state change
  /// (used by AuthRefreshNotifier → GoRouter).
  VoidCallback? onAuthChange;

  AuthNotifier(this._api, this._storage) : super(const AuthState()) {
    // Wire up the 401 handler so expired tokens auto-logout
    _api.onUnauthorised = _onUnauthorised;
    _init();
  }

  void _notify() {
    onAuthChange?.call();
  }

  /// Called by ApiService when a 401 response is received.
  void _onUnauthorised() {
    state = state.copyWith(status: AuthStatus.unauthenticated);
    _notify();
  }

  /// Check for existing token on app launch.
  Future<void> _init() async {
    final hasToken = await _storage.hasToken();
    if (hasToken) {
      // Verify the token is still valid
      try {
        await _api.getMe();
        state = state.copyWith(status: AuthStatus.authenticated);
      } catch (_) {
        await _storage.clear();
        state = state.copyWith(status: AuthStatus.unauthenticated);
      }
    } else {
      state = state.copyWith(status: AuthStatus.unauthenticated);
    }
    _notify();
  }

  Future<void> login({required String email, required String password}) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      await _api.login(email: email, password: password);
      state = state.copyWith(
        status: AuthStatus.authenticated,
        isLoading: false,
      );
      _notify();
    } on DioException catch (e) {
      final msg = _extractError(e);
      state = state.copyWith(isLoading: false, error: msg);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> register({
    required String email,
    required String username,
    required String password,
  }) async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      await _api.register(
        email: email,
        username: username,
        password: password,
      );
      state = state.copyWith(
        status: AuthStatus.authenticated,
        isLoading: false,
      );
      _notify();
    } on DioException catch (e) {
      final msg = _extractError(e);
      state = state.copyWith(isLoading: false, error: msg);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> logout() async {
    await _api.logout();
    state = state.copyWith(status: AuthStatus.unauthenticated);
    _notify();
  }

  String _extractError(DioException e) {
    final data = e.response?.data;
    if (data is Map<String, dynamic> && data.containsKey('detail')) {
      return data['detail'] as String;
    }
    return e.message ?? 'Something went wrong';
  }

  @override
  void dispose() {
    _api.onUnauthorised = null;
    super.dispose();
  }
}

// ── Refresh notifier for GoRouter ────────────────
// A standalone ChangeNotifier that GoRouter uses as
// its refreshListenable. It listens for auth changes
// via AuthNotifier.onAuthChange.

class AuthRefreshNotifier extends ChangeNotifier {
  AuthRefreshNotifier(AuthNotifier authNotifier) {
    authNotifier.onAuthChange = notifyListeners;
  }
}

// ── Providers ────────────────────────────────────

final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final api = ref.watch(apiServiceProvider);
  final storage = ref.watch(authStorageProvider);
  return AuthNotifier(api, storage);
});

// Use this with GoRouter's `refreshListenable`.
final authRefreshProvider = ChangeNotifierProvider<AuthRefreshNotifier>((ref) {
  final notifier = ref.watch(authProvider.notifier);
  return AuthRefreshNotifier(notifier);
});
