import 'package:flutter/foundation.dart';
import '../models/route_suggestion.dart';

/// The route the runner chose on the Map tab. The Map and Run tabs both read
/// it from here.
class PlannedRouteStore {
  PlannedRouteStore._();

  static final ValueNotifier<RouteSuggestion?> current = ValueNotifier(null);

  /// Counts requests to open the Run tab; the navigation shell listens.
  static final ValueNotifier<int> runTabRequests = ValueNotifier(0);

  static bool get hasRoute => current.value != null;

  static void set(RouteSuggestion route) => current.value = route;

  static void clear() => current.value = null;

  static void requestRunTab() => runTabRequests.value++;

  /// "Following: Most from friends · 2.3 km", or null with no route.
  static String? get followingText {
    final route = current.value;
    if (route == null) return null;
    return 'Following: ${route.label} · ${route.distanceKm.toStringAsFixed(1)} km';
  }
}
