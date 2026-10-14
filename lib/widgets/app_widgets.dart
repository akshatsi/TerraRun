import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Wide-tracked brand name.
class Wordmark extends StatelessWidget {
  final double size;

  const Wordmark({super.key, this.size = 14});

  @override
  Widget build(BuildContext context) {
    return Padding(
      // Balances the trailing letter-spacing so the word sits centred.
      padding: EdgeInsets.only(left: size * 0.38),
      child: Text('TERRARUN', style: AppText.wordmark(size)),
    );
  }
}

class AppLoader extends StatelessWidget {
  final double size;

  const AppLoader({super.key, this.size = 24});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: const CircularProgressIndicator(
        strokeWidth: 2.4,
        color: AppColors.pink,
      ),
    );
  }
}

class IconCircleButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;
  final double size;

  /// Near-opaque fill, for buttons that sit on top of a map.
  final bool solid;

  const IconCircleButton({
    super.key,
    required this.icon,
    this.onTap,
    this.size = 40,
    this.solid = false,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: solid
              ? AppColors.surface.withValues(alpha: 0.94)
              : AppColors.surface,
          shape: BoxShape.circle,
          border: Border.all(color: AppColors.border),
        ),
        child: Icon(icon, size: size * 0.45, color: Colors.white),
      ),
    );
  }
}

class ScreenHeader extends StatelessWidget {
  final String title;
  final Widget? leading;
  final Widget? trailing;

  const ScreenHeader({
    super.key,
    required this.title,
    this.leading,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 8),
      child: Row(
        children: [
          SizedBox(width: 40, height: 40, child: leading),
          Expanded(
            child: Center(child: Text(title, style: AppText.subtitle)),
          ),
          SizedBox(width: 40, height: 40, child: trailing),
        ],
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  final String text;
  final Widget? trailing;

  const SectionTitle(this.text, {super.key, this.trailing});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: Text(text, style: AppText.title)),
        ?trailing,
      ],
    );
  }
}

class AppCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;
  final Color? color;
  final Gradient? gradient;
  final Color? borderColor;
  final double radius;
  final VoidCallback? onTap;

  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.margin,
    this.color,
    this.gradient,
    this.borderColor,
    this.radius = 20,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final box = Container(
      margin: margin,
      decoration: BoxDecoration(
        color: gradient == null ? (color ?? AppColors.surface) : null,
        gradient: gradient,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: borderColor ?? AppColors.border),
      ),
      child: Padding(padding: padding, child: child),
    );

    if (onTap == null) return box;

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: box,
    );
  }
}

/// Pill-shaped switch between a few views. The active segment is light.
class SegmentedPill extends StatelessWidget {
  final List<String> labels;
  final int index;
  final ValueChanged<int> onChanged;

