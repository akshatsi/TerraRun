// -----------------------------------------------
// TerraRun – Providers: User Profile
// -----------------------------------------------
// FIX: Added autoDispose and auth guard.
// -----------------------------------------------

import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/user.dart';
import 'auth_provider.dart';

final userProvider = FutureProvider.autoDispose<UserModel>((ref) async {
  // Don't fetch if not authenticated
  final authState = ref.watch(authProvider);
  if (authState.status != AuthStatus.authenticated) {
    throw Exception('Not authenticated');
  }

  final api = ref.watch(apiServiceProvider);
  return api.getMe();
});
