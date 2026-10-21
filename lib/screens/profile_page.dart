import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';
import 'edit_profile_page.dart';
import '../services/auth_service.dart';
import '../services/social_service.dart';
import '../services/stats_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';
import '../widgets/run_history_tile.dart';
import 'login_page.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  static const _monthNames = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ];

  static const _weekdayInitials = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

  bool _isLoading = true;
  String? _error;

  String _userName = 'Runner';
  String? _userEmail;
  String _bio = '';
  int? _followers;
  int? _following;
  double _territorySqM = 0.0;

  double _totalDistanceKm = 0.0;
  int _totalRuns = 0;
  double _avgSpeed = 0.0;

  Map<String, int> _runsPerDay = {};
  List<dynamic> _runs = [];
  List<double> _weeklyDistances = List.filled(7, 0.0);

  @override
  void initState() {
    super.initState();
    _loadProfileData();
  }

  Future<void> _loadProfileData() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final userName = await AuthService.getUserName();
    final userEmail = await AuthService.getUserEmail();
    final statsResult = await StatsService.getProfileStats();
    final runsResult = await StatsService.getAllRuns();
    final cardResult = await SocialService.getMyCard();

    if (!mounted) return;

    final card = cardResult['success'] == true && cardResult['data'] is Map
        ? cardResult['data'] as Map
        : null;
    final cardName = card?['name']?.toString();

    final name = (cardName != null && cardName.isNotEmpty)
        ? cardName
        : (userName == null || userName.isEmpty)
        ? 'Runner'
        : userName;

    if (statsResult['success'] == true && runsResult['success'] == true) {
      final stats = statsResult['data'] as Map<String, dynamic>;
      final runs = runsResult['data'] as List<dynamic>;

      final Map<String, int> runsPerDay = {};
      final List<double> weeklyDistances = List.filled(7, 0.0);

      final now = DateTime.now();

      for (final run in runs) {
        final createdAtString = run['created_at']?.toString();
        if (createdAtString == null) continue;

        DateTime? createdAt;
        try {
          createdAt = DateTime.parse(createdAtString).toLocal();
        } catch (_) {
          createdAt = null;
        }

        if (createdAt == null) continue;

        final dateKey = Fmt.dateKey(createdAt);

        runsPerDay[dateKey] = (runsPerDay[dateKey] ?? 0) + 1;

        final difference = now
            .difference(
              DateTime(createdAt.year, createdAt.month, createdAt.day),
            )
            .inDays;

        if (difference >= 0 && difference < 7) {
          final index = 6 - difference;
          weeklyDistances[index] += ((run['distance_km'] ?? 0) as num)
              .toDouble();
        }
      }

      setState(() {
        _userName = name;
        _userEmail = userEmail;
        _bio = card?['bio']?.toString() ?? '';
        _followers = (card?['followers_count'] as num?)?.toInt();
        _following = (card?['following_count'] as num?)?.toInt();
        _territorySqM =
            ((card?['territory_area_sq_m'] ?? stats['territory_area_sq_m'] ?? 0)
                    as num)
                .toDouble();
        _totalDistanceKm = (stats['total_distance_km'] ?? 0).toDouble();
        _totalRuns = (stats['total_runs'] ?? 0) as int;
        _avgSpeed = (stats['avg_speed'] ?? 0).toDouble();
        _runsPerDay = runsPerDay;
        _runs = runs;
        _weeklyDistances = weeklyDistances;
        _isLoading = false;
      });
    } else {
      setState(() {
        _userName = name;
        _userEmail = userEmail;
        _error =
            statsResult['message']?.toString() ??
            runsResult['message']?.toString() ??
            'Failed to load profile data';
        _isLoading = false;
      });
    }
  }

  Widget _buildIdentity() {
    return Row(
      children: [
        Avatar(name: _userName, size: 64),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _userName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: AppText.title,
              ),
              if (_userEmail != null && _userEmail!.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  _userEmail!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.bodySecondary,
                ),
              ],
              if (_followers != null && _following != null) ...[
                const SizedBox(height: 6),
                Text(
                  '$_followers ${_followers == 1 ? 'follower' : 'followers'}'
                  ' · $_following following',
                  style: AppText.label,
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Future<void> _editProfile() async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => EditProfilePage(name: _userName, bio: _bio),
      ),
    );
    if (saved == true && mounted) _loadProfileData();
  }

  Future<void> _shareProfile() async {
    final text = Fmt.shareText(
      name: _userName,
      distanceKm: _totalDistanceKm,
      territorySqM: _territorySqM,
    );
    await SharePlus.instance.share(ShareParams(text: text));
  }

  Widget _buildActions() {
    return Row(
      children: [
        Expanded(
          child: SecondaryButton(
            label: 'Edit profile',
            height: 44,
            onPressed: _editProfile,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: SecondaryButton(
            label: 'Share profile',
            height: 44,
            onPressed: _shareProfile,
          ),
        ),
      ],
    );
  }

  Widget _buildStatsCard() {
    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      child: StatRow(
        children: [
          StatBlock(
            value: _totalDistanceKm.toStringAsFixed(2),
            unit: 'km',
            label: 'Distance',
          ),
          StatBlock(value: _totalRuns.toString(), label: 'Runs'),
          StatBlock(
            value: _avgSpeed.toStringAsFixed(1),
            unit: 'km/h',
            label: 'Avg speed',
          ),
        ],
      ),
    );
  }

  Widget _buildWeeklyChart() {
    final now = DateTime.now();

    // Oldest day first, today last.
    final labels = List.generate(7, (i) {
      final day = now.subtract(Duration(days: 6 - i));
      return i == 6 ? 'Today' : _weekdayInitials[day.weekday - 1];
    });

    return AppCard(
      padding: const EdgeInsets.fromLTRB(8, 18, 8, 14),
      child: Column(
        children: [
          SizedBox(
            height: 120,
            child: CustomPaint(
              size: Size.infinite,
              painter: ProgressGraphPainter(_weeklyDistances),
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              for (int i = 0; i < labels.length; i++)
                Expanded(
                  child: Center(
                    child: Text(
                      labels[i],
                      maxLines: 1,
                      style: AppText.caption.copyWith(
                        color: i == 6 ? AppColors.text : AppColors.textMuted,
                        fontWeight: i == 6 ? FontWeight.w500 : FontWeight.w400,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget buildCalendarDay(int day, String dateKey) {
    final hasRun = _runsPerDay.containsKey(dateKey);
    final isToday = dateKey == Fmt.dateKey(DateTime.now());

    return Container(
      width: 36,
      height: 36,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: hasRun ? AppColors.text : Colors.transparent,
        borderRadius: BorderRadius.circular(AppRadius.chip),
        border: isToday && !hasRun
            ? Border.all(color: AppColors.textSecondary)
            : null,
      ),
      child: Text(
        '$day',
        style: AppText.caption.copyWith(
          color: hasRun
              ? AppColors.onLight
              : isToday
              ? AppColors.text
              : AppColors.textSecondary,
          fontWeight: hasRun || isToday ? FontWeight.w500 : FontWeight.w400,
        ),
      ),
    );
  }

  Widget _buildCalendar() {
    final now = DateTime.now();
    final daysInMonth = DateTime(now.year, now.month + 1, 0).day;
    // DateTime.weekday: Monday = 1, so Monday-first needs weekday - 1 blanks.
    final leadingBlanks = DateTime(now.year, now.month, 1).weekday - 1;
    final cellCount = ((leadingBlanks + daysInMonth + 6) ~/ 7) * 7;

    final cells = List<Widget>.generate(cellCount, (i) {
      final day = i - leadingBlanks + 1;
      if (day < 1 || day > daysInMonth) {
        return const SizedBox(width: 36, height: 36);
      }
      return buildCalendarDay(
        day,
        Fmt.dateKey(DateTime(now.year, now.month, day)),
      );
    });

    return AppCard(
      padding: const EdgeInsets.fromLTRB(14, 16, 14, 8),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              for (final d in _weekdayInitials)
                SizedBox(
                  width: 36,
                  child: Center(child: Text(d, style: AppText.overline)),
                ),
            ],
          ),
          const SizedBox(height: 12),
          for (int row = 0; row < cellCount ~/ 7; row++)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: cells.sublist(row * 7, row * 7 + 7),
              ),
            ),
        ],
      ),
    );
  }

  Widget buildProgressView(BuildContext context) {
    final now = DateTime.now();

    return RefreshIndicator(
      onRefresh: _loadProfileData,
      color: AppColors.text,
      backgroundColor: AppColors.surfaceHigh,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildIdentity(),
            if (_bio.isNotEmpty) ...[
              const SizedBox(height: 14),
              Text(_bio, style: AppText.body),
            ],
            const SizedBox(height: 18),
            _buildActions(),
            const SizedBox(height: 24),
            if (_isLoading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 40),
                child: Center(child: AppLoader(size: 28)),
              )
            else if (_error != null)
              ErrorBanner(_error!)
            else ...[
              _buildStatsCard(),
              const SizedBox(height: 26),
              const SectionTitle('Past 7 days'),
              const SizedBox(height: 12),
              _buildWeeklyChart(),
              const SizedBox(height: 26),
              SectionTitle(
                '${_monthNames[now.month - 1]} ${now.year}',
                trailing: Text('RUN DAYS', style: AppText.overline),
              ),
              const SizedBox(height: 12),
              _buildCalendar(),
            ],
            const SizedBox(height: 26),
            if (!_isLoading && _error == null) ...[
              const SectionTitle('Run history'),
              const SizedBox(height: 4),
              if (_runs.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  child: Text('No runs yet.', style: AppText.bodySecondary),
                )
              else
                for (final run in _runs) RunHistoryTile(run: run),
              const SizedBox(height: 26),
            ],
            MenuTile(
              icon: Icons.logout_rounded,
              title: 'Log out',
              danger: true,
              onTap: () async {
                await AuthService.logout();

                if (!context.mounted) return;

                Navigator.pushAndRemoveUntil(
                  context,
                  MaterialPageRoute(builder: (_) => const LoginPage()),
                  (route) => false,
                );
              },
            ),
            const AppDivider(),
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
            ScreenHeader(
              title: 'Profile',
              leading: const AppIconButton(icon: Icons.person_outline_rounded),
              trailing: AppIconButton(
                icon: Icons.refresh_rounded,
                onTap: _loadProfileData,
              ),
            ),
            Expanded(child: buildProgressView(context)),
          ],
        ),
      ),
    );
  }
}

