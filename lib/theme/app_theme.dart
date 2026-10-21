import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

/// Colour tokens. See docs/design.md. Near-black and near-white, plus one
/// signature colour used sparingly for the things that matter most.
class AppColors {
  AppColors._();

  static const bg = Color(0xFF090B0D);
  static const surface = Color(0xFF121518);
  static const surfaceHigh = Color(0xFF1B1F24);
  static const line = Color(0xFF262B31);

  static const text = Color(0xFFF4F6FA);
  static const textSecondary = Color(0xFFA3ACBD);
  static const textMuted = Color(0xFF6B7589);

  /// Text and icons on a near-white fill.
  static const onLight = Color(0xFF090B0D);

  /// The signature colour (soft lime). Used only for your territory, the
  /// Run button, the start action and progress — never for plain text.
  static const signature = Color(0xFFC6F36A);
  static const onSignature = Color(0xFF090B0D);

  /// The primary action: a solid near-white button with near-black text.
  static const accent = text;

  static const positive = Color(0xFF4ADE80);
  static const warning = Color(0xFFFBBF24);
  static const negative = Color(0xFFF87171);

  /// Your territory and route on the map. Fill it at [mineFillOpacity].
  static const mine = signature;
  static const mineFillOpacity = 0.28;

  /// Other players' territory: muted solid hues.
  static const rivalPalette = [
    Color(0xFF60A5FA),
    Color(0xFFF59E0B),
    Color(0xFF34D399),
    Color(0xFFF472B6),
    Color(0xFFA78BFA),
    Color(0xFFF87171),
    Color(0xFF22D3EE),
  ];
}

/// Corner radii. Circles are only for avatars, the location dot and the
/// round map buttons.
class AppRadius {
  AppRadius._();

  static const card = 10.0;
  static const control = 8.0;
  static const chip = 6.0;
}

/// Type scale, set in Inter. Weights: 400 and 500 for most text, 600 only for
/// titles, the one big number on a card and buttons.
class AppText {
  AppText._();

  static TextStyle _s(
    double size,
    FontWeight weight, {
    Color color = AppColors.text,
    double height = 1.3,
    double letterSpacing = 0,
    List<FontFeature>? features,
  }) {
    return GoogleFonts.inter(
      fontSize: size,
      fontWeight: weight,
      color: color,
      height: height,
      letterSpacing: letterSpacing,
      fontFeatures: features,
    );
  }

  static TextStyle get display =>
      _s(32, FontWeight.w600, height: 1.12, letterSpacing: -0.5);
  static TextStyle get title => _s(20, FontWeight.w600);
  static TextStyle get headline => _s(17, FontWeight.w600);
  static TextStyle get body => _s(15, FontWeight.w400, height: 1.4);
  static TextStyle get bodySecondary =>
      _s(14, FontWeight.w400, color: AppColors.textSecondary, height: 1.4);
  static TextStyle get label =>
      _s(13, FontWeight.w500, color: AppColors.textSecondary);
  static TextStyle get caption =>
      _s(12, FontWeight.w400, color: AppColors.textMuted);
  static TextStyle get overline =>
      _s(11, FontWeight.w500, color: AppColors.textMuted, letterSpacing: 0.8);
  static TextStyle get button => _s(15, FontWeight.w600);

  /// Numbers, with tabular figures so columns and timers do not jitter.
  static TextStyle stat(
    double size, {
    Color color = AppColors.text,
    FontWeight weight = FontWeight.w500,
  }) {
    return _s(
      size,
      weight,
      color: color,
      height: 1.0,
      features: const [FontFeature.tabularFigures()],
    );
  }

  /// Unit after a number ("km", "/km", "m²").
  static TextStyle unit(double size) =>
      _s(size, FontWeight.w400, color: AppColors.textSecondary, height: 1.0);

  static TextStyle wordmark(double size) =>
      _s(size, FontWeight.w500, height: 1.0, letterSpacing: size * 0.38);
}

class AppTheme {
  AppTheme._();

