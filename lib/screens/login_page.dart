import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'login_form_page.dart';
import 'signup_page.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final PageController _pageController = PageController();
  Timer? _timer;
  int currentIndex = 0;

  static const List<OnboardingData> pages = [
    OnboardingData(
      headline: 'Own your streets.',
      subtitle: 'Run a loop and the ground inside it becomes yours.',
      backgroundImage: 'assets/onboarding/bg1.jpg',
    ),
    OnboardingData(
      headline: 'Close loops that never run out.',
      subtitle: 'Every route you close adds to your territory.',
      backgroundImage: 'assets/onboarding/bg2.jpg',
    ),
    OnboardingData(
      headline: 'Get motivation from your people.',
      subtitle: 'Climb the leaderboard and watch rivals chase your streets.',
      backgroundImage: 'assets/onboarding/bg3.jpg',
    ),
    OnboardingData(
      headline: 'Run your world.',
      subtitle: 'Your crew against the world.',
      backgroundImage: 'assets/onboarding/bg4.jpg',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _startAutoScroll();
  }

  void _startAutoScroll() {
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(milliseconds: 4500), (_) {
      if (!_pageController.hasClients) return;

      final nextIndex = (currentIndex + 1) % pages.length;
      _pageController.animateToPage(
        nextIndex,
        duration: const Duration(milliseconds: 700),
        curve: Curves.easeInOutCubic,
      );
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final imageHeight = media.size.height * 0.58;
    final controlsHeight = 176 + media.padding.bottom;

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Stack(
        children: [
          PageView.builder(
            controller: _pageController,
            itemCount: pages.length,
            onPageChanged: (index) {
              setState(() {
                currentIndex = index;
              });
            },
            itemBuilder: (context, index) {
              return _Slide(
                data: pages[index],
                imageHeight: imageHeight,
                bottomInset: controlsHeight,
              );
            },
          ),
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: SafeArea(
              bottom: false,
              child: const Padding(
                padding: EdgeInsets.only(top: 20),
                child: Center(child: Wordmark(size: 15)),
              ),
            ),
          ),
          Positioned(
            left: 24,
            right: 24,
            bottom: 0,
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.only(bottom: 18),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: List.generate(
                        pages.length,
                        (dotIndex) => AnimatedContainer(
                          duration: const Duration(milliseconds: 260),
                          margin: const EdgeInsets.symmetric(horizontal: 3),
                          width: currentIndex == dotIndex ? 20 : 8,
                          height: 4,
                          decoration: BoxDecoration(
                            color: currentIndex == dotIndex
                                ? AppColors.text
                                : AppColors.line,
                            borderRadius: BorderRadius.circular(4),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 22),
                    PrimaryButton(
                      label: 'Join for free',
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => const SignupPage()),
                        );
                      },
                    ),
                    const SizedBox(height: 8),
                    ShadButton.ghost(
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => const LoginFormPage(),
                          ),
                        );
                      },
                      foregroundColor: AppColors.textSecondary,
                      textStyle: AppText.button.copyWith(
                        fontWeight: FontWeight.w500,
                      ),
                      child: const Text('Log in'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class OnboardingData {
  final String headline;
  final String subtitle;
  final String backgroundImage;

  const OnboardingData({
    required this.headline,
    required this.subtitle,
    required this.backgroundImage,
  });
}

class _Slide extends StatelessWidget {
  final OnboardingData data;
  final double imageHeight;
  final double bottomInset;

  const _Slide({
    required this.data,
    required this.imageHeight,
    required this.bottomInset,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          height: imageHeight,
          child: Stack(
            fit: StackFit.expand,
            children: [
              Image.asset(
                data.backgroundImage,
                fit: BoxFit.cover,
                alignment: Alignment.topCenter,
                errorBuilder: (context, error, stackTrace) {
                  return Container(color: AppColors.surface);
                },
              ),
              // Plain dark scrim so the photo stays legible.
              ColoredBox(color: AppColors.bg.withValues(alpha: 0.5)),
            ],
          ),
        ),
        Positioned(
          left: 24,
          right: 24,
          bottom: bottomInset,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(data.headline, style: AppText.display),
              const SizedBox(height: 12),
              Text(
                data.subtitle,
                style: AppText.bodySecondary.copyWith(fontSize: 15),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
