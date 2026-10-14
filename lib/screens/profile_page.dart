import 'package:flutter/material.dart';
import 'location_test_page.dart';
import 'run_history_page.dart';
import '../services/auth_service.dart';
import '../services/stats_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';
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

  double _totalDistanceKm = 0.0;
  int _totalRuns = 0;
  double _avgSpeed = 0.0;

  Map<String, int> _runsPerDay = {};
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

    if (!mounted) return;

    final name = (userName == null || userName.isEmpty) ? 'Runner' : userName;

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

        final difference = now.difference(
          DateTime(createdAt.year, createdAt.month, createdAt.day),
        ).inDays;

        if (difference >= 0 && difference < 7) {
          final index = 6 - difference;
          weeklyDistances[index] += ((run['distance_km'] ?? 0) as num).toDouble();
        }
      }

      setState(() {
        _userName = name;
        _userEmail = userEmail;
        _totalDistanceKm = (stats['total_distance_km'] ?? 0).toDouble();
        _totalRuns = (stats['total_runs'] ?? 0) as int;
        _avgSpeed = (stats['avg_speed'] ?? 0).toDouble();
        _runsPerDay = runsPerDay;
        _weeklyDistances = weeklyDistances;
        _isLoading = false;
      });
    } else {
      setState(() {
        _userName = name;
        _userEmail = userEmail;
        _error = statsResult['message']?.toString() ??
            runsResult['message']?.toString() ??
            'Failed to load profile data';
        _isLoading = false;
      });
    }
  }

  Widget _buildIdentity() {
    final initial = _userName.isNotEmpty ? _userName[0].toUpperCase() : 'R';

    return Row(
      children: [
        Container(
          width: 64,
          height: 64,
          alignment: Alignment.center,
          decoration: const BoxDecoration(
            gradient: AppColors.territoryGradient,
            shape: BoxShape.circle,
          ),
          child: Text(initial, style: AppText.stat(26)),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _userName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: AppText.headline,
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
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildStatsCard() {
    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
      child: Row(
        children: [
          Expanded(
            child: StatBlock(
              value: _totalDistanceKm.toStringAsFixed(2),
              unit: 'KM',
              label: 'Distance',
            ),
          ),
          const StatDivider(),
          Expanded(
            child: StatBlock(
              value: _totalRuns.toString(),
              label: 'Runs',
            ),
          ),
          const StatDivider(),
          Expanded(
            child: StatBlock(
              value: _avgSpeed.toStringAsFixed(1),
              unit: 'KM/H',
              label: 'Avg speed',
              accent: true,
            ),
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
                        fontSize: 10,
                        color: i == 6 ? AppColors.pink : AppColors.textMuted,
                        fontWeight: i == 6 ? FontWeight.w700 : FontWeight.w600,
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
        gradient: isToday || hasRun ? AppColors.brandGradient : null,
        shape: BoxShape.circle,
        border: Border.all(
          color: isToday
              ? Colors.white
              : hasRun
                  ? Colors.transparent
                  : AppColors.border,
          width: isToday ? 1.6 : 1,
        ),
      ),
      child: Text(
        '$day',
        style: AppText.caption.copyWith(
          fontSize: 12,
          color: isToday || hasRun ? Colors.white : AppColors.textSecondary,
          fontWeight: isToday ? FontWeight.w800 : FontWeight.w600,
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
      return buildCalendarDay(day, Fmt.dateKey(DateTime(now.year, now.month, day)));
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
      color: AppColors.pink,
      backgroundColor: AppColors.surfaceHigh,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildIdentity(),
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
            MenuTile(
              icon: Icons.history_rounded,
              title: 'Run history',
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const RunHistoryPage()),
                );
              },
            ),
            MenuTile(
              icon: Icons.location_on_rounded,
              title: 'Location access',
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const LocationTestPage()),
                );
              },
            ),
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
              leading: const IconCircleButton(icon: Icons.person_outline_rounded),
              trailing: IconCircleButton(
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

class ProgressGraphPainter extends CustomPainter {
  final List<double> weeklyDistances;

  ProgressGraphPainter(this.weeklyDistances);

  @override
  void paint(Canvas canvas, Size size) {
    if (weeklyDistances.isEmpty) return;

    final maxRaw = weeklyDistances.reduce((a, b) => a > b ? a : b);
    final maxValue = maxRaw == 0 ? 1.0 : maxRaw;

    // Faint guide lines.
    final guide = Paint()
      ..color = Colors.white.withValues(alpha: 0.08)
      ..strokeWidth = 1;
    for (int i = 0; i < 3; i++) {
      final y = size.height * (0.15 + i * 0.35);
      canvas.drawLine(Offset(0, y), Offset(size.width, y), guide);
    }

    // One point per day, centred in its column so labels line up.
    final slot = size.width / weeklyDistances.length;
    final List<Offset> points = [];

    for (int i = 0; i < weeklyDistances.length; i++) {
      final x = slot * (i + 0.5);
      final normalized = weeklyDistances[i] / maxValue;
      final y = size.height * (0.85 - (normalized * 0.65));
      points.add(Offset(x, y));
    }

    final line = Path()..moveTo(points.first.dx, points.first.dy);
    for (int i = 1; i < points.length; i++) {
      line.lineTo(points[i].dx, points[i].dy);
    }

    final fill = Path.from(line)
      ..lineTo(points.last.dx, size.height)
      ..lineTo(points.first.dx, size.height)
      ..close();

    canvas.drawPath(
      fill,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            AppColors.pink.withValues(alpha: 0.3),
            AppColors.pink.withValues(alpha: 0.0),
          ],
        ).createShader(Offset.zero & size),
    );

    canvas.drawPath(
      line,
      Paint()
        ..color = AppColors.pink
        ..strokeWidth = 2.5
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );

    final dotPaint = Paint()..color = AppColors.pink;
    for (int i = 0; i < points.length - 1; i++) {
      canvas.drawCircle(points[i], 3.5, dotPaint);
    }

    canvas.drawCircle(
      points.last,
      10,
      Paint()..color = AppColors.pink.withValues(alpha: 0.25),
    );
    canvas.drawCircle(points.last, 5.5, dotPaint);
  }

  @override
  bool shouldRepaint(covariant ProgressGraphPainter oldDelegate) =>
      oldDelegate.weeklyDistances != weeklyDistances;
}
