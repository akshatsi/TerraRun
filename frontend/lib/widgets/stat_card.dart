// -----------------------------------------------
// TerraRun – Widget: Stat Card
// -----------------------------------------------
// Reusable glassmorphism stat card used on the
// dashboard. Features a gradient border, icon,
// label, and large value display.
// -----------------------------------------------

import 'package:flutter/material.dart';
import '../core/constants.dart';

class StatCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color accentColor;

  const StatCard({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
    this.accentColor = AppColors.primary,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(kCardRadius),
        border: Border.all(color: AppColors.cardBorder),
        // Subtle glow from the accent colour
        boxShadow: [
          BoxShadow(
            color: accentColor.withValues(alpha: 0.08),
            blurRadius: 20,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Icon with coloured background circle
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: accentColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, size: 20, color: accentColor),
          ),
          const SizedBox(height: 12),
          // Value
          Text(
            value,
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  color: AppColors.textPrimary,
                  fontWeight: FontWeight.w700,
                ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 4),
          // Label
          Text(
            label,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: AppColors.textMuted,
                  letterSpacing: 0.5,
                ),
          ),
        ],
      ),
    );
  }
}
