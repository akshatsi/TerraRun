// -----------------------------------------------
// TerraRun – Screen: Auth (Login / Register)
// -----------------------------------------------
// Tab‑based authentication screen with animated
// transitions. Dark‑themed with glowing accent
// input fields and gradient submit button.
// -----------------------------------------------

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/constants.dart';
import '../providers/auth_provider.dart';

class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({super.key});

  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  // Login form
  final _loginEmail = TextEditingController();
  final _loginPassword = TextEditingController();
  final _loginFormKey = GlobalKey<FormState>();

  // Register form
  final _regEmail = TextEditingController();
  final _regUsername = TextEditingController();
  final _regPassword = TextEditingController();
  final _regConfirm = TextEditingController();
  final _regFormKey = GlobalKey<FormState>();

  bool _obscureLogin = true;
  bool _obscureReg = true;
  bool _obscureConfirm = true;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    _loginEmail.dispose();
    _loginPassword.dispose();
    _regEmail.dispose();
    _regUsername.dispose();
    _regPassword.dispose();
    _regConfirm.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);

    // Show error snackbar
    ref.listen<AuthState>(authProvider, (prev, next) {
      if (next.error != null && next.error != prev?.error) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(next.error!),
            backgroundColor: AppColors.error,
          ),
        );
      }
    });

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24),
            child: Column(
              children: [
                const SizedBox(height: 40),
                // ── Logo / Title ──
                _buildLogo(),
                const SizedBox(height: 40),
                // ── Tab bar ──
                _buildTabBar(),
                const SizedBox(height: 24),
                // ── Tab content ──
                SizedBox(
                  height: 380,
                  child: TabBarView(
                    controller: _tabController,
                    children: [
                      _buildLoginForm(authState),
                      _buildRegisterForm(authState),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLogo() {
    return Column(
      children: [
        // Glowing icon
        Container(
          width: 72,
          height: 72,
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [AppColors.primary, AppColors.primaryLight],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: AppColors.primary.withValues(alpha: 0.4),
                blurRadius: 24,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: const Icon(
            Icons.terrain_rounded,
            size: 40,
            color: Colors.white,
          ),
        ),
        const SizedBox(height: 16),
        Text(
          'TerraRun',
          style: Theme.of(context).textTheme.displayMedium,
        ),
        const SizedBox(height: 6),
        Text(
          'Run more. Own the map.',
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: AppColors.textMuted,
              ),
        ),
      ],
    );
  }

  Widget _buildTabBar() {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(kButtonRadius),
      ),
      child: TabBar(
        controller: _tabController,
        indicator: BoxDecoration(
          color: AppColors.primary,
          borderRadius: BorderRadius.circular(kButtonRadius),
        ),
        indicatorSize: TabBarIndicatorSize.tab,
        labelColor: Colors.white,
        unselectedLabelColor: AppColors.textMuted,
        dividerColor: Colors.transparent,
        splashBorderRadius: BorderRadius.circular(kButtonRadius),
        tabs: const [
          Tab(text: 'Login'),
          Tab(text: 'Register'),
        ],
      ),
    );
  }

  Widget _buildLoginForm(AuthState authState) {
    return Form(
      key: _loginFormKey,
      child: Column(
        children: [
          TextFormField(
            controller: _loginEmail,
            keyboardType: TextInputType.emailAddress,
            decoration: const InputDecoration(
              labelText: 'Email',
              prefixIcon: Icon(Icons.email_outlined, size: 20),
            ),
            validator: (v) =>
                v == null || v.isEmpty ? 'Enter your email' : null,
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _loginPassword,
            obscureText: _obscureLogin,
            decoration: InputDecoration(
              labelText: 'Password',
              prefixIcon: const Icon(Icons.lock_outline, size: 20),
              suffixIcon: IconButton(
                icon: Icon(
                  _obscureLogin
                      ? Icons.visibility_off_outlined
                      : Icons.visibility_outlined,
                  size: 20,
                ),
                onPressed: () =>
                    setState(() => _obscureLogin = !_obscureLogin),
              ),
            ),
            validator: (v) =>
                v == null || v.isEmpty ? 'Enter your password' : null,
          ),
          const SizedBox(height: 28),
          SizedBox(
            width: double.infinity,
            height: 50,
            child: ElevatedButton(
              onPressed: authState.isLoading ? null : _doLogin,
              child: authState.isLoading
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Text('Sign In'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRegisterForm(AuthState authState) {
    return Form(
      key: _regFormKey,
      child: SingleChildScrollView(
        child: Column(
          children: [
            TextFormField(
              controller: _regUsername,
              decoration: const InputDecoration(
                labelText: 'Username',
                prefixIcon: Icon(Icons.person_outline, size: 20),
              ),
              validator: (v) =>
                  v == null || v.length < 3 ? 'Min 3 characters' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _regEmail,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'Email',
                prefixIcon: Icon(Icons.email_outlined, size: 20),
              ),
              validator: (v) =>
                  v == null || !v.contains('@') ? 'Enter a valid email' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _regPassword,
              obscureText: _obscureReg,
              decoration: InputDecoration(
                labelText: 'Password',
                prefixIcon: const Icon(Icons.lock_outline, size: 20),
                suffixIcon: IconButton(
                  icon: Icon(
                    _obscureReg
                        ? Icons.visibility_off_outlined
                        : Icons.visibility_outlined,
                    size: 20,
                  ),
                  onPressed: () =>
                      setState(() => _obscureReg = !_obscureReg),
                ),
              ),
              validator: (v) =>
                  v == null || v.length < 8 ? 'Min 8 characters' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _regConfirm,
              obscureText: _obscureConfirm,
              decoration: InputDecoration(
                labelText: 'Confirm Password',
                prefixIcon: const Icon(Icons.lock_outline, size: 20),
                suffixIcon: IconButton(
                  icon: Icon(
                    _obscureConfirm
                        ? Icons.visibility_off_outlined
                        : Icons.visibility_outlined,
                    size: 20,
                  ),
                  onPressed: () =>
                      setState(() => _obscureConfirm = !_obscureConfirm),
                ),
              ),
              validator: (v) =>
                  v != _regPassword.text ? 'Passwords do not match' : null,
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              height: 50,
              child: ElevatedButton(
                onPressed: authState.isLoading ? null : _doRegister,
                child: authState.isLoading
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text('Create Account'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _doLogin() {
    if (!_loginFormKey.currentState!.validate()) return;
    ref.read(authProvider.notifier).login(
          email: _loginEmail.text.trim(),
          password: _loginPassword.text,
        );
  }

  void _doRegister() {
    if (!_regFormKey.currentState!.validate()) return;
    ref.read(authProvider.notifier).register(
          email: _regEmail.text.trim(),
          username: _regUsername.text.trim(),
          password: _regPassword.text,
        );
  }
}
