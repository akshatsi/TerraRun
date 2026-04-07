// -----------------------------------------------
// TerraRun – Providers: Runs
// -----------------------------------------------
// FIX: Guarded with autoDispose so it doesn't
// hold stale data, and checks auth status before
// fetching to avoid 401 loops.
// -----------------------------------------------

import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/run.dart';
import 'auth_provider.dart';

final runsProvider = FutureProvider.autoDispose<List<RunModel>>((ref) async {
  // Don't fetch if not authenticated — avoids 401 loops
  final authState = ref.watch(authProvider);
  if (authState.status != AuthStatus.authenticated) {
    return [];
  }

  final api = ref.watch(apiServiceProvider);
  return api.getRuns();
});
