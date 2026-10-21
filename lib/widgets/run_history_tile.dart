import 'package:flutter/material.dart';
import '../screens/run_detail_page.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import 'app_widgets.dart';

/// One run in a run history list: date, loop/route, GPS quality and the main
/// stats. Tapping it opens the run detail screen.
class RunHistoryTile extends StatelessWidget {
  final dynamic run;

  const RunHistoryTile({super.key, required this.run});

  String _formatDate(String isoString) {
    try {
      final dt = DateTime.parse(isoString).toLocal();
      return '${dt.day}/${dt.month}/${dt.year}';
    } catch (_) {
      return isoString;
    }
  }

  ({String label, Color color})? _quality(dynamic value) {
    return switch (value) {
      'good' => (label: 'Good', color: AppColors.positive),
      'fair' => (label: 'Fair', color: AppColors.warning),
      'poor' => (label: 'Poor', color: AppColors.negative),
      _ => null,
    };
  }

  String? _territoryKind(dynamic run) {
    final territory = run['territory'];
    final kind = territory is Map ? territory['kind'] : run['territory_kind'];
    return switch (kind) {
      'loop' => 'Loop',
      'route' => 'Route',
      _ => null,
    };
  }

  @override
  Widget build(BuildContext context) {
    final distance = (run['distance_km'] ?? 0).toDouble();
    final duration = (run['duration_seconds'] ?? 0) as int;
    final avgSpeed = (run['avg_speed'] ?? 0).toDouble();
    final createdAt = run['created_at']?.toString() ?? '';
    final processing = run['processing'];
    final quality = _quality(
      processing is Map ? processing['quality'] : run['quality'],
    );

    final kind = _territoryKind(run);

    final id = (run['id'] as num?)?.toInt();

    return Column(
      children: [
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: id == null
              ? null
              : () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => RunDetailPage(runId: id)),
                ),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        _formatDate(createdAt).toUpperCase(),
                        style: AppText.overline,
                      ),
                    ),
                    if (kind != null)
                      Text(
                        quality == null ? kind : '$kind · ',
                        style: AppText.label,
                      ),
                    if (quality != null)
                      Text(
                        '${quality.label} GPS',
                        style: AppText.label.copyWith(color: quality.color),
                      ),
                  ],
                ),
                const SizedBox(height: 12),
                StatRow(
                  children: [
                    StatBlock(
                      value: distance.toStringAsFixed(2),
                      unit: 'km',
                      label: 'Distance',
                    ),
                    StatBlock(value: Fmt.duration(duration), label: 'Duration'),
                    StatBlock(
                      value: avgSpeed.toStringAsFixed(1),
                      unit: 'km/h',
                      label: 'Avg speed',
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const AppDivider(),
      ],
    );
  }

}