  static ThemeData dark() {
    final base = ThemeData.dark(useMaterial3: true);

    return base.copyWith(
      scaffoldBackgroundColor: AppColors.bg,
      colorScheme: const ColorScheme.dark(
        primary: AppColors.text,
        onPrimary: AppColors.onLight,
        secondary: AppColors.textSecondary,
        surface: AppColors.surface,
        onSurface: AppColors.text,
        error: AppColors.negative,
      ),
      textTheme: GoogleFonts.interTextTheme(
        base.textTheme,
      ).apply(bodyColor: AppColors.text, displayColor: AppColors.text),
      dividerColor: AppColors.line,
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.text,
      ),
    );
  }
}

/// The shadcn_ui theme. It carries the same tokens as [AppTheme.dark]: a
/// near-black page, 1 px line borders, no fills, no shadows, Inter at light
/// weights and tight corners.
class AppShadTheme {
  AppShadTheme._();

  static const colorScheme = ShadColorScheme(
    background: AppColors.bg,
    foreground: AppColors.text,
    card: AppColors.bg,
    cardForeground: AppColors.text,
    popover: AppColors.surface,
    popoverForeground: AppColors.text,
    primary: AppColors.text,
    primaryForeground: AppColors.onLight,
    secondary: AppColors.surfaceHigh,
    secondaryForeground: AppColors.text,
    muted: AppColors.surface,
    mutedForeground: AppColors.textSecondary,
    accent: AppColors.surfaceHigh,
    accentForeground: AppColors.text,
    destructive: AppColors.negative,
    destructiveForeground: AppColors.onLight,
    border: AppColors.line,
    input: AppColors.line,
    ring: AppColors.line,
    selection: Color(0x55A3ACBD),
  );

  static ShadTextTheme _textTheme() {
    TextStyle s(double size, FontWeight weight, {double height = 1.3}) =>
        TextStyle(fontSize: size, fontWeight: weight, height: height);

    final base = ShadTextTheme(
      h1Large: s(32, FontWeight.w600, height: 1.12),
      h1: s(32, FontWeight.w600, height: 1.12),
      h2: s(20, FontWeight.w600),
      h3: s(17, FontWeight.w600),
      h4: s(17, FontWeight.w600),
      p: s(15, FontWeight.w400, height: 1.4),
      blockquote: s(15, FontWeight.w400, height: 1.4),
      table: s(15, FontWeight.w400, height: 1.4),
      list: s(15, FontWeight.w400, height: 1.4),
      lead: s(15, FontWeight.w400, height: 1.4),
      large: s(17, FontWeight.w600),
      small: s(13, FontWeight.w500),
      muted: s(14, FontWeight.w400, height: 1.4),
    );
    return ShadTextTheme.fromGoogleFont(GoogleFonts.inter, textTheme: base);
  }

  static ShadBorder _line(double radius, [Color color = AppColors.line]) {
    return ShadBorder.all(
      color: color,
      width: 1,
      radius: BorderRadius.circular(radius),
    );
  }