  const SegmentedPill({
    super.key,
    required this.labels,
    required this.index,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          for (int i = 0; i < labels.length; i++)
            Expanded(
              child: GestureDetector(
                onTap: () => onChanged(i),
                behavior: HitTestBehavior.opaque,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: i == index
                        ? const Color(0xFFE4E4E8)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    labels[i],
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.caption.copyWith(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: i == index ? Colors.black : Colors.white,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// A large value with a small unit, and a muted label underneath.
class StatBlock extends StatelessWidget {
  final String value;
  final String? unit;
  final String label;
  final bool accent;
  final double valueSize;
  final CrossAxisAlignment align;

  const StatBlock({
    super.key,
    required this.value,
    required this.label,
    this.unit,
    this.accent = false,
    this.valueSize = 22,
    this.align = CrossAxisAlignment.start,
  });

  @override
  Widget build(BuildContext context) {
    final color = accent ? AppColors.pink : AppColors.textPrimary;
    final textAlign = align == CrossAxisAlignment.center
        ? TextAlign.center
        : align == CrossAxisAlignment.end
            ? TextAlign.right
            : TextAlign.left;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: align,
      children: [
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: value,
                  style: AppText.stat(valueSize, color: color),
                ),
                if (unit != null)
                  TextSpan(
                    text: ' $unit',
                    style: AppText.stat(
                      valueSize * 0.5,
                      color: color,
                      weight: FontWeight.w700,
                    ),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text(label, style: AppText.caption, textAlign: textAlign),
      ],
    );
  }
}

class StatDivider extends StatelessWidget {
  const StatDivider({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1,
      height: 34,
      margin: const EdgeInsets.symmetric(horizontal: 12),
      color: AppColors.border,
    );
  }
}

class GradientButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool loading;
  final IconData? icon;
  final Gradient gradient;
  final double height;

  const GradientButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.loading = false,
    this.icon,
    this.gradient = AppColors.brandGradient,
    this.height = 56,
  });

  @override
  Widget build(BuildContext context) {
    final disabled = onPressed == null && !loading;
    final glow = (gradient as LinearGradient).colors.last;

    return Opacity(
      opacity: disabled ? 0.5 : 1,
      child: Container(
        decoration: BoxDecoration(
          gradient: gradient,
          borderRadius: BorderRadius.circular(999),
          boxShadow: [
            BoxShadow(
              color: glow.withValues(alpha: 0.32),
              blurRadius: 24,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(999),
            onTap: loading ? null : onPressed,
            child: SizedBox(
              height: height,
              width: double.infinity,
              child: Center(
                child: loading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.2,
                          color: Colors.white,
                        ),
                      )
                    : Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (icon != null) ...[
                            Icon(icon, color: Colors.white, size: 20),
                            const SizedBox(width: 8),
                          ],
                          Text(label, style: AppText.button),
                        ],
                      ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class HeadlineSpan {
  final String text;
  final bool emphasis;
  final bool italic;

  const HeadlineSpan(this.text, {this.emphasis = false, this.italic = false});
}

/// Headline in which chosen words are picked out in the brand colour.
class Headline extends StatelessWidget {
  final List<HeadlineSpan> spans;
  final TextStyle? style;
  final TextAlign align;

  const Headline(
    this.spans, {
    super.key,
    this.style,
    this.align = TextAlign.start,
  });

  @override
  Widget build(BuildContext context) {
    final base = style ?? AppText.headline;

    return Text.rich(
      TextSpan(
        style: base,
        children: [
          for (final s in spans)
            TextSpan(
              text: s.text,
              style: s.emphasis
                  ? base.copyWith(
                      color: AppColors.pink,
                      fontStyle: s.italic ? FontStyle.italic : FontStyle.normal,
                    )
                  : null,
            ),
        ],
      ),
      textAlign: align,
    );
  }
}

class GradientProgressBar extends StatelessWidget {
  final double value;
  final double height;

  const GradientProgressBar({super.key, required this.value, this.height = 8});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(height),
      child: Stack(
        children: [
          Container(height: height, color: Colors.white.withValues(alpha: 0.1)),
          FractionallySizedBox(
            widthFactor: value.clamp(0.0, 1.0),
            child: Container(
              height: height,
              decoration: const BoxDecoration(gradient: AppColors.brandGradient),
            ),
          ),
        ],
      ),
    );
  }
}

/// Purple-to-coral card with a faint street grid and a claimed-area shape.
class HeroCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;

  const HeroCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(20),
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(26),
      child: DecoratedBox(
        decoration: const BoxDecoration(gradient: AppColors.territoryGradient),
        child: Stack(
          children: [
            const Positioned.fill(child: TerritoryBackdrop()),
            Padding(
              padding: padding,
              child: SizedBox(width: double.infinity, child: child),
            ),
          ],
        ),
      ),
    );
  }
}

class TerritoryBackdrop extends StatelessWidget {
  const TerritoryBackdrop({super.key});

  @override
  Widget build(BuildContext context) {
    return const CustomPaint(painter: _TerritoryPainter());
  }
}

class _TerritoryPainter extends CustomPainter {
  const _TerritoryPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final grid = Paint()
      ..color = Colors.white.withValues(alpha: 0.08)
      ..strokeWidth = 1;

    for (double x = -size.height; x < size.width; x += 28) {
      canvas.drawLine(
        Offset(x, size.height),
        Offset(x + size.height, 0),
        grid,
      );
    }
    for (double x = 0; x < size.width + size.height; x += 36) {
      canvas.drawLine(Offset(x, 0), Offset(x - size.height, size.height), grid);
    }

    final w = size.width;
    final h = size.height;
    final shape = Path()
      ..moveTo(w * 0.58, h * 0.18)
      ..lineTo(w * 0.92, h * 0.10)
      ..lineTo(w * 0.97, h * 0.52)
      ..lineTo(w * 0.80, h * 0.62)
      ..lineTo(w * 0.84, h * 0.92)
      ..lineTo(w * 0.52, h * 0.80)
      ..lineTo(w * 0.44, h * 0.46)
      ..close();

    canvas.drawPath(
      shape,
      Paint()..color = Colors.white.withValues(alpha: 0.14),
    );
    canvas.drawPath(
      shape,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5
        ..color = Colors.white.withValues(alpha: 0.4),
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class AppTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  final String? Function(String?) validator;
  final bool obscure;
  final Widget? suffix;
  final TextInputType? keyboardType;

  const AppTextField({
    super.key,
    required this.controller,
    required this.label,
    required this.hint,
    required this.validator,
    this.obscure = false,
    this.suffix,
    this.keyboardType,
  });

  static OutlineInputBorder _border(Color color, [double width = 1]) {
    return OutlineInputBorder(
      borderRadius: BorderRadius.circular(18),
      borderSide: BorderSide(color: color, width: width),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: AppText.caption.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 8),
        TextFormField(
          controller: controller,
          obscureText: obscure,
          keyboardType: keyboardType,
          validator: validator,
          style: AppText.body,
          cursorColor: AppColors.pink,
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: AppText.body.copyWith(color: AppColors.textMuted),
            errorStyle: AppText.caption.copyWith(color: AppColors.danger),
            filled: true,
            fillColor: AppColors.surface,
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 18,
              vertical: 16,
            ),
            suffixIcon: suffix,
            enabledBorder: _border(AppColors.border),
            border: _border(AppColors.border),
            focusedBorder: _border(AppColors.pink, 1.4),
            errorBorder: _border(AppColors.danger),
            focusedErrorBorder: _border(AppColors.danger, 1.4),
          ),
        ),
      ],
    );
  }
}

