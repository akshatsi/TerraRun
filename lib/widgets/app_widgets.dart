import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
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
        strokeWidth: 2,
        color: AppColors.text,
      ),
    );
  }
}

/// Shows a short message at the bottom of the screen.
void showAppToast(BuildContext context, String message) {
  ShadToaster.of(context).show(ShadToast(description: Text(message)));
}

/// Round button for use over a map. [active] fills it near-white.
class IconCircleButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;
  final double size;

  /// Shows a mode is on: near-white fill, near-black icon.
  final bool active;

  const IconCircleButton({
    super.key,
    required this.icon,
    this.onTap,
    this.size = 40,
    this.active = false,
  });

  @override
  Widget build(BuildContext context) {
    final fill = active ? AppColors.text : AppColors.surface;
    final fg = active ? AppColors.onLight : AppColors.text;

    return ShadIconButton.raw(
      variant: active ? ShadButtonVariant.primary : ShadButtonVariant.outline,
      icon: Icon(icon),
      iconSize: size * 0.45,
      width: size,
      height: size,
      padding: EdgeInsets.zero,
      backgroundColor: fill,
      hoverBackgroundColor: fill,
      pressedBackgroundColor: fill,
      foregroundColor: fg,
      hoverForegroundColor: fg,
      decoration: ShadDecoration(
        shape: BoxShape.circle,
        border: ShadBorder.all(
          color: active ? AppColors.text : AppColors.line,
          width: 1,
        ),
      ),
      onPressed: onTap,
    );
  }
}

/// Square icon button for headers and toolbars.
class AppIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onTap;
  final double size;

  const AppIconButton({
    super.key,
    required this.icon,
    this.onTap,
    this.size = 40,
  });

  @override
  Widget build(BuildContext context) {
    return ShadIconButton.outline(
      icon: Icon(icon),
      iconSize: size * 0.5,
      width: size,
      height: size,
      padding: EdgeInsets.zero,
      onPressed: onTap,
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
            child: Center(
              child: Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: ShadTheme.of(context).textTheme.h3,
              ),
            ),
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
        Expanded(child: Text(text, style: ShadTheme.of(context).textTheme.h3)),
        ?trailing,
      ],
    );
  }
}

/// A 1 px horizontal line, for dividing list rows.
class AppDivider extends StatelessWidget {
  const AppDivider({super.key});

  @override
  Widget build(BuildContext context) {
    return const ShadSeparator.horizontal(margin: EdgeInsets.zero);
  }
}

class AppCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;
  final Color? color;
  final Color? borderColor;
  final VoidCallback? onTap;

  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.margin,
    this.color,
    this.borderColor,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    // Cards fill the available width, like block elements, unless they sit
    // somewhere without a width limit (then they size to their content).
    Widget box = LayoutBuilder(
      builder: (context, constraints) => ShadCard(
        width: constraints.hasBoundedWidth ? double.infinity : null,
        padding: padding,
        backgroundColor: color,
        border: borderColor == null
            ? null
            : ShadBorder.all(color: borderColor!, width: 1),
        child: child,
      ),
    );

    if (onTap != null) {
      box = GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: box,
      );
    }

    return margin == null ? box : Padding(padding: margin!, child: box);
  }
}

/// Segmented control: a track with the selected segment one step lighter.
class SegmentedPill extends StatelessWidget {
  final List<String> labels;
  final int index;
  final ValueChanged<int> onChanged;

  /// Fill behind the control. Leave null (no fill) on plain screens; pass a
  /// surface colour when the control sits on top of the map.
  final Color? background;

  const SegmentedPill({
    super.key,
    required this.labels,
    required this.index,
    required this.onChanged,
    this.background,
  });

  static const _tabHeight = 35.0;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      // Tab height, 3 px track padding and the 1 px border on each side.
      height: _tabHeight + 8,
      child: ShadTabs<int>(
        value: index,
        onChanged: onChanged,
        decoration: ShadDecoration(color: background),
        tabs: [
          for (int i = 0; i < labels.length; i++)
            ShadTab<int>(
              value: i,
              height: _tabHeight,
              child: Text(
                labels[i],
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
      ),
    );
  }
}

/// A label above a value, with a small unit after the value.
class StatBlock extends StatelessWidget {
  final String value;
  final String? unit;
  final String label;
  final double valueSize;
  final CrossAxisAlignment align;

