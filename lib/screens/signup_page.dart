import 'package:flutter/material.dart';
import 'login_form_page.dart';
import 'main_navigation.dart';
import '../services/auth_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class SignupPage extends StatefulWidget {
  const SignupPage({super.key});

  @override
  State<SignupPage> createState() => _SignupPageState();
}

class _SignupPageState extends State<SignupPage> {
  final _formKey = GlobalKey<FormState>();

  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _isLoading = false;
  String? _serverError;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  String? _validateName(String? value) {
    final text = value?.trim() ?? '';
    if (text.isEmpty) return 'Name is required';
    if (text.length < 2) return 'Name is too short';
    return null;
  }

  String? _validateEmail(String? value) {
    final text = value?.trim() ?? '';
    if (text.isEmpty) return 'Email is required';
    final emailRegex = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
    if (!emailRegex.hasMatch(text)) return 'Enter a valid email';
    return null;
  }

  String? _validatePassword(String? value) {
    final text = value ?? '';
    if (text.isEmpty) return 'Password is required';
    if (text.length < 6) return 'Password must be at least 6 characters';
    return null;
  }

  String? _validateConfirmPassword(String? value) {
    final text = value ?? '';
    if (text.isEmpty) return 'Please confirm your password';
    if (text != _passwordController.text) return 'Passwords do not match';
    return null;
  }

  Widget _visibilityToggle(bool obscured, VoidCallback onTap) {
    return IconButton(
      onPressed: onTap,
      icon: Icon(
        obscured ? Icons.visibility_off_rounded : Icons.visibility_rounded,
        color: AppColors.textMuted,
        size: 20,
      ),
    );
  }

  Future<void> _signup() async {
    FocusScope.of(context).unfocus();
    setState(() {
      _serverError = null;
    });

    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
    });

    try {
      await AuthService.signup(
        name: _nameController.text,
        email: _emailController.text,
        password: _passwordController.text,
      );

      if (!mounted) return;

      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const MainNavigation()),
      );
    } catch (e) {
      setState(() {
        _serverError = e.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Column(
          children: [
            ScreenHeader(
              title: 'Sign up',
              leading: IconCircleButton(
                icon: Icons.arrow_back_rounded,
                onTap: () => Navigator.pop(context),
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 24),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Headline(
                        [
                          HeadlineSpan('Create your '),
                          HeadlineSpan('account', emphasis: true, italic: true),
                          HeadlineSpan('.'),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Start tracking runs and building your territory.',
                        style: AppText.bodySecondary,
                      ),
                      const SizedBox(height: 28),
                      AppTextField(
                        controller: _nameController,
                        label: 'Name',
                        hint: 'Enter your name',
                        validator: _validateName,
                      ),
                      const SizedBox(height: 18),
                      AppTextField(
                        controller: _emailController,
                        label: 'Email',
                        hint: 'Enter your email',
                        keyboardType: TextInputType.emailAddress,
                        validator: _validateEmail,
                      ),
                      const SizedBox(height: 18),
                      AppTextField(
                        controller: _passwordController,
                        label: 'Password',
                        hint: 'Create a password',
                        obscure: _obscurePassword,
                        validator: _validatePassword,
                        suffix: _visibilityToggle(_obscurePassword, () {
                          setState(() {
                            _obscurePassword = !_obscurePassword;
                          });
                        }),
                      ),
                      const SizedBox(height: 18),
                      AppTextField(
                        controller: _confirmPasswordController,
                        label: 'Confirm password',
                        hint: 'Confirm your password',
                        obscure: _obscureConfirmPassword,
                        validator: _validateConfirmPassword,
                        suffix: _visibilityToggle(_obscureConfirmPassword, () {
                          setState(() {
                            _obscureConfirmPassword = !_obscureConfirmPassword;
                          });
                        }),
                      ),
                      const SizedBox(height: 20),
                      if (_serverError != null) ...[
                        ErrorBanner(_serverError!),
                        const SizedBox(height: 20),
                      ],
                      GradientButton(
                        label: 'Create account',
                        loading: _isLoading,
                        onPressed: _isLoading ? null : _signup,
                      ),
                      const SizedBox(height: 18),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            'Already have an account? ',
                            style: AppText.bodySecondary,
                          ),
                          GestureDetector(
                            onTap: () {
                              Navigator.pushReplacement(
                                context,
                                MaterialPageRoute(
                                  builder: (_) => const LoginFormPage(),
                                ),
                              );
                            },
                            child: Text(
                              'Log in',
                              style: AppText.bodySecondary.copyWith(
                                color: AppColors.pink,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        ],
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