class ErrorBanner extends StatelessWidget {
  final String text;

  const ErrorBanner(this.text, {super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.danger.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.danger.withValues(alpha: 0.3)),
      ),
      child: Text(
        text,
        style: AppText.bodySecondary.copyWith(
          color: const Color(0xFFFF9A9A),
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

/// Centred message for empty and error states.
class MessageView extends StatelessWidget {
  final String text;

  const MessageView(this.text, {super.key});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: Text(
          text,
          textAlign: TextAlign.center,
          style: AppText.bodySecondary,
        ),
      ),
    );
  }
}

class MenuTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final VoidCallback onTap;
  final bool danger;

  const MenuTile({
    super.key,
    required this.icon,
    required this.title,
    required this.onTap,
    this.danger = false,
  });

  @override
  Widget build(BuildContext context) {
    final tint = danger ? AppColors.danger : AppColors.pink;

    return AppCard(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      onTap: onTap,
      borderColor: danger ? AppColors.danger.withValues(alpha: 0.3) : null,
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: tint.withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: tint, size: 18),
          ),
          const SizedBox(width: 12),
          Expanded(child: Text(title, style: AppText.subtitle)),
          const Icon(
            Icons.chevron_right_rounded,
            color: AppColors.textMuted,
            size: 20,
          ),
        ],
      ),
    );
  }
}
