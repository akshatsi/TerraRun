// -----------------------------------------------
// TerraRun – Screen: Run Tracking
// -----------------------------------------------
// "Start Run" begins GPS tracking. Shows a live map
// with the route polyline and distance/time counters.
// "Finish Run" submits to the backend.
//
// GEOLOCATOR STREAM SETUP IS COMMENTED IN
// providers/run_tracking_provider.dart.
// -----------------------------------------------

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/constants.dart';
import '../providers/run_tracking_provider.dart';

class RunScreen extends ConsumerStatefulWidget {
  const RunScreen({super.key});

  @override
  ConsumerState<RunScreen> createState() => _RunScreenState();
}

class _RunScreenState extends ConsumerState<RunScreen>
    with SingleTickerProviderStateMixin {
  final MapController _mapController = MapController();
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tracking = ref.watch(runTrackingProvider);

    // Listen for errors
    ref.listen<RunTrackingState>(runTrackingProvider, (prev, next) {
      if (next.error != null && next.error != prev?.error) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(next.error!),
            backgroundColor: AppColors.error,
          ),
        );
      }

      // Auto-center map on latest position during tracking
      if (next.status == TrackingStatus.tracking &&
          next.routeLatLngs.isNotEmpty &&
          next.routeLatLngs.length != (prev?.routeLatLngs.length ?? 0)) {
        _mapController.move(next.routeLatLngs.last, 16);
      }
    });

    return Scaffold(
      body: Stack(
        children: [
          // ── Map showing live route ──
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: tracking.routeLatLngs.isNotEmpty
                  ? tracking.routeLatLngs.last
                  : kDefaultMapCenter,
              initialZoom: 16,
            ),
            children: [
              TileLayer(
                urlTemplate: kTileUrlTemplate,
                maxZoom: 19,
                userAgentPackageName: 'com.terrarun.app',
              ),
              // ── Route polyline ──
              if (tracking.routeLatLngs.length >= 2)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: tracking.routeLatLngs,
                      strokeWidth: 4.0,
                      color: AppColors.primaryLight,
                    ),
                  ],
                ),
              // ── Current position marker ──
              if (tracking.routeLatLngs.isNotEmpty)
                MarkerLayer(
                  markers: [
                    Marker(
                      point: tracking.routeLatLngs.last,
                      width: 20,
                      height: 20,
                      child: Container(
                        decoration: BoxDecoration(
                          color: AppColors.primary,
                          shape: BoxShape.circle,
                          border:
                              Border.all(color: Colors.white, width: 3),
                          boxShadow: [
                            BoxShadow(
                              color: AppColors.primary.withValues(alpha: 0.5),
                              blurRadius: 10,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
            ],
          ),

          // ── Top gradient ──
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: Container(
              height: MediaQuery.of(context).padding.top + 20,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.scaffoldBg.withValues(alpha: 0.8),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),

          // ── Bottom control panel ──
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: _buildControlPanel(context, tracking),
          ),
        ],
      ),
    );
  }

  Widget _buildControlPanel(BuildContext context, RunTrackingState tracking) {
    final isTracking = tracking.status == TrackingStatus.tracking;
    final isSubmitting = tracking.status == TrackingStatus.submitting;
    final isIdle = tracking.status == TrackingStatus.idle;

    return Container(
      padding: EdgeInsets.fromLTRB(
          24, 20, 24, MediaQuery.of(context).padding.bottom + 20),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        border: const Border(
          top: BorderSide(color: AppColors.cardBorder),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.3),
            blurRadius: 20,
            offset: const Offset(0, -5),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // ── Stats row (visible while tracking) ──
          if (isTracking || isSubmitting) ...[
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _LiveStat(
                  label: 'Distance',
                  value: tracking.distanceDisplay,
                  icon: Icons.straighten,
                ),
                Container(
                  width: 1,
                  height: 40,
                  color: AppColors.cardBorder,
                ),
                _LiveStat(
                  label: 'Time',
                  value: tracking.elapsedDisplay,
                  icon: Icons.timer_outlined,
                ),
                Container(
                  width: 1,
                  height: 40,
                  color: AppColors.cardBorder,
                ),
                _LiveStat(
                  label: 'Points',
                  value: '${tracking.recordedPoints.length}',
                  icon: Icons.gps_fixed,
                ),
              ],
            ),
            const SizedBox(height: 20),
          ],

          // ── Action buttons ──
          if (isIdle)
            // Start button with pulsing animation
            AnimatedBuilder(
              animation: _pulseController,
              builder: (context, child) {
                final scale = 1.0 + _pulseController.value * 0.05;
                return Transform.scale(
                  scale: scale,
                  child: child,
                );
              },
              child: SizedBox(
                width: double.infinity,
                height: 56,
                child: ElevatedButton.icon(
                  onPressed: () {
                    ref.read(runTrackingProvider.notifier).startTracking();
                  },
                  icon: const Icon(Icons.play_arrow_rounded, size: 28),
                  label: const Text('Start Run',
                      style: TextStyle(fontSize: 18)),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                ),
              ),
            ),

          if (isTracking)
            Row(
              children: [
                // Cancel button
                Expanded(
                  child: SizedBox(
                    height: 52,
                    child: OutlinedButton(
                      onPressed: () {
                        _showCancelDialog(context);
                      },
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: AppColors.error),
                        foregroundColor: AppColors.error,
                      ),
                      child: const Text('Cancel'),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                // Finish button
                Expanded(
                  flex: 2,
                  child: SizedBox(
                    height: 52,
                    child: ElevatedButton.icon(
                      onPressed: _finishRun,
                      icon: const Icon(Icons.stop_rounded, size: 24),
                      label: const Text('Finish Run',
                          style: TextStyle(fontSize: 16)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.primary,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),

          if (isSubmitting)
            const Column(
              children: [
                CircularProgressIndicator(color: AppColors.primary),
                SizedBox(height: 12),
                Text(
                  'Submitting your run...',
                  style: TextStyle(color: AppColors.textSecondary),
                ),
              ],
            ),
        ],
      ),
    );
  }

  Future<void> _finishRun() async {
    final run =
        await ref.read(runTrackingProvider.notifier).finishRun();
    if (run != null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              'Run saved! ${run.distanceKm.toStringAsFixed(2)} km captured'),
          backgroundColor: AppColors.success,
        ),
      );
    }
  }

  void _showCancelDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.cardBg,
        title: const Text('Cancel Run?'),
        content: const Text(
          'Your tracking data will be lost.',
          style: TextStyle(color: AppColors.textSecondary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Keep Running'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              ref.read(runTrackingProvider.notifier).cancelTracking();
            },
            child: const Text('Cancel Run',
                style: TextStyle(color: AppColors.error)),
          ),
        ],
      ),
    );
  }
}

// ── Live stat display ────────────────────────────

class _LiveStat extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;

  const _LiveStat({
    required this.label,
    required this.value,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: AppColors.textMuted),
        const SizedBox(height: 4),
        Text(
          value,
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              ),
        ),
        Text(
          label,
          style: const TextStyle(
            color: AppColors.textMuted,
            fontSize: 11,
          ),
        ),
      ],
    );
  }
}
