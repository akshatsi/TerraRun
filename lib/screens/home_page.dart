import 'package:flutter/material.dart';
import '../services/stats_service.dart';
import '../services/auth_service.dart';
import '../services/territory_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  bool _isLoading = true;
  String? _error;

  double _totalDistanceKm = 0.0;
  int _totalRuns = 0;
  double _avgSpeed = 0.0;
  String _userName = 'Runner';
  double _territoryArea = 0.0;

  @override
  void initState() {
    super.initState();
    _loadHomeData();
  }

  Future<void> _loadHomeData() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final userName = await AuthService.getUserName();
    final result = await StatsService.getProfileStats();

    // Fetch territory area
    final terrResult = await TerritoryService.getMyTerritory();

    if (!mounted) return;

    if (result['success'] == true) {
      final data = result['data'] as Map<String, dynamic>;

      double terrArea = 0.0;
      if (terrResult['success'] == true) {
        final terrData = terrResult['data'] as Map<String, dynamic>;
        terrArea = ((terrData['area_sq_m'] ?? 0) as num).toDouble();
      }

      setState(() {
        _userName = (userName == null || userName.isEmpty) ? 'Runner' : userName;
        _totalDistanceKm = (data['total_distance_km'] ?? 0).toDouble();
        _totalRuns = (data['total_runs'] ?? 0) as int;
        _avgSpeed = (data['avg_speed'] ?? 0).toDouble();
        _territoryArea = terrArea;
        _isLoading = false;
      });
    } else {
      setState(() {
        _userName = (userName == null || userName.isEmpty) ? 'Runner' : userName;
        _error = result['message']?.toString() ?? 'Failed to load stats';
        _isLoading = false;
      });
    }
  }

  Widget buildActivityTile({
    required IconData icon,
    required Color color,
    required String title,
    required String subtitle,
    required String trailing,
  }) {
    return AppCard(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.16),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(icon, color: color, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: AppText.subtitle),
                const SizedBox(height: 3),
                Text(subtitle, style: AppText.bodySecondary),
              ],
            ),
          ),
          Text(trailing, style: AppText.overline),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    final initial = _userName.isNotEmpty ? _userName[0].toUpperCase() : 'R';

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 6),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            alignment: Alignment.center,
            decoration: const BoxDecoration(
              gradient: AppColors.brandGradient,
              shape: BoxShape.circle,
            ),
            child: Text(initial, style: AppText.stat(18)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Welcome back', style: AppText.caption),
                const SizedBox(height: 3),
                Text(
                  _userName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.title,
                ),
              ],
            ),
          ),
          IconCircleButton(
            icon: Icons.refresh_rounded,
            onTap: _loadHomeData,
          ),
        ],
      ),
    );
  }

  Widget _buildHero() {
    final hasArea = _totalRuns > 0 && _territoryArea > 0;
    final area = Fmt.area(_territoryArea);

    final heroText = _totalRuns == 0
        ? 'Start your first run today'
        : _territoryArea > 0
            ? ''
            : '$_totalRuns runs completed';

    final heroSubtext = _totalRuns == 0
        ? 'Complete your first run to start building your zone.'
        : _territoryArea > 0
            ? 'You covered ${_totalDistanceKm.toStringAsFixed(2)} km and claimed territory.'
            : 'You covered ${_totalDistanceKm.toStringAsFixed(2)} km overall.';

    return HeroCard(
      padding: const EdgeInsets.fromLTRB(22, 22, 22, 24),
      child: _isLoading
          ? const SizedBox(
              height: 96,
              child: Center(
                child: SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    color: Colors.white,
                    strokeWidth: 2.4,
                  ),
                ),
              ),
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'YOUR TERRITORY',
                  style: AppText.overline.copyWith(
                    color: Colors.white.withValues(alpha: 0.75),
                  ),
                ),
                const SizedBox(height: 14),
                if (hasArea)
                  Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(text: area.value, style: AppText.stat(48)),
                        TextSpan(
                          text: ' ${area.unit}',
                          style: AppText.stat(
                            20,
                            weight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  )
                else
                  Text(heroText, style: AppText.headline),
                const SizedBox(height: 10),
                Text(
                  heroSubtext,
                  style: AppText.body.copyWith(
                    color: Colors.white.withValues(alpha: 0.88),
                  ),
                ),
              ],
            ),
    );
  }

  Widget _buildStatsCard() {
    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
      child: Row(
        children: [
          Expanded(
            child: StatBlock(
              value: _isLoading ? '--' : _totalDistanceKm.toStringAsFixed(2),
              unit: 'KM',
              label: 'Distance',
            ),
          ),
          const StatDivider(),
          Expanded(
            child: StatBlock(
              value: _isLoading ? '--' : _totalRuns.toString(),
              label: 'Runs',
            ),
          ),
          const StatDivider(),
          Expanded(
            child: StatBlock(
              value: _isLoading ? '--' : _avgSpeed.toStringAsFixed(1),
              unit: 'KM/H',
              label: 'Avg speed',
              accent: true,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMission() {
    final missionProgress = _totalRuns == 0
        ? 0.0
        : _totalRuns >= 5
            ? 1.0
            : _totalRuns / 5.0;
    final runsDone = _totalRuns >= 5 ? 5 : _totalRuns;

    return AppCard(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: AppColors.pink.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(11),
                ),
                child: const Icon(
                  Icons.flag_rounded,
                  color: AppColors.pink,
                  size: 18,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(child: Text('Secure Main Loop', style: AppText.subtitle)),
              Text('$runsDone/5 RUNS', style: AppText.overline),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            _totalRuns == 0
                ? 'Complete your first run to activate your mission.'
                : 'Keep running to improve your total distance and control.',
            style: AppText.bodySecondary,
          ),
          const SizedBox(height: 14),
          GradientProgressBar(value: missionProgress),
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
            _buildHeader(),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _loadHomeData,
                color: AppColors.pink,
                backgroundColor: AppColors.surfaceHigh,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (_error != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 14),
                          child: ErrorBanner(_error!),
                        ),
                      _buildHero(),
                      const SizedBox(height: 14),
                      _buildStatsCard(),
                      const SizedBox(height: 26),
                      const SectionTitle('Today’s mission'),
                      const SizedBox(height: 12),
                      _buildMission(),
                      const SizedBox(height: 26),
                      const SectionTitle('Recent activity'),
                      const SizedBox(height: 12),
                      buildActivityTile(
                        icon: Icons.route_rounded,
                        color: AppColors.pink,
                        title: 'Total distance',
                        subtitle:
                            '${_totalDistanceKm.toStringAsFixed(2)} km covered so far',
                        trailing: 'LIVE',
                      ),
                      buildActivityTile(
                        icon: Icons.directions_run_rounded,
                        color: AppColors.purple,
                        title: 'Runs completed',
                        subtitle: 'You have finished $_totalRuns runs',
                        trailing: 'NOW',
                      ),
                      buildActivityTile(
                        icon: Icons.speed_rounded,
                        color: AppColors.gold,
                        title: 'Average speed',
                        subtitle:
                            'Current average speed is ${_avgSpeed.toStringAsFixed(1)} km/h',
                        trailing: 'STATS',
                      ),
                    ],
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
