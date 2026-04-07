// -----------------------------------------------
// TerraRun – Core Constants
// -----------------------------------------------
// Centralised configuration values used throughout
// the app: API base URL, colour palette, map defaults.
// -----------------------------------------------

import 'dart:io' show Platform;
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

// ── API ──────────────────────────────────────────
// Selects the correct base URL based on the platform:
//   • Web            → localhost (same machine)
//   • Android emu    → 10.0.2.2 (special alias for host)
//   • iOS sim / rest → localhost
String get kApiBaseUrl {
  if (kIsWeb) return 'http://localhost:8000';

  if (Platform.isAndroid) {
    return 'http://10.0.2.2:8000';
  }

  // iOS simulator, macOS, Linux, Windows — all reach
  // the host machine via localhost.
  return 'http://localhost:8000';
}

// ── Map defaults ─────────────────────────────────
// Centred on Jaipur, India
final LatLng kDefaultMapCenter = LatLng(26.9124, 75.7873);
const double kDefaultMapZoom = 13.0;

// CartoDB Dark Matter tiles for the dark‑themed map
// NOTE: flutter_map v7 removed the `subdomains` parameter,
// so we use a fixed subdomain ('a') instead of the {s} placeholder.
const String kTileUrlTemplate =
    'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png';

// ── Colour palette ───────────────────────────────
class AppColors {
  AppColors._();

  // Background / surface
  static const Color scaffoldBg    = Color(0xFF0D0F14);
  static const Color cardBg        = Color(0xFF161B22);
  static const Color cardBorder    = Color(0xFF2A3140);
  static const Color surfaceLight  = Color(0xFF1C2230);

  // Brand accent — vibrant teal/green
  static const Color primary       = Color(0xFF1D9E75);
  static const Color primaryLight  = Color(0xFF2EEAA3);
  static const Color primaryDark   = Color(0xFF137A58);

  // Secondary accent — electric blue
  static const Color accent        = Color(0xFF3B82F6);
  static const Color accentLight   = Color(0xFF60A5FA);

  // Text
  static const Color textPrimary   = Color(0xFFE6EDF3);
  static const Color textSecondary = Color(0xFF8893A4);
  static const Color textMuted     = Color(0xFF545D6E);

  // Territory colours
  static const Color ownTerritory   = Color(0xFF1D9E75);
  static const Color otherTerritory = Color(0x559E9E9E);

  // Medals
  static const Color gold   = Color(0xFFFFD700);
  static const Color silver = Color(0xFFC0C0C0);
  static const Color bronze = Color(0xFFCD7F32);

  // Status
  static const Color error   = Color(0xFFEF4444);
  static const Color success = Color(0xFF22C55E);
  static const Color warning = Color(0xFFF59E0B);
}

// ── Spacing / Radius ─────────────────────────────
const double kPadding     = 16.0;
const double kCardRadius  = 16.0;
const double kButtonRadius = 12.0;