  static ShadThemeData dark() {
    const control = BorderRadius.all(Radius.circular(AppRadius.control));

    return ShadThemeData(
      brightness: Brightness.dark,
      colorScheme: colorScheme,
      radius: control,
      textTheme: _textTheme(),
      // No focus halo around controls; inputs show focus with their border.
      decoration: ShadDecoration(
        secondaryFocusedBorder: ShadBorder.all(width: 0),
        labelStyle: AppText.label,
        errorStyle: AppText.caption.copyWith(color: AppColors.negative),
        descriptionStyle: AppText.caption,
        labelPadding: const EdgeInsets.only(bottom: 8),
        errorPadding: const EdgeInsets.only(top: 6),
        descriptionPadding: const EdgeInsets.only(top: 6),
      ),
      primaryButtonTheme: ShadButtonTheme(
        hoverBackgroundColor: AppColors.text.withValues(alpha: 0.9),
        pressedBackgroundColor: AppColors.text.withValues(alpha: 0.8),
        shadows: const [],
      ),
      secondaryButtonTheme: const ShadButtonTheme(
        pressedBackgroundColor: AppColors.line,
        shadows: [],
      ),
      destructiveButtonTheme: ShadButtonTheme(
        hoverBackgroundColor: AppColors.negative.withValues(alpha: 0.9),
        pressedBackgroundColor: AppColors.negative.withValues(alpha: 0.8),
        shadows: const [],
      ),
      outlineButtonTheme: const ShadButtonTheme(
        foregroundColor: AppColors.text,
        hoverBackgroundColor: AppColors.surfaceHigh,
        pressedBackgroundColor: AppColors.surfaceHigh,
        shadows: [],
      ),
      ghostButtonTheme: const ShadButtonTheme(
        foregroundColor: AppColors.text,
        hoverBackgroundColor: AppColors.surfaceHigh,
        pressedBackgroundColor: AppColors.surfaceHigh,
        shadows: [],
      ),
      cardTheme: ShadCardTheme(
        backgroundColor: Colors.transparent,
        padding: const EdgeInsets.all(16),
        radius: BorderRadius.circular(AppRadius.card),
        border: _line(AppRadius.card),
        shadows: const [],
      ),
      inputTheme: ShadInputTheme(
        style: AppText.body,
        placeholderStyle: AppText.body.copyWith(color: AppColors.textMuted),
        cursorColor: AppColors.text,
        padding: const EdgeInsets.symmetric(horizontal: 14),
        inputPadding: const EdgeInsets.symmetric(vertical: 14),
        decoration: ShadDecoration(
          border: _line(AppRadius.control),
          focusedBorder: _line(AppRadius.control, AppColors.textSecondary),
          errorBorder: _line(AppRadius.control, AppColors.negative),
        ),
      ),
      tabsTheme: ShadTabsTheme(
        gap: 0,
        padding: const EdgeInsets.all(3),
        decoration: ShadDecoration(border: _line(AppRadius.control)),
        tabDecoration: ShadDecoration(
          border: ShadBorder.all(
            width: 0,
            radius: BorderRadius.circular(AppRadius.control - 3),
          ),
          secondaryBorder: ShadBorder.all(width: 0, padding: EdgeInsets.zero),
          secondaryFocusedBorder: ShadBorder.all(
            width: 0,
            padding: EdgeInsets.zero,
          ),
        ),
        tabPadding: const EdgeInsets.symmetric(horizontal: 8),
        tabBackgroundColor: Colors.transparent,
        tabHoverBackgroundColor: Colors.transparent,
        tabSelectedBackgroundColor: AppColors.surfaceHigh,
        tabSelectedHoverBackgroundColor: AppColors.surfaceHigh,
        tabForegroundColor: AppColors.textSecondary,
        tabSelectedForegroundColor: AppColors.text,
        tabShadows: const [],
        tabSelectedShadows: const [],
        // No colour here: each tab sets its own foreground.
        tabTextStyle: GoogleFonts.inter(
          fontSize: 13,
          fontWeight: FontWeight.w500,
          height: 1.3,
        ),
      ),
      secondaryBadgeTheme: ShadBadgeTheme(
        backgroundColor: AppColors.surfaceHigh,
        hoverBackgroundColor: AppColors.surfaceHigh,
        foregroundColor: AppColors.textSecondary,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.chip),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      ),
      primaryBadgeTheme: ShadBadgeTheme(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.chip),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      ),
      destructiveAlertTheme: ShadAlertTheme(
        iconColor: AppColors.negative,
        titleStyle: AppText.bodySecondary.copyWith(color: AppColors.negative),
        descriptionStyle: AppText.bodySecondary.copyWith(
          color: AppColors.negative,
        ),
        decoration: ShadDecoration(
          color: AppColors.negative.withValues(alpha: 0.1),
          border: ShadBorder.all(
            color: AppColors.negative.withValues(alpha: 0.35),
            width: 1,
            radius: BorderRadius.circular(AppRadius.card),
            padding: const EdgeInsets.all(14),
          ),
        ),
      ),
      avatarTheme: const ShadAvatarTheme(
        backgroundColor: AppColors.surfaceHigh,
      ),
      separatorTheme: const ShadSeparatorTheme(
        thickness: 1,
        color: AppColors.line,
        horizontalMargin: EdgeInsets.zero,
        verticalMargin: EdgeInsets.zero,
      ),
      progressTheme: const ShadProgressTheme(
        color: AppColors.signature,
        backgroundColor: AppColors.surfaceHigh,
      ),
      primaryToastTheme: ShadToastTheme(
        alignment: Alignment.bottomCenter,
        backgroundColor: AppColors.surfaceHigh,
        border: _line(AppRadius.control),
        radius: BorderRadius.circular(AppRadius.control),
        shadows: const [],
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        descriptionStyle: AppText.body,
        titleStyle: AppText.body,
        showCloseIconOnlyWhenHovered: true,
      ),
    );
  }
}
