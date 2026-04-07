// -----------------------------------------------
// TerraRun – Screen: Leaderboard
// -----------------------------------------------
// Top runners ranked by territory area.
// Top 3 get gold / silver / bronze badges.
// -----------------------------------------------

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/constants.dart';
import '../models/leaderboard.dart';
import '../providers/leaderboard_provider.dart';

class LeaderboardScreen extends ConsumerWidget {
  const LeaderboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lbAsync = ref.watch(leaderboardProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Leaderboard')),
      body: RefreshIndicator(
        color: AppColors.primary,
        backgroundColor: AppColors.cardBg,
        onRefresh: () async => ref.invalidate(leaderboardProvider),
        child: lbAsync.when(
          data: (entries) {
            if (entries.isEmpty) {
              return Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.emoji_events_outlined,
                        size: 56, color: AppColors.textMuted),
                    const SizedBox(height: 12),
                    Text(
                      'No runners yet',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Be the first to capture territory!',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              );
            }
            return ListView.builder(
              padding: const EdgeInsets.all(kPadding),
              itemCount: entries.length,
              itemBuilder: (context, index) {
                return _LeaderboardTile(entry: entries[index]);
              },
            );
          },
          loading: () => const Center(
            child: CircularProgressIndicator(color: AppColors.primary),
          ),
          error: (e, _) => Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline,
                    size: 48, color: AppColors.error),
                const SizedBox(height: 12),
                Text('Failed to load leaderboard',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                ElevatedButton(
                  onPressed: () => ref.invalidate(leaderboardProvider),
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Leaderboard tile ─────────────────────────────

class _LeaderboardTile extends StatelessWidget {
  final LeaderboardEntry entry;
  const _LeaderboardTile({required this.entry});

  @override
  Widget build(BuildContext context) {
    final isTopThree = entry.rank <= 3;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        // Top 3 get a subtle gradient background
        gradient: isTopThree
            ? LinearGradient(
                colors: [
                  _medalColor.withValues(alpha: 0.10),
                  AppColors.cardBg,
                ],
                begin: Alignment.centerLeft,
                end: Alignment.centerRight,
              )
            : null,
        color: isTopThree ? null : AppColors.cardBg,
        borderRadius: BorderRadius.circular(kCardRadius),
        border: Border.all(
          color: isTopThree
              ? _medalColor.withValues(alpha: 0.3)
              : AppColors.cardBorder,
        ),
      ),
      child: Row(
        children: [
          // Rank badge
          SizedBox(
            width: 40,
            child: isTopThree ? _buildMedal() : _buildRankText(context),
          ),
          const SizedBox(width: 12),

          // Avatar placeholder
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: isTopThree
                  ? _medalColor.withValues(alpha: 0.15)
                  : AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Center(
              child: Text(
                entry.username.isNotEmpty
                    ? entry.username[0].toUpperCase()
                    : '?',
                style: TextStyle(
                  color: isTopThree ? _medalColor : AppColors.textSecondary,
                  fontWeight: FontWeight.w700,
                  fontSize: 18,
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),

          // Username & distance
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  entry.username,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight:
                            isTopThree ? FontWeight.w700 : FontWeight.w500,
                      ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${entry.distanceKm.toStringAsFixed(1)} km run',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),

          // Territory area
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                entry.areaKm2.toStringAsFixed(3),
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      color: AppColors.primary,
                      fontWeight: FontWeight.w700,
                    ),
              ),
              Text(
                'km²',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Color get _medalColor {
    switch (entry.rank) {
      case 1:
        return AppColors.gold;
      case 2:
        return AppColors.silver;
      case 3:
        return AppColors.bronze;
      default:
        return AppColors.textMuted;
    }
  }

  String get _medalEmoji {
    switch (entry.rank) {
      case 1:
        return '🥇';
      case 2:
        return '🥈';
      case 3:
        return '🥉';
      default:
        return '';
    }
  }

  Widget _buildMedal() {
    return Text(
      _medalEmoji,
      style: const TextStyle(fontSize: 24),
      textAlign: TextAlign.center,
    );
  }

  Widget _buildRankText(BuildContext context) {
    return Text(
      '#${entry.rank}',
      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: AppColors.textMuted,
            fontWeight: FontWeight.w600,
          ),
      textAlign: TextAlign.center,
    );
  }
}