  /// The one hero number on a screen may use semibold.
  final bool hero;

  /// Colour of the number; the signature colour marks your territory.
  final Color? valueColor;

  const StatBlock({
    super.key,
    required this.value,
    required this.label,
    this.unit,
    this.valueSize = 22,
    this.align = CrossAxisAlignment.start,
    this.hero = false,
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    final textAlign = align == CrossAxisAlignment.center
        ? TextAlign.center
        : align == CrossAxisAlignment.end
        ? TextAlign.right
        : TextAlign.left;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: align,
      children: [
        Text(label, style: AppText.label, textAlign: textAlign),
        const SizedBox(height: 6),
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: value,
                  style: AppText.stat(
                    valueSize,
                    weight: hero ? FontWeight.w600 : FontWeight.w500,
                    color: valueColor ?? AppColors.text,
                  ),
                ),
                if (unit != null)
                  TextSpan(
                    text: ' ${unit!.toLowerCase()}',
                    style: AppText.unit((valueSize * 0.55).clamp(11, 20)),
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class StatDivider extends StatelessWidget {
  const StatDivider({super.key});

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      height: 40,
      child: ShadSeparator.vertical(
        margin: EdgeInsets.symmetric(horizontal: 14),
      ),
    );
  }
}

/// Stats side by side with 1 px lines between them (Strava style).
class StatRow extends StatelessWidget {
  final List<Widget> children;

  const StatRow({super.key, required this.children});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (int i = 0; i < children.length; i++) ...[
          if (i > 0) const StatDivider(),
          Expanded(child: children[i]),
        ],
      ],
    );
  }
}

enum _ButtonKind { primary, signature, secondary, destructive }

class _AppButton extends StatelessWidget {
  final _ButtonKind kind;
  final String label;
  final VoidCallback? onPressed;
  final bool loading;
  final IconData? icon;
  final double height;

  const _AppButton({
    super.key,
    required this.kind,
    required this.label,
    required this.onPressed,
    required this.loading,
    required this.icon,
    required this.height,
  });

  @override
  Widget build(BuildContext context) {
    final disabled = onPressed == null && !loading;
    final signature = kind == _ButtonKind.signature;
    final fg = switch (kind) {
      _ButtonKind.signature => AppColors.onSignature,
      _ButtonKind.secondary => AppColors.text,
      _ => AppColors.onLight,
    };

    return ShadButton.raw(
      variant: switch (kind) {
        _ButtonKind.secondary => ShadButtonVariant.outline,
        _ButtonKind.destructive => ShadButtonVariant.destructive,
        _ => ShadButtonVariant.primary,
      },
      width: double.infinity,
      height: height,
      enabled: !disabled,
      textStyle: AppText.button,
      // The signature button is the primary variant in the signature colour.
      backgroundColor: signature ? AppColors.signature : null,
      hoverBackgroundColor: signature
          ? AppColors.signature.withValues(alpha: 0.9)
          : null,
      pressedBackgroundColor: signature
          ? AppColors.signature.withValues(alpha: 0.8)
          : null,
      foregroundColor: signature ? AppColors.onSignature : null,
      hoverForegroundColor: signature ? AppColors.onSignature : null,
      onPressed: loading ? null : onPressed,
      leading: !loading && icon != null ? Icon(icon, size: 20) : null,
      child: loading
          ? SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2, color: fg),
            )
          : Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
    );
  }
}

/// Solid near-white button with near-black text.
class PrimaryButton extends _AppButton {
  const PrimaryButton({
    super.key,
    required super.label,
    required super.onPressed,
    super.loading = false,
    super.icon,
    super.height = 48,
  }) : super(kind: _ButtonKind.primary);
}

/// Button in the signature colour, for the one main action (start a run).
class SignatureButton extends _AppButton {
  const SignatureButton({
    super.key,
    required super.label,
    required super.onPressed,
    super.loading = false,
    super.icon,
    super.height = 48,
  }) : super(kind: _ButtonKind.signature);
}

/// Outlined button.
class SecondaryButton extends _AppButton {
  const SecondaryButton({
    super.key,
    required super.label,
    required super.onPressed,
    super.loading = false,
    super.icon,
    super.height = 48,
  }) : super(kind: _ButtonKind.secondary);
}

