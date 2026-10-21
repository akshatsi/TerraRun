import 'package:flutter/material.dart';
import '../services/stats_service.dart';
import '../services/auth_service.dart';
import '../services/social_service.dart';
import '../services/territory_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';
import 'friends_page.dart';
import 'run_detail_page.dart';
import 'runner_profile_page.dart';

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

  bool _feedLoading = true;
  String? _feedError;
  List<Map<String, dynamic>> _feed = [];

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
    _loadFeed();

    if (!mounted) return;

    if (result['success'] == true) {
      final data = result['data'] as Map<String, dynamic>;

      double terrArea = 0.0;
      if (terrResult['success'] == true) {
        final terrData = terrResult['data'] as Map<String, dynamic>;
        terrArea = ((terrData['area_sq_m'] ?? 0) as num).toDouble();
      }

      setState(() {
        _userName = (userName == null || userName.isEmpty)
            ? 'Runner'
            : userName;
        _totalDistanceKm = (data['total_distance_km'] ?? 0).toDouble();
        _totalRuns = (data['total_runs'] ?? 0) as int;
        _avgSpeed = (data['avg_speed'] ?? 0).toDouble();
        _territoryArea = terrArea;
        _isLoading = false;
      });
    } else {
      setState(() {
        _userName = (userName == null || userName.isEmpty)
            ? 'Runner'
            : userName;
        _error = result['message']?.toString() ?? 'Failed to load stats';
        _isLoading = false;
      });
    }
  }

  Future<void> _loadFeed() async {
    final result = await SocialService.feed(limit: 5);
    if (!mounted) return;

    setState(() {
      _feedLoading = false;
      if (result['success'] == true && result['data'] is List) {
        _feed = (result['data'] as List)
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .take(5)
            .toList();
        _feedError = null;
      } else {
        _feedError = result['message']?.toString() ?? 'Failed to load activity';
      }
    });
  }

  Future<void> _openSearch() async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const FriendsPage(focusSearch: true)),
    );
    if (mounted) _loadFeed();
  }

  Future<void> _openFriends() async {
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const FriendsPage()));
    if (mounted) _loadFeed();
  }

  Future<void> _openRunner(Map<String, dynamic> user) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => RunnerProfilePage(
          userId: (user['id'] as num).toInt(),
          name: user['name']?.toString() ?? '',
        ),
      ),
    );
    if (mounted) _loadFeed();
  }

  Future<void> _openRun(int id) async {
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => RunDetailPage(runId: id)));
  }

  Widget _buildFeedTile(Map<String, dynamic> item) {
    final user = Map<String, dynamic>.from((item['user'] ?? {}) as Map);
    final name = user['name']?.toString() ?? 'Runner';
    final first = name.split(' ').first;

    return Column(
      children: [
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: item['run_id'] == null
              ? (user['id'] == null ? null : () => _openRunner(user))
              : () => _openRun((item['run_id'] as num).toInt()),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: Row(
              children: [
                Avatar(name: name, size: 40),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '$first ran',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppText.body.copyWith(
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        Fmt.runSummary(item),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: AppText.bodySecondary,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  Fmt.timeAgoFrom(item['created_at']?.toString()),
                  style: AppText.caption,
                ),
              ],
            ),
          ),
        ),
        const AppDivider(),
      ],
    );
  }

  Widget _buildFeed() {
    if (_feedLoading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 16),
        child: Center(child: AppLoader()),
      );
    }
    if (_feedError != null) {
      return ErrorBanner(_feedError!);
    }
    if (_feed.isEmpty) {
      return AppCard(
        child: Column(
          children: [
            const Icon(
              Icons.people_outline_rounded,
              color: AppColors.textMuted,
              size: 28,
            ),
            const SizedBox(height: 10),
            Text(
              'Follow runners to see their runs here',
              textAlign: TextAlign.center,
              style: AppText.body,
            ),
            const SizedBox(height: 14),
            SecondaryButton(
              label: 'Find runners',
              icon: Icons.person_add_alt_1_rounded,
              height: 44,
              onPressed: _openFriends,
            ),
          ],
        ),
      );
    }
    return Column(children: _feed.map(_buildFeedTile).toList());
  }

  Widget _buildHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 6),
      child: Row(
        children: [
          Avatar(name: _userName, size: 44),
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
          AppIconButton(icon: Icons.search_rounded, onTap: _openSearch),
          const SizedBox(width: 8),
          AppIconButton(icon: Icons.refresh_rounded, onTap: _loadHomeData),
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

    return AppCard(
      padding: const EdgeInsets.all(20),
      child: SizedBox(
        width: double.infinity,
        child: _isLoading
            ? const SizedBox(height: 96, child: Center(child: AppLoader()))
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('YOUR TERRITORY', style: AppText.overline),
                  const SizedBox(height: 14),
                  if (hasArea)
                    Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: area.value,
                            style: AppText.stat(
                              44,
                              weight: FontWeight.w600,
                              color: AppColors.signature,
                            ),
                          ),
                          TextSpan(
                            text: ' ${area.unit.toLowerCase()}',
                            style: AppText.unit(18),
                          ),
                        ],
                      ),
                    )
                  else
                    Text(heroText, style: AppText.headline),
                  const SizedBox(height: 10),
                  Text(heroSubtext, style: AppText.bodySecondary),
                ],
              ),
      ),
    );
  }

  Widget _buildStatsCard() {
    return AppCard(
      child: StatRow(
        children: [
          StatBlock(
            value: _isLoading ? '--' : _totalDistanceKm.toStringAsFixed(2),
            unit: 'km',
            label: 'Distance',
          ),
          StatBlock(
            value: _isLoading ? '--' : _totalRuns.toString(),
            label: 'Runs',
          ),
          StatBlock(
            value: _isLoading ? '--' : _avgSpeed.toStringAsFixed(1),
            unit: 'km/h',
            label: 'Avg speed',
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Secure Main Loop', style: AppText.headline),
              ),
              Text('$runsDone/5 RUNS', style: AppText.overline),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            _totalRuns == 0
                ? 'Complete your first run to activate your mission.'
                : 'Keep running to improve your total distance and control.',
            style: AppText.bodySecondary,
          ),
          const SizedBox(height: 14),
          AppProgressBar(value: missionProgress),
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
                color: AppColors.text,
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
                      const SizedBox(height: 12),
                      _buildStatsCard(),
                      const SizedBox(height: 26),
                      const SectionTitle('Today’s mission'),
                      const SizedBox(height: 12),
                      _buildMission(),
                      const SizedBox(height: 26),
                      SectionTitle(
                        'Friends’ activity',
                        trailing: AppIconButton(
                          icon: Icons.group_rounded,
                          size: 36,
                          onTap: _openFriends,
                        ),
                      ),
                      const SizedBox(height: 12),
                      _buildFeed(),
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
