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

  // 0 = rank by distance, 1 = rank by territory
  int _sortIndex = 0;

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
    final result = await LeaderboardService.getLeaderboard();

    if (!mounted) return;

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

  Color _rankColor(int index) {
    switch (index) {
      case 0:
        return AppColors.gold;
      case 1:
        return AppColors.silver;
      case 2:
        return AppColors.bronze;
      default:
        return Colors.white;
    }
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

    return _scoreText(_distanceOf(leader).toStringAsFixed(2), 'KM');
  }

  Widget _scoreText(String value, String unit) {
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(text: value, style: AppText.stat(18)),
          TextSpan(
            text: ' $unit',
            style: AppText.stat(10, weight: FontWeight.w700),
          ),
        ],
      ),
    );
  }

  Widget buildRankTile({
    required int index,
    required dynamic leader,
  }) {
    final name = leader['name'].toString();
    final isMe = _myName != null && _myName!.isNotEmpty && name == _myName;
    final tint = AppColors.rowTints[index % AppColors.rowTints.length];

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: tint,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: isMe ? AppColors.pink : AppColors.border,
          width: isMe ? 1.4 : 1,
        ),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 24,
            child: Text(
              '${index + 1}',
              style: AppText.stat(15, color: _rankColor(index)),
            ),
          ),
          const SizedBox(width: 8),
          Container(
            width: 40,
            height: 40,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              gradient: AppColors.territoryGradient,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              name.isNotEmpty ? name[0].toUpperCase() : '?',
              style: AppText.stat(16),
            ),
          ),
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
                        style: AppText.subtitle,
                      ),
                    ),
                    if (isMe) ...[
                      const SizedBox(width: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.pink.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          'YOU',
                          style: AppText.overline.copyWith(
                            color: AppColors.pink,
                            fontSize: 9,
                          ),
                        ),
                      ),
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
      return const Padding(
        padding: EdgeInsets.only(top: 80),
        child: MessageView('No leaderboard data yet'),
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
        HeroCard(
          padding: const EdgeInsets.fromLTRB(22, 22, 22, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'LIVE RANKINGS',
                style: AppText.overline.copyWith(
                  color: Colors.white.withValues(alpha: 0.75),
                ),
              ),
              const SizedBox(height: 12),
              Text(
                '${sortedByDistance.first['name']} is ranked #1',
                style: AppText.headline,
              ),
              const SizedBox(height: 8),
              Text(
                _leaders.length > 1
                    ? 'Top spot lead: ${gap.toStringAsFixed(2)} km'
                    : 'Only one runner on the board right now.',
                style: AppText.body.copyWith(
                  color: Colors.white.withValues(alpha: 0.88),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        AppCard(
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
          child: Row(
            children: [
              Expanded(
                child: StatBlock(
                  value: topDistance.toStringAsFixed(2),
                  unit: 'KM',
                  label: 'Top distance',
                ),
              ),
              const StatDivider(),
              Expanded(
                child: StatBlock(
                  value: _leaders.length.toString(),
                  label: 'Players',
                ),
              ),
              const StatDivider(),
              Expanded(
                child: topArea > 0
                    ? StatBlock(
                        value: area.value,
                        unit: area.unit,
                        label: 'Top territory',
                        accent: true,
                      )
                    : StatBlock(
                        value: '${top['total_runs'] ?? 0}',
                        label: 'Top runs',
                        accent: true,
                      ),
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
              leading: const IconCircleButton(icon: Icons.emoji_events_outlined),
              trailing: IconCircleButton(
                icon: Icons.refresh_rounded,
                onTap: _loadLeaderboard,
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _loadLeaderboard,
                color: AppColors.pink,
                backgroundColor: AppColors.surfaceHigh,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
                  child: _buildContent(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
