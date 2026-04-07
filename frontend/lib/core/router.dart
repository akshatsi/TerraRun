// -----------------------------------------------
// TerraRun – GoRouter Configuration
// -----------------------------------------------
// Declarative routing with auth‑aware redirects.
// Uses StatefulShellRoute for the bottom nav bar.
//
// FIX: The router is now created once and uses
// `refreshListenable` to react to auth changes
// instead of being recreated on every state change
// (which destroyed navigation state).
// -----------------------------------------------


import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/auth_provider.dart';
import '../screens/auth_screen.dart';
import '../screens/dashboard_screen.dart';
import '../screens/map_screen.dart';
import '../screens/run_screen.dart';
import '../screens/leaderboard_screen.dart';
import '../widgets/bottom_nav.dart';

final routerProvider = Provider<GoRouter>((ref) {
  // Create a ChangeNotifier that fires whenever auth state changes.
  // This tells GoRouter to re-evaluate its redirect without
  // recreating the entire router instance.
  final refreshNotifier = ref.watch(authRefreshProvider);

  return GoRouter(
    initialLocation: '/dashboard',
    debugLogDiagnostics: true,

    // The router re-evaluates redirects when this notifier fires,
    // but keeps the navigation stack intact.
    refreshListenable: refreshNotifier,

    // ── Auth redirect ──
    redirect: (context, state) {
      // Read the latest auth state at redirect time (not watch)
      final authState = ref.read(authProvider);
      final isAuthenticated = authState.status == AuthStatus.authenticated;
      final isAuthRoute = state.matchedLocation == '/login';

      // Still loading auth state — don't redirect yet
      if (authState.status == AuthStatus.unknown) return null;

      // Not authenticated and not on login → go to login
      if (!isAuthenticated && !isAuthRoute) return '/login';

      // Authenticated but on login → go to dashboard
      if (isAuthenticated && isAuthRoute) return '/dashboard';

      return null;
    },

    routes: [
      // ── Login route (no bottom nav) ──
      GoRoute(
        path: '/login',
        builder: (context, state) => const AuthScreen(),
      ),

      // ── Main app shell with bottom nav ──
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          return BottomNavShell(navigationShell: navigationShell);
        },
        branches: [
          // Dashboard tab
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/dashboard',
                builder: (context, state) => const DashboardScreen(),
              ),
            ],
          ),
          // Map tab
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/map',
                builder: (context, state) => const MapScreen(),
              ),
            ],
          ),
          // Run tab
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/run',
                builder: (context, state) => const RunScreen(),
              ),
            ],
          ),
          // Leaderboard tab
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/leaderboard',
                builder: (context, state) => const LeaderboardScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
});