/// Solid red button, for stop and delete.
class DestructiveButton extends _AppButton {
  const DestructiveButton({
    super.key,
    required super.label,
    required super.onPressed,
    super.loading = false,
    super.icon,
    super.height = 48,
  }) : super(kind: _ButtonKind.destructive);
}

/// Thin solid progress bar.
class AppProgressBar extends StatelessWidget {
  final double value;
  final double height;

  const AppProgressBar({super.key, required this.value, this.height = 4});

  @override
  Widget build(BuildContext context) {
    return ShadProgress(
      value: value.clamp(0.0, 1.0),
      minHeight: height,
      borderRadius: BorderRadius.circular(height / 2),
    );
  }
}

/// Small rounded-rectangle badge. Pass [color] for a meaningful state
/// (positive, warning, negative); the default is neutral.
class AppChip extends StatelessWidget {
  final String label;
  final Color? color;

  const AppChip(this.label, {super.key, this.color});

  @override
  Widget build(BuildContext context) {
    final c = color;
    final text = Text(
      label,
      style: AppText.label.copyWith(fontSize: 12, color: c),
    );

    if (c == null) {
      return ShadBadge.secondary(child: text);
    }

    final tint = c.withValues(alpha: 0.14);
    return ShadBadge(
      backgroundColor: tint,
      hoverBackgroundColor: tint,
      foregroundColor: c,
      child: text,
    );
  }
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

  @override
  Widget build(BuildContext context) {
    return ShadInputFormField(
      controller: controller,
      label: Text(label),
      placeholder: Text(hint),
      obscureText: obscure,
      keyboardType: keyboardType,
      validator: validator,
      trailing: suffix,
    );
  }
}

class ErrorBanner extends StatelessWidget {
  final String text;

  const ErrorBanner(this.text, {super.key});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: ShadAlert.destructive(description: Text(text)),
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
          style: ShadTheme.of(
            context,
          ).textTheme.muted.copyWith(color: AppColors.textSecondary),
        ),
      ),
    );
  }
}

/// A list row with an icon, a title and a chevron. Rows are separated by a
/// 1 px line; wrap a few in a [Column] and end with an [AppDivider].
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
    final tint = danger ? AppColors.negative : AppColors.text;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const AppDivider(),
        GestureDetector(
          onTap: onTap,
          behavior: HitTestBehavior.opaque,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 15),
            child: Row(
              children: [
                Icon(
                  icon,
                  color: danger ? AppColors.negative : AppColors.textSecondary,
                  size: 22,
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Text(title, style: AppText.body.copyWith(color: tint)),
                ),
                const Icon(
                  Icons.chevron_right_rounded,
                  color: AppColors.textMuted,
                  size: 20,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Circle showing a runner's first letter.
class Avatar extends StatelessWidget {
  final String name;
  final double size;

  const Avatar({super.key, required this.name, this.size = 40});

  @override
  Widget build(BuildContext context) {
    return ShadAvatar(
      null,
      size: Size.square(size),
      backgroundColor: AppColors.surfaceHigh,
      shape: const CircleBorder(side: BorderSide(color: AppColors.line)),
      placeholder: Text(
        name.isNotEmpty ? name[0].toUpperCase() : '?',
        style: AppText.stat(size * 0.4),
      ),
    );
  }
}

/// Small button that switches between "Follow" and "Following".
class FollowButton extends StatelessWidget {
  final bool following;
  final VoidCallback? onTap;

  const FollowButton({super.key, required this.following, this.onTap});

  @override
  Widget build(BuildContext context) {
    final label = Text(
      following ? 'Following' : 'Follow',
      style: AppText.label.copyWith(
        color: following ? AppColors.text : AppColors.onLight,
        fontWeight: FontWeight.w600,
      ),
    );

    return following
        ? ShadButton.outline(
            height: 34,
            padding: const EdgeInsets.symmetric(horizontal: 14),
            onPressed: onTap,
            child: label,
          )
        : ShadButton(
            height: 34,
            padding: const EdgeInsets.symmetric(horizontal: 14),
            onPressed: onTap,
            child: label,
          );
  }
}
