import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Colour tokens. Near-black canvas, a coral-to-magenta brand pair and a
/// purple used for claimed territory.
class AppColors {
  AppColors._();

  static const bg = Color(0xFF0A0A0C);
  static const surface = Color(0xFF141417);
  static const surfaceHigh = Color(0xFF1D1D22);
  static const border = Color(0x14FFFFFF);
  static const borderStrong = Color(0x29FFFFFF);

  static const textPrimary = Color(0xFFFFFFFF);
  static const textSecondary = Color(0xFFA1A1AA);
  static const textMuted = Color(0xFF6E6E78);

  static const pink = Color(0xFFFF5C7A);
  static const magenta = Color(0xFFE0369F);
  static const purple = Color(0xFFB44FE0);
  static const deepPurple = Color(0xFF6B2FA0);

  static const success = Color(0xFF3DD68C);
  static const danger = Color(0xFFFF4D4D);

  static const gold = Color(0xFFF5C542);
  static const silver = Color(0xFFC4C8D0);
  static const bronze = Color(0xFFD98B55);

  static const brandGradient = LinearGradient(
    begin: Alignment.centerLeft,
    end: Alignment.centerRight,
    colors: [pink, magenta],
  );

  static const territoryGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF7B2FBE), Color(0xFFD13C9E), Color(0xFFFF6B81)],
  );

  static const dangerGradient = LinearGradient(
    begin: Alignment.centerLeft,
    end: Alignment.centerRight,
    colors: [Color(0xFFFF6B6B), Color(0xFFD93636)],
  );

  /// Dark, tinted row backgrounds used on the leaderboard.
  static const rowTints = [
    Color(0xFF3A1A1F),
    Color(0xFF331A26),
    Color(0xFF2E2A1A),
    Color(0xFF2A1830),
    Color(0xFF1B2433),
    Color(0xFF17302A),
  ];
}

/// Type scale, set in Plus Jakarta Sans.
class AppText {
  AppText._();

  static TextStyle _s(
    double size,
    FontWeight weight, {
    Color color = AppColors.textPrimary,
    double height = 1.25,
    double letterSpacing = 0,
    FontStyle fontStyle = FontStyle.normal,
  }) {
    return GoogleFonts.plusJakartaSans(
      fontSize: size,
      fontWeight: weight,
      color: color,
      height: height,
      letterSpacing: letterSpacing,
      fontStyle: fontStyle,
    );
  }

  static TextStyle get display =>
      _s(34, FontWeight.w800, height: 1.08, letterSpacing: -1);
  static TextStyle get headline =>
      _s(26, FontWeight.w800, height: 1.15, letterSpacing: -0.6);
  static TextStyle get title => _s(18, FontWeight.w700);
  static TextStyle get subtitle => _s(15, FontWeight.w700);
  static TextStyle get body => _s(14, FontWeight.w500, height: 1.4);
  static TextStyle get bodySecondary =>
      _s(13, FontWeight.w500, color: AppColors.textSecondary, height: 1.4);
  static TextStyle get caption =>
      _s(11, FontWeight.w600, color: AppColors.textSecondary);
  static TextStyle get overline => _s(
        10,
        FontWeight.w700,
        color: AppColors.textMuted,
        letterSpacing: 1.2,
      );
  static TextStyle get button =>
      _s(15, FontWeight.w700, letterSpacing: 0.2);

  static TextStyle stat(
    double size, {
    Color color = AppColors.textPrimary,
    FontWeight weight = FontWeight.w800,
  }) {
    return _s(size, weight, color: color, height: 1.0, letterSpacing: -0.5);
  }

  static TextStyle wordmark(double size) =>
      _s(size, FontWeight.w600, height: 1.0, letterSpacing: size * 0.38);
}

class AppTheme {
  AppTheme._();

  static ThemeData dark() {
    final base = ThemeData.dark(useMaterial3: true);

    return base.copyWith(
      scaffoldBackgroundColor: AppColors.bg,
      colorScheme: const ColorScheme.dark(
        primary: AppColors.pink,
        onPrimary: Colors.white,
        secondary: AppColors.purple,
        surface: AppColors.surface,
        onSurface: Colors.white,
        error: AppColors.danger,
      ),
      textTheme: GoogleFonts.plusJakartaSansTextTheme(base.textTheme).apply(
        bodyColor: AppColors.textPrimary,
        displayColor: AppColors.textPrimary,
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.pink,
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: AppColors.surfaceHigh,
        behavior: SnackBarBehavior.floating,
        contentTextStyle: AppText.body,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
      ),
    );
  }
}
