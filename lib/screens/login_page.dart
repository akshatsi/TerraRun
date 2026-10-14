import 'dart:async';
import 'package:flutter/material.dart';
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
      headline: [
        HeadlineSpan('Own your '),
        HeadlineSpan('streets', emphasis: true, italic: true),
        HeadlineSpan('.'),
      ],
      subtitle: 'Run a loop and the ground inside it becomes yours.',
      backgroundImage: 'assets/onboarding/bg1.jpg',
    ),
    OnboardingData(
      headline: [
        HeadlineSpan('Close '),
        HeadlineSpan('loops', emphasis: true, italic: true),
        HeadlineSpan(' that never run out.'),
      ],
      subtitle: 'Every route you close adds to your territory.',
      backgroundImage: 'assets/onboarding/bg2.jpg',
    ),
    OnboardingData(
      headline: [
        HeadlineSpan('Get motivation from '),
        HeadlineSpan('your people', emphasis: true, italic: true),
        HeadlineSpan('.'),
      ],
      subtitle: 'Climb the leaderboard and watch rivals chase your streets.',
      backgroundImage: 'assets/onboarding/bg3.jpg',
    ),
    OnboardingData(
      headline: [
        HeadlineSpan('Run your '),
        HeadlineSpan('world', emphasis: true, italic: true),
        HeadlineSpan('.'),
      ],
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
    final imageHeight = media.size.height * 0.74;
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
                          width: currentIndex == dotIndex ? 22 : 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: currentIndex == dotIndex
                                ? AppColors.pink
                                : Colors.white.withValues(alpha: 0.25),
                            borderRadius: BorderRadius.circular(20),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 22),
                    GradientButton(
                      label: 'Join for free',
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => const SignupPage(),
                          ),
                        );
                      },
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => const LoginFormPage(),
                          ),
                        );
                      },
                      child: Text(
                        'Log in',
                        style: AppText.button.copyWith(
                          color: AppColors.textSecondary,
                        ),
                      ),
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
  final List<HeadlineSpan> headline;
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
              DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    stops: const [0.0, 0.45, 0.8, 1.0],
                    colors: [
                      AppColors.bg.withValues(alpha: 0.55),
                      AppColors.deepPurple.withValues(alpha: 0.28),
                      AppColors.bg.withValues(alpha: 0.9),
                      AppColors.bg,
                    ],
                  ),
                ),
              ),
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
              Headline(data.headline, style: AppText.display),
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
