// -----------------------------------------------
// TerraRun – Screen: Dashboard
// -----------------------------------------------
// Stat cards (distance, territory, streak) and a
// recent‑runs list. Pull‑to‑refresh supported.
// -----------------------------------------------

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import '../core/constants.dart';
import '../models/run.dart';
import '../providers/auth_provider.dart';
import '../providers/user_provider.dart';
import '../providers/runs_provider.dart';
import '../widgets/stat_card.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final userAsync = ref.watch(userProvider);
    final runsAsync = ref.watch(runsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('TerraRun'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout_rounded, size: 22),
            tooltip: 'Logout',
            onPressed: () => ref.read(authProvider.notifier).logout(),
          ),
        ],
      ),
      body: RefreshIndicator(
        color: AppColors.primary,
        backgroundColor: AppColors.cardBg,
        onRefresh: () async {
          ref.invalidate(userProvider);
          ref.invalidate(runsProvider);
        },
        child: ListView(
          padding: const EdgeInsets.all(kPadding),
          children: [
            // ── Greeting ──
            userAsync.when(
              data: (user) => _GreetingBanner(username: user.username),
              loading: () => const _GreetingBanner(username: '...'),
              error: (_, __) => const _GreetingBanner(username: 'Runner'),
            ),
            const SizedBox(height: 20),

            // ── Stat cards ──
            userAsync.when(
              data: (user) => _StatRow(
                distanceKm: user.distanceKm,
                areaKm2: user.areaKm2,
                streak: user.streakDays,
              ),
              loading: () => const _StatRow(
                distanceKm: 0,
                areaKm2: 0,
                streak: 0,
              ),
              error: (_, __) => const _StatRow(
                distanceKm: 0,
                areaKm2: 0,
                streak: 0,
              ),
            ),
            const SizedBox(height: 28),

            // ── Recent Runs header ──
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Recent Runs',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Text(
                  runsAsync.whenOrNull(data: (r) => '${r.length} runs') ?? '',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
            const SizedBox(height: 12),

            // ── Runs list ──
            runsAsync.when(
              data: (runs) {
                if (runs.isEmpty) {
                  return const _EmptyRunsCard();
                }
                return Column(
                  children: runs.map((r) => _RunCard(run: r)).toList(),
                );
              },
              loading: () => const Center(
                child: Padding(
                  padding: EdgeInsets.all(32),
                  child: CircularProgressIndicator(color: AppColors.primary),
                ),
              ),
              error: (e, _) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(32),
                  child: Text(
                    'Failed to load runs',
                    style: TextStyle(color: AppColors.textMuted),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Greeting banner ──────────────────────────────

class _GreetingBanner extends StatelessWidget {
  final String username;
  const _GreetingBanner({required this.username});

  @override
  Widget build(BuildContext context) {
    final hour = DateTime.now().hour;
    String greeting;
    if (hour < 12) {
      greeting = 'Good morning';
    } else if (hour < 17) {
      greeting = 'Good afternoon';
    } else {
      greeting = 'Good evening';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '$greeting,',
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: AppColors.textMuted,
              ),
        ),
        Text(
          username,
          style: Theme.of(context).textTheme.displayMedium,
        ),
      ],
    );
  }
}

// ── Stat cards row ───────────────────────────────

class _StatRow extends StatelessWidget {
  final double distanceKm;
  final double areaKm2;
  final int streak;

  const _StatRow({
    required this.distanceKm,
    required this.areaKm2,
    required this.streak,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: StatCard(
            icon: Icons.route_rounded,
            label: 'Distance',
            value: '${distanceKm.toStringAsFixed(1)} km',
            accentColor: AppColors.accent,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: StatCard(
            icon: Icons.hexagon_outlined,
            label: 'Territory',
            value: '${areaKm2.toStringAsFixed(3)} km²',
            accentColor: AppColors.primary,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: StatCard(
            icon: Icons.local_fire_department_rounded,
            label: 'Streak',
            value: '$streak days',
            accentColor: AppColors.warning,
          ),
        ),
      ],
    );
  }
}

// ── Empty state ──────────────────────────────────

class _EmptyRunsCard extends StatelessWidget {
  const _EmptyRunsCard();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(kCardRadius),
        border: Border.all(color: AppColors.cardBorder),
      ),
      child: Column(
        children: [
          Icon(Icons.directions_run_rounded,
              size: 48, color: AppColors.textMuted),
          const SizedBox(height: 12),
          Text(
            'No runs yet',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 6),
          Text(
            'Start your first run to capture territory!',
            style: Theme.of(context).textTheme.bodySmall,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

// ── Run card ─────────────────────────────────────

class _RunCard extends StatelessWidget {
  final RunModel run;
  const _RunCard({required this.run});

  @override
  Widget build(BuildContext context) {
    final dateStr = DateFormat('MMM d, yyyy • h:mm a').format(run.startedAt.toLocal());

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(kCardRadius),
        border: Border.all(color: AppColors.cardBorder),
      ),
      child: Row(
        children: [
          // Left accent bar
          Container(
            width: 4,
            height: 48,
            decoration: BoxDecoration(
              color: AppColors.primary,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(width: 14),
          // Info
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  dateStr,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    _RunStat(
                      icon: Icons.straighten,
                      value: '${run.distanceKm.toStringAsFixed(2)} km',
                    ),
                    const SizedBox(width: 20),
                    _RunStat(
                      icon: Icons.timer_outlined,
                      value: run.durationFormatted,
                    ),
                    const SizedBox(width: 20),
                    _RunStat(
                      icon: Icons.speed,
                      value: run.paceFormatted,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _RunStat extends StatelessWidget {
  final IconData icon;
  final String value;
  const _RunStat({required this.icon, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: AppColors.textMuted),
        const SizedBox(width: 4),
        Text(
          value,
          style: Theme.of(context).textTheme.labelLarge?.copyWith(
                fontSize: 13,
              ),
        ),
      ],
    );
  }
}
