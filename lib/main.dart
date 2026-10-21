import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
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
    // ShadApp.custom hosts a MaterialApp, so shadcn components and the Material
    // widgets that have no shadcn version (maps, pull to refresh, page views)
    // share one dark theme.
    return ShadApp.custom(
      themeMode: ThemeMode.dark,
      darkTheme: AppShadTheme.dark(),
      appBuilder: (context) {
        return MaterialApp(
          title: 'TerraRun',
          debugShowCheckedModeBanner: false,
          theme: AppTheme.dark(),
          localizationsDelegates: const [GlobalShadLocalizations.delegate],
          builder: (context, child) => ShadAppBuilder(child: child!),
          home: const AppStartPage(),
        );
      },
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
          children: [Wordmark(size: 22), SizedBox(height: 28), AppLoader()],
        ),
      ),
    );
  }
}
