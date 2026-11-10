import 'package:flutter/material.dart';
import '../models/route_suggestion.dart';
import '../services/suggestion_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import 'app_widgets.dart';

/// Opens the suggestions sheet. Completes with the route the runner picked,
/// or null if they closed it.
Future<RouteSuggestion?> showSuggestionSheet(
  BuildContext context, {
  required double lat,
  required double lng,
}) {
  return showModalBottomSheet<RouteSuggestion>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.surface,
    barrierColor: Colors.black54,
    elevation: 0,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.card)),
      side: BorderSide(color: AppColors.line),
    ),
    constraints: BoxConstraints(
      maxHeight: MediaQuery.of(context).size.height * 0.85,
    ),
    builder: (_) => SuggestionSheet(lat: lat, lng: lng),
  );
}

class SuggestionSheet extends StatefulWidget {
  final double lat;
  final double lng;

  const SuggestionSheet({super.key, required this.lat, required this.lng});

  /// Loop length for each choice, as a share of the server's target.
  static const lengthFactors = [1.0, 0.6, 1.5];
  static const lengthLabels = ['Usual', 'Short', 'Long'];

  /// The `distance_km` to ask for. Null for "Usual": the server then picks.
  static double? distanceFor(int index, double? targetKm) {
    if (index == 0) return null;
    final base = (targetKm == null || targetKm <= 0) ? 2.0 : targetKm;
    final km = base * lengthFactors[index];
    return ((km * 10).round() / 10).clamp(0.5, 20.0);
  }

  @override
  State<SuggestionSheet> createState() => _SuggestionSheetState();
}

class _SuggestionSheetState extends State<SuggestionSheet> {
  int _length = 0;
  bool _loading = true;
  String? _error;
  SuggestionsResult? _result;

  // The server's own target for this runner, from the first answer.
  double? _targetKm;

  // Ignores an answer when a newer request has started.
  int _request = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final id = ++_request;
    setState(() {
      _loading = true;
      _error = null;
    });

    final result = await SuggestionService.getSuggestions(
      widget.lat,
      widget.lng,
      distanceKm: SuggestionSheet.distanceFor(_length, _targetKm),
    );

    if (!mounted || id != _request) return;

    if (result['success'] == true) {
      final data = result['data'] as SuggestionsResult;
      setState(() {
        _result = data;
        _loading = false;
        if (_length == 0 && data.targetDistanceKm > 0) {
          _targetKm = data.targetDistanceKm;
        }
      });
    } else {
      setState(() {
        _error = result['message']?.toString();
        _result = null;
        _loading = false;
      });
    }
  }

  Widget _body() {
    if (_loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 48),
        child: Center(child: AppLoader()),
      );
    }

    if (_error != null) {
      return Column(
        children: [
          ErrorBanner(_error!),
          const SizedBox(height: 12),
          SecondaryButton(label: 'Try again', onPressed: _load),
        ],
      );
    }

    final result = _result;
    if (result == null || result.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 32),
        child: MessageView(result?.message ?? 'No road loops near you yet'),
      );
    }

    return Column(
      children: [
        for (final s in result.suggestions.take(3)) ...[
          _SuggestionCard(
            suggestion: s,
            onTap: () => Navigator.of(context).pop(s),
          ),
          const SizedBox(height: 10),
        ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(child: Text('Suggest a route', style: AppText.title)),
                AppIconButton(
                  icon: Icons.close_rounded,
                  size: 36,
                  onTap: () => Navigator.of(context).pop(),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              'Loops on main roads that grow your land.',
              style: AppText.bodySecondary,
            ),
            const SizedBox(height: 14),
            SegmentedPill(
              labels: SuggestionSheet.lengthLabels,
              index: _length,
              onChanged: (i) {
                if (i == _length) return;
                setState(() => _length = i);
                _load();
              },
            ),
            const SizedBox(height: 14),
            _body(),
          ],
        ),
      ),
    );
  }
}

class _SuggestionCard extends StatelessWidget {
  final RouteSuggestion suggestion;
  final VoidCallback onTap;

  const _SuggestionCard({required this.suggestion, required this.onTap});

  String get _gains {
    final s = suggestion;
    final parts = <String>[];
    if (s.newAreaSqM >= 1) parts.add('${Fmt.areaText(s.newAreaSqM)} new land');
    if (s.stolenAreaSqM >= 1) {
      final names = s.friendNames;
      parts.add(
        '${Fmt.areaText(s.stolenAreaSqM)} from friends'
        '${names.isEmpty ? '' : ' ($names)'}',
      );
    }
    return parts.isEmpty ? 'No new land' : parts.join(' · ');
  }

  @override
  Widget build(BuildContext context) {
    final s = suggestion;
    final gain = Fmt.area(s.gainSqM);

    return AppCard(
      onTap: onTap,
      color: AppColors.bg,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(s.label, style: AppText.headline),
          if (s.reason.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(s.reason, style: AppText.bodySecondary),
          ],
          const SizedBox(height: 14),
          StatRow(
            children: [
              StatBlock(
                value: s.distanceKm.toStringAsFixed(1),
                unit: 'km',
                label: 'Distance',
                valueSize: 18,
              ),
              StatBlock(
                value: '${s.estimatedMinutes}',
                unit: 'min',
                label: 'Time',
                valueSize: 18,
              ),
              StatBlock(
                value: '+${gain.value}',
                unit: gain.unit,
                label: 'Gain',
                valueSize: 18,
                valueColor: AppColors.signature,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(_gains, style: AppText.caption),
        ],
      ),
    );
  }
}