/// Bar chart of distance per day.
class ProgressGraphPainter extends CustomPainter {
  final List<double> weeklyDistances;

  ProgressGraphPainter(this.weeklyDistances);

  @override
  void paint(Canvas canvas, Size size) {
    if (weeklyDistances.isEmpty) return;

    final maxRaw = weeklyDistances.reduce((a, b) => a > b ? a : b);
    final maxValue = maxRaw == 0 ? 1.0 : maxRaw;

    // One bar per day, centred in its column so labels line up.
    final slot = size.width / weeklyDistances.length;
    final barWidth = slot * 0.46;
    final last = weeklyDistances.length - 1;

    for (int i = 0; i < weeklyDistances.length; i++) {
      final height = (size.height * weeklyDistances[i] / maxValue).clamp(
        2.0,
        size.height,
      );
      final left = slot * (i + 0.5) - barWidth / 2;
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(left, size.height - height, barWidth, height),
          const Radius.circular(3),
        ),
        Paint()
          ..color = i == last
              ? AppColors.text
              : weeklyDistances[i] > 0
              ? AppColors.textSecondary
              : AppColors.line,
      );
    }
  }

  @override
  bool shouldRepaint(covariant ProgressGraphPainter oldDelegate) =>
      oldDelegate.weeklyDistances != weeklyDistances;
}
