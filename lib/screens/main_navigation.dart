import 'package:flutter/material.dart';
import '../services/location_service.dart';
import '../theme/app_theme.dart';
import 'home_page.dart';
import 'run_page.dart';
import 'map_page.dart';
import 'leaderboard_page.dart';
import 'profile_page.dart';

class MainNavigation extends StatefulWidget {
  const MainNavigation({super.key});

  @override
  State<MainNavigation> createState() => _MainNavigationState();
}

class _MainNavigationState extends State<MainNavigation> {
  int selectedIndex = 0;

  // Index 2 is the Run tab. It is built once and then kept alive, so a run
  // keeps recording while the user looks at another tab.
  final List<Widget> pages = const [
    HomePage(),
    MapPage(),
    SizedBox.shrink(),
    LeaderboardPage(),
    ProfilePage(),
  ];

  final Widget _runPage = const RunPage();
  bool _runVisited = false;

  @override
  void initState() {
    super.initState();
    LocationService.startPassive();
  }

  @override
  void dispose() {
    LocationService.stopPassive();
    super.dispose();
  }

  void onItemTapped(int index) {
    setState(() {
      selectedIndex = index;
      if (index == 2) _runVisited = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          pages[selectedIndex],
          if (_runVisited)
            Offstage(
              key: const ValueKey('run-tab'),
              offstage: selectedIndex != 2,
              child: _runPage,
            ),
        ],
      ),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: AppColors.bg,
          border: Border(top: BorderSide(color: AppColors.border)),
        ),
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(8, 8, 8, 6),
            child: Row(
              children: [
                navItem(Icons.home_outlined, Icons.home_rounded, 'Home', 0),
                navItem(Icons.map_outlined, Icons.map_rounded, 'Map', 1),
                runItem(),
                navItem(
                  Icons.emoji_events_outlined,
                  Icons.emoji_events_rounded,
                  'Ranks',
                  3,
                ),
                navItem(
                  Icons.person_outline_rounded,
                  Icons.person_rounded,
                  'Profile',
                  4,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget navItem(IconData icon, IconData activeIcon, String label, int index) {
    final bool isSelected = selectedIndex == index;
    final color = isSelected ? AppColors.pink : AppColors.textMuted;

    return Expanded(
      child: GestureDetector(
        onTap: () => onItemTapped(index),
        behavior: HitTestBehavior.opaque,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(isSelected ? activeIcon : icon, size: 24, color: color),
              const SizedBox(height: 4),
              Text(
                label,
                style: AppText.caption.copyWith(
                  fontSize: 10,
                  color: color,
                  fontWeight: isSelected ? FontWeight.w700 : FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget runItem() {
    final bool isSelected = selectedIndex == 2;

    return Expanded(
      child: GestureDetector(
        onTap: () => onItemTapped(2),
        behavior: HitTestBehavior.opaque,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  gradient: AppColors.brandGradient,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.magenta
                          .withValues(alpha: isSelected ? 0.5 : 0.28),
                      blurRadius: isSelected ? 20 : 12,
                      offset: const Offset(0, 5),
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.directions_run_rounded,
                  color: Colors.white,
                  size: 24,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                'Run',
                style: AppText.caption.copyWith(
                  fontSize: 10,
                  color: isSelected ? AppColors.pink : AppColors.textMuted,
                  fontWeight: isSelected ? FontWeight.w700 : FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
