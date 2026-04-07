// -----------------------------------------------
// TerraRun – Providers: Leaderboard
// -----------------------------------------------
// FIX: Guarded with autoDispose and auth check
// to prevent 401 loops on unauthenticated access.
// -----------------------------------------------

import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/leaderboard.dart';
import 'auth_provider.dart';

final leaderboardProvider =
    FutureProvider.autoDispose<List<LeaderboardEntry>>((ref) async {
  // Don't fetch if not authenticated — avoids 401 loops
  final authState = ref.watch(authProvider);
  if (authState.status != AuthStatus.authenticated) {
    return [];
  }

  final api = ref.watch(apiServiceProvider);
  return api.getLeaderboard();
});
