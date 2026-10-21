import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../services/leaderboard_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';

class LeaderboardPage extends StatefulWidget {
  const LeaderboardPage({super.key});

  @override
  State<LeaderboardPage> createState() => _LeaderboardPageState();
}

class _LeaderboardPageState extends State<LeaderboardPage> {
  bool _isLoading = true;
  String? _error;
  List<dynamic> _leaders = [];
  String? _myName;

  // 0 = everyone, 1 = friends
  int _scopeIndex = 0;
  // 0 = this week, 1 = all time
  int _periodIndex = 1;

  // 0 = rank by distance, 1 = rank by territory
  int _sortIndex = 0;

  String get _scope => LeaderboardService.scopes[_scopeIndex];
  String get _period => _periodIndex == 0 ? 'week' : 'all';

  @override
  void initState() {
    super.initState();
    _loadLeaderboard();
  }

  Future<void> _loadLeaderboard() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final myName = await AuthService.getUserName();
    final scope = _scope;
    final period = _period;
    final result = await LeaderboardService.getLeaderboard(
      scope: scope,
      period: period,
    );

    // Ignore an answer to a filter the user has since changed.
    if (!mounted || scope != _scope || period != _period) return;

    if (result["success"] == true) {
      setState(() {
        _myName = myName;
        _leaders = result["data"] as List<dynamic>;
        _isLoading = false;
      });
    } else {
      setState(() {
        _myName = myName;
        _error = result["message"]?.toString() ?? "Failed to fetch leaderboard";
        _isLoading = false;
      });
    }
  }

  double _distanceOf(dynamic leader) =>
      ((leader['total_distance'] ?? 0) as num).toDouble();

  double _areaOf(dynamic leader) =>
      ((leader['territory_area'] ?? 0) as num).toDouble();

  List<dynamic> get _ranked {
    final list = List<dynamic>.from(_leaders);
    if (_sortIndex == 1) {
      list.sort((a, b) => _areaOf(b).compareTo(_areaOf(a)));
    } else {
      list.sort((a, b) => _distanceOf(b).compareTo(_distanceOf(a)));
    }
    return list;
  }

  String _subtitleText(dynamic leader) {
    final runs = leader['total_runs'] ?? 0;
    final avg = ((leader['avg_speed'] ?? 0) as num).toDouble();
    final base = '$runs runs • avg ${avg.toStringAsFixed(1)}';

    if (_sortIndex == 1) {
      return '$base • ${_distanceOf(leader).toStringAsFixed(2)} km';
    }

    final area = _areaOf(leader);
    return area > 0 ? '$base • ${Fmt.areaText(area)}' : base;
  }

  Widget _buildScore(dynamic leader) {
    if (_sortIndex == 1) {
      final area = _areaOf(leader);
      if (area <= 0) {
        return Text('—', style: AppText.stat(18, color: AppColors.textMuted));
      }
      final parts = Fmt.area(area);
      return _scoreText(parts.value, parts.unit);
    }

    return _scoreText(_distanceOf(leader).toStringAsFixed(2), 'km');
  }

  Widget _scoreText(String value, String unit) {
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(text: value, style: AppText.stat(18)),
          TextSpan(text: ' ${unit.toLowerCase()}', style: AppText.unit(11)),
        ],
      ),
    );
  }

  Widget buildRankTile({required int index, required dynamic leader}) {
    final name = leader['name'].toString();
    final isMe = leader['is_me'] is bool
        ? leader['is_me'] as bool
        : _myName != null && _myName!.isNotEmpty && name == _myName;

    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadius.card),
            border: isMe ? Border.all(color: AppColors.line) : null,
          ),
          child: Row(
            children: [
              SizedBox(
                width: 28,
                child: Text(
                  '${index + 1}',
                  style: AppText.stat(
                    15,
                    color: index < 3 ? AppColors.text : AppColors.textSecondary,
                  ),
                ),
              ),
              const SizedBox(width: 6),
              Avatar(name: name, size: 36),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: AppText.body.copyWith(
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                        if (isMe) ...[
                          const SizedBox(width: 6),
                          const AppChip('You', color: AppColors.signature),
                        ],
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(
                      _subtitleText(leader),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppText.caption,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              _buildScore(leader),
            ],
          ),
        ),
        const AppDivider(),
      ],
    );
  }

  void _setFilter({int? scope, int? period}) {
    setState(() {
      _scopeIndex = scope ?? _scopeIndex;
      _periodIndex = period ?? _periodIndex;
    });
    _loadLeaderboard();
  }

  Widget _buildFilters() {
    return Column(
      children: [
        SegmentedPill(
          labels: const ['Everyone', 'Friends'],
          index: _scopeIndex,
          onChanged: (i) => _setFilter(scope: i),
        ),
        const SizedBox(height: 10),
        SegmentedPill(
          labels: const ['This week', 'All time'],
          index: _periodIndex,
          onChanged: (i) => _setFilter(period: i),
        ),
        const SizedBox(height: 10),
      ],
    );
  }

  Widget _buildContent() {
    if (_isLoading) {
      return const Padding(
        padding: EdgeInsets.only(top: 80),
        child: Center(child: AppLoader(size: 28)),
      );
    }

    if (_error != null) {
      return Padding(
        padding: const EdgeInsets.only(top: 80),
        child: MessageView(_error!),
      );
    }

    if (_leaders.isEmpty) {
      return Padding(
        padding: const EdgeInsets.only(top: 60),
        child: MessageView(
          _scopeIndex == 1
              ? 'No friends on the board yet. Follow runners from the '
                    'Friends screen on the Map tab.'
              : _periodIndex == 0
              ? 'No runs this week yet'
              : 'No leaderboard data yet',
        ),
      );
    }

    final ranked = _ranked;
    final top = ranked.first;
    final topDistance = _distanceOf(
      _leaders.reduce((a, b) => _distanceOf(a) >= _distanceOf(b) ? a : b),
    );
    final topArea = _leaders.map(_areaOf).reduce((a, b) => a > b ? a : b);

    final sortedByDistance = List<dynamic>.from(_leaders)
      ..sort((a, b) => _distanceOf(b).compareTo(_distanceOf(a)));
    final gap = sortedByDistance.length > 1
        ? (_distanceOf(sortedByDistance[0]) - _distanceOf(sortedByDistance[1]))
              .abs()
        : 0.0;

    final area = Fmt.area(topArea);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('LIVE RANKINGS', style: AppText.overline),
              const SizedBox(height: 10),
              Text(
                '${sortedByDistance.first['name']} is ranked #1',
                style: AppText.headline,
              ),
              const SizedBox(height: 6),
              Text(
                _leaders.length > 1
                    ? 'Top spot lead: ${gap.toStringAsFixed(2)} km'
                    : 'Only one runner on the board right now.',
                style: AppText.bodySecondary,
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        AppCard(
          child: StatRow(
            children: [
              StatBlock(
                value: topDistance.toStringAsFixed(2),
                unit: 'km',
                label: 'Top distance',
              ),
              StatBlock(value: _leaders.length.toString(), label: 'Players'),
              topArea > 0
                  ? StatBlock(
                      value: area.value,
                      unit: area.unit,
                      label: 'Top territory',
                    )
                  : StatBlock(
                      value: '${top['total_runs'] ?? 0}',
                      label: 'Top runs',
                    ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        SegmentedPill(
          labels: const ['Distance', 'Territory'],
          index: _sortIndex,
          onChanged: (i) => setState(() => _sortIndex = i),
        ),
        const SizedBox(height: 16),
        ...List.generate(ranked.length, (index) {
          return buildRankTile(index: index, leader: ranked[index]);
        }),
      ],
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
              title: 'Leaderboard',
              leading: const AppIconButton(icon: Icons.emoji_events_outlined),
              trailing: AppIconButton(
                icon: Icons.refresh_rounded,
                onTap: _loadLeaderboard,
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _loadLeaderboard,
                color: AppColors.text,
                backgroundColor: AppColors.surfaceHigh,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [_buildFilters(), _buildContent()],
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
