import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import '../models/run_detail.dart';
import '../services/run_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';
import '../widgets/map_tiles.dart';

/// One run in full: the route and territory on a map, a stat grid and the
/// kilometre splits.
class RunDetailPage extends StatefulWidget {
  final int runId;

  const RunDetailPage({super.key, required this.runId});

  @override
  State<RunDetailPage> createState() => _RunDetailPageState();
}

class _RunDetailPageState extends State<RunDetailPage> {
  static const _months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];

  bool _isLoading = true;
  String? _error;
  RunDetail? _run;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final result = await RunService.getRunDetail(widget.runId);
    if (!mounted) return;

    setState(() {
      _isLoading = false;
      if (result['success'] == true && result['data'] is RunDetail) {
        _run = result['data'] as RunDetail;
      } else {
        _error = result['message']?.toString() ?? 'Failed to load run';
      }
    });
  }

  String _date(DateTime? when) {
    if (when == null) return '';
    final d = when.toLocal();
    return '${d.day} ${_months[d.month - 1]} ${d.year}';
  }

  Color _routeColor(RunDetail run) {
    if (run.isMine) return AppColors.mine;
    return AppColors.rivalPalette[run.userId % AppColors.rivalPalette.length];
  }

  Widget _header(RunDetail? run) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
      child: Row(
        children: [
          AppIconButton(
            icon: Icons.arrow_back_rounded,
            onTap: () => Navigator.of(context).pop(),
          ),
          const SizedBox(width: 12),
          if (run != null) ...[
            Avatar(name: run.userName, size: 36),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    run.userName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.body.copyWith(fontWeight: FontWeight.w500),
                  ),
                  Text(
                    [
                      if (run.isMine) 'Your run',
                      if (_date(run.createdAt).isNotEmpty) _date(run.createdAt),
                    ].join(' · '),
                    style: AppText.caption,
                  ),
                ],
              ),
            ),
          ] else
            Expanded(child: Text('Run', style: AppText.headline)),
        ],
      ),
    );
  }

  Widget _marker({required bool filled}) {
    return Container(
      decoration: BoxDecoration(
        color: filled ? AppColors.text : AppColors.bg,
        shape: BoxShape.circle,
        border: Border.all(
          color: filled ? AppColors.bg : AppColors.text,
          width: 3,
        ),
      ),
    );
  }

  Widget _map(RunDetail run, double height) {
    final lines = run.routeLines;
    final rings = run.awardedRings.where((r) => r.length >= 3).toList();
    final all = [for (final l in lines) ...l, for (final r in rings) ...r];

    if (all.isEmpty) {
      return Container(
        height: height,
        color: AppColors.surface,
        child: const MessageView('No route recorded for this run'),
      );
    }

    final color = _routeColor(run);
    final start = lines.isEmpty ? null : lines.first.first;
    final end = lines.isEmpty ? null : lines.last.last;

    return SizedBox(
      height: height,
      child: FlutterMap(
        options: MapOptions(
          backgroundColor: AppColors.bg,
          initialCameraFit: all.length < 2
              ? null
              : CameraFit.bounds(
                  bounds: LatLngBounds.fromPoints(all),
                  padding: const EdgeInsets.all(36),
                  maxZoom: 18,
                ),
          initialCenter: all.first,
          initialZoom: 16,
          interactionOptions: const InteractionOptions(
            flags:
                InteractiveFlag.drag |
                InteractiveFlag.pinchZoom |
                InteractiveFlag.doubleTapZoom,
          ),
        ),
        children: [
          buildBaseTileLayer(),
          if (rings.isNotEmpty)
            PolygonLayer(
              polygons: [
                for (final ring in rings)
                  Polygon(
                    points: ring,
                    color: color.withValues(alpha: 0.25),
                    borderColor: color,
                    borderStrokeWidth: 1,
                  ),
              ],
            ),
          if (lines.isNotEmpty)
            PolylineLayer(
              polylines: [
                for (final line in lines)
                  Polyline(points: line, strokeWidth: 4, color: color),
              ],
            ),
          if (start != null && end != null)
            MarkerLayer(
              markers: [
                Marker(
                  point: start,
                  width: 18,
                  height: 18,
                  child: _marker(filled: false),
                ),
                Marker(
                  point: end,
                  width: 18,
                  height: 18,
                  child: _marker(filled: true),
                ),
              ],
            ),
        ],
      ),
    );
  }

  /// The stats this run has, as label / value / unit.
  List<({String label, String value, String? unit})> _stats(RunDetail run) {
    final stats = <({String label, String value, String? unit})>[];

    stats.add((
      label: 'Distance',
      value: run.distanceKm.toStringAsFixed(2),
      unit: 'km',
    ));
    final moving = run.movingTimeS;
    if (moving != null) {
      stats.add((
        label: 'Moving time',
        value: Fmt.durationFrom(moving),
        unit: null,
      ));
    }
    if (run.avgPaceSPerKm != null) {
      stats.add((
        label: 'Avg pace',
        value: Fmt.pace(run.avgPaceSPerKm),
        unit: '/km',
      ));
    }
    if (run.avgSpeedKmh > 0) {
      stats.add((
        label: 'Avg speed',
        value: run.avgSpeedKmh.toStringAsFixed(1),
        unit: 'km/h',
      ));
    }
    if (run.elevationGainM != null) {
      stats.add((
        label: 'Elevation gain',
        value: run.elevationGainM!.round().toString(),
        unit: 'm',
      ));
    }
    if (run.maxSpeedKmh != null) {
      stats.add((
        label: 'Max speed',
        value: run.maxSpeedKmh!.toStringAsFixed(1),
        unit: 'km/h',
      ));
    }

    final kind = switch (run.territoryKind) {
      'loop' => 'Loop',
      'route' => 'Route',
      _ => null,
    };
    if (kind != null) {
      final a = Fmt.area(run.awardedAreaSqM);
      stats.add((label: 'Territory · $kind', value: a.value, unit: a.unit));
    }

    final quality = switch (run.quality) {
      'good' => 'Good',
      'fair' => 'Fair',
      'poor' => 'Poor',
      _ => null,
    };
    if (quality != null) {
      stats.add((label: 'GPS quality', value: quality, unit: null));
    }
    return stats;
  }

  Widget _statGrid(RunDetail run) {
    final stats = _stats(run);
    const columns = 3;
    final rows = <Widget>[];

    for (var start = 0; start < stats.length; start += columns) {
      final chunk = stats.sublist(
        start,
        (start + columns).clamp(0, stats.length),
      );
      rows.add(const AppDivider());
      rows.add(
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: StatRow(
            children: [
              for (final s in chunk)
                StatBlock(
                  label: s.label,
                  value: s.value,
                  unit: s.unit,
                  hero: start == 0 && s == chunk.first,
                  valueColor: s.label.startsWith('Territory')
                      ? AppColors.signature
                      : null,
                ),
              for (var i = chunk.length; i < columns; i++)
                const SizedBox.shrink(),
            ],
          ),
        ),
      );
    }
    rows.add(const AppDivider());
    return Column(children: rows);
  }

  Widget _splitRow(RunSplit split, int? fastest) {
    final partial = split.distanceM < 995;
    final km = partial
        ? (split.distanceM / 1000).toStringAsFixed(2)
        : '${split.km}';
    final elev = split.elevationChangeM;
    final isFastest = fastest != null && split.paceSPerKm == fastest;
    final fraction = RunSplit.barFraction(split.paceSPerKm, fastest ?? 0);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Row(
            children: [
              SizedBox(width: 44, child: Text(km, style: AppText.stat(15))),
              SizedBox(
                width: 48,
                child: Text(
                  Fmt.pace(split.paceSPerKm),
                  style: AppText.stat(15),
                ),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: FractionallySizedBox(
                      widthFactor: fraction,
                      child: Container(
                        height: 6,
                        decoration: BoxDecoration(
                          color: isFastest
                              ? AppColors.text
                              : AppColors.textMuted,
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              SizedBox(
                width: 44,
                child: Text(
                  elev == null
                      ? '—'
                      : '${elev >= 0 ? '+' : '−'}${elev.abs().round()}',
                  textAlign: TextAlign.right,
                  style: AppText.stat(15, color: AppColors.textSecondary),
                ),
              ),
            ],
          ),
        ),
        const AppDivider(),
      ],
    );
  }

  Widget _splits(RunDetail run) {
    if (run.splits.isEmpty) {
      return Text('No split data for this run', style: AppText.bodySecondary);
    }
    final fastest = run.fastestPace;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            children: [
              SizedBox(width: 44, child: Text('KM', style: AppText.overline)),
              SizedBox(width: 48, child: Text('PACE', style: AppText.overline)),
              const Spacer(),
              SizedBox(
                width: 44,
                child: Text(
                  'ELEV',
                  textAlign: TextAlign.right,
                  style: AppText.overline,
                ),
              ),
            ],
          ),
        ),
        const AppDivider(),
        for (final split in run.splits) _splitRow(split, fastest),
      ],
    );
  }

  Widget _body() {
    if (_isLoading) return const Center(child: AppLoader(size: 28));
    final run = _run;
    if (_error != null || run == null) {
      return MessageView(_error ?? 'Failed to load run');
    }

    final mapHeight = MediaQuery.of(context).size.height * 0.45;

    return RefreshIndicator(
      onRefresh: _load,
      color: AppColors.text,
      backgroundColor: AppColors.surfaceHigh,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _map(run, mapHeight),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _statGrid(run),
                  const SizedBox(height: 26),
                  const SectionTitle('Splits'),
                  const SizedBox(height: 12),
                  _splits(run),
                ],
              ),
            ),
          ],
        ),
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
            _header(_run),
            Expanded(child: _body()),
          ],
        ),
      ),
    );
  }
}
