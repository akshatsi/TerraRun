import 'package:flutter/material.dart';
import '../services/run_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';

class RunHistoryPage extends StatefulWidget {
  const RunHistoryPage({super.key});

  @override
  State<RunHistoryPage> createState() => _RunHistoryPageState();
}

class _RunHistoryPageState extends State<RunHistoryPage> {
  bool _isLoading = true;
  String? _error;
  List<dynamic> _runs = [];

  @override
  void initState() {
    super.initState();
    _loadRuns();
  }

  Future<void> _loadRuns() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final result = await RunService.getRuns();

    if (!mounted) return;

    if (result['success'] == true) {
      setState(() {
        _runs = result['runs'] as List<dynamic>;
        _isLoading = false;
      });
    } else {
      setState(() {
        _error = result['message']?.toString() ?? 'Failed to load runs';
        _isLoading = false;
      });
    }
  }

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
      'good' => (label: 'Good', color: AppColors.success),
      'fair' => (label: 'Fair', color: AppColors.gold),
      'poor' => (label: 'Poor', color: AppColors.danger),
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

  Widget _runCard(dynamic run) {
    final distance = (run['distance_km'] ?? 0).toDouble();
    final duration = (run['duration_seconds'] ?? 0) as int;
    final avgSpeed = (run['avg_speed'] ?? 0).toDouble();
    final createdAt = run['created_at']?.toString() ?? '';
    final processing = run['processing'];
    final quality = _quality(
      processing is Map ? processing['quality'] : run['quality'],
    );

    final kind = _territoryKind(run);

    return AppCard(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(18),
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
                  style: AppText.caption.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
              if (quality != null)
                Text(
                  '${quality.label} GPS',
                  style: AppText.caption.copyWith(
                    color: quality.color,
                    fontWeight: FontWeight.w700,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: StatBlock(
                  value: distance.toStringAsFixed(2),
                  unit: 'KM',
                  label: 'Distance',
                  accent: true,
                ),
              ),
              Expanded(
                child: StatBlock(
                  value: Fmt.duration(duration),
                  label: 'Duration',
                ),
              ),
              Expanded(
                child: StatBlock(
                  value: avgSpeed.toStringAsFixed(1),
                  unit: 'KM/H',
                  label: 'Avg speed',
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Column(
          children: [
            ScreenHeader(
              title: 'Run history',
              leading: IconCircleButton(
                icon: Icons.arrow_back_rounded,
                onTap: () => Navigator.pop(context),
              ),
              trailing: IconCircleButton(
                icon: Icons.refresh_rounded,
                onTap: _loadRuns,
              ),
            ),
            Expanded(
              child: _isLoading
                  ? const Center(child: AppLoader(size: 28))
                  : _error != null
                      ? MessageView(_error!)
                      : _runs.isEmpty
                          ? const MessageView('No runs saved yet')
                          : ListView.builder(
                              padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
                              itemCount: _runs.length,
                              itemBuilder: (context, index) {
                                return _runCard(_runs[index]);
                              },
                            ),
            ),
          ],
        ),
      ),
    );
  }
}
