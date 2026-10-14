import 'package:flutter/material.dart';
import 'screens/login_page.dart';
import 'screens/main_navigation.dart';
import 'services/auth_service.dart';
import 'theme/app_theme.dart';
import 'widgets/app_widgets.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TerraRun',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark(),
      home: const AppStartPage(),
    );
  }
}

class AppStartPage extends StatefulWidget {
  const AppStartPage({super.key});

  @override
  State<AppStartPage> createState() => _AppStartPageState();
}

class _AppStartPageState extends State<AppStartPage> {
  @override
  void initState() {
    super.initState();
    _checkLogin();
  }

  Future<void> _checkLogin() async {
    final loggedIn = await AuthService.isLoggedIn();

    if (!mounted) return;

    if (loggedIn) {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const MainNavigation()),
      );
    } else {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const LoginPage()),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: AppColors.bg,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Wordmark(size: 22),
            SizedBox(height: 28),
            AppLoader(),
          ],
        ),
      ),
    );
  }
}
