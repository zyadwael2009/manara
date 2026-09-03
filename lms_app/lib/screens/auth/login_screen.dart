import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../core/utils/validators.dart';
import '../../core/widgets/app_button.dart';
import '../../core/widgets/app_text_field.dart';
import '../../providers/auth_provider.dart';
import '../../services/api_service.dart';
import '../public/verify_screen.dart';
import 'register_screen.dart';

/// Pre-seeded demo credentials — must match seed_dev.py.
/// Kept public so main.dart can trigger them from a `?demo=` query string.
class DemoCredentials {
  DemoCredentials._();
  static const Map<String, ({String email, String password, String label})> byRole = {
    'student': (email: 'amira@school.local', password: 'student1', label: 'Try as student'),
    'teacher': (email: 'rivera@school.local', password: 'teacher1', label: 'Try as teacher'),
    'parent': (email: 'parent@school.local', password: 'parent12', label: 'Try as parent'),
    'admin': (email: 'admin@school.local', password: 'adminadmin', label: 'Try as admin'),
  };
}

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _submitting = false;
  bool _obscure = true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _submitting = true);
    try {
      await ref.read(authProvider.notifier).login(
            email: _email.text.trim(),
            password: _password.text,
          );
      // No pop needed — LmsApp watches authProvider and swaps the home
      // widget as soon as this succeeds.
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _demoLogin(String role) async {
    final creds = DemoCredentials.byRole[role];
    if (creds == null) return;
    setState(() => _submitting = true);
    try {
      await ref.read(authProvider.notifier).login(
            email: creds.email,
            password: creds.password,
          );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: AppSpacing.xl),
                Text('Welcome back', style: AppTextStyles.display(context)),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Sign in to ${AppConstants.appName}.',
                  style: AppTextStyles.body(context, color: AppColors.textSecondary),
                ),
                const SizedBox(height: AppSpacing.xxl),
                AppTextField(
                  controller: _email,
                  label: 'Email',
                  hint: 'you@example.com',
                  icon: Icons.mail_outline_rounded,
                  keyboardType: TextInputType.emailAddress,
                  validator: Validators.email,
                  autofocus: true,
                ),
                const SizedBox(height: AppSpacing.lg),
                AppTextField(
                  controller: _password,
                  label: 'Password',
                  hint: '••••••••',
                  icon: Icons.lock_outline_rounded,
                  obscure: _obscure,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _submit(),
                  validator: Validators.password,
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(
                    onPressed: () => setState(() => _obscure = !_obscure),
                    child: Text(_obscure ? 'Show password' : 'Hide password'),
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                AppButton(
                  label: 'Sign in',
                  loading: _submitting,
                  onPressed: _submit,
                ),
                const SizedBox(height: AppSpacing.xl),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text("Don't have an account?", style: AppTextStyles.body(context)),
                    TextButton(
                      onPressed: () {
                        Navigator.of(context).pushReplacement(
                          fadeThroughRoute(const RegisterScreen()),
                        );
                      },
                      child: const Text('Create one'),
                    ),
                  ],
                ),
                Center(
                  child: TextButton.icon(
                    onPressed: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const VerifyScreen()),
                      );
                    },
                    icon: const Icon(Icons.workspace_premium_outlined, size: 16),
                    label: const Text('Verify a certificate'),
                  ),
                ),
                const SizedBox(height: AppSpacing.xl),
                _DemoDivider(),
                const SizedBox(height: AppSpacing.md),
                _DemoGrid(busy: _submitting, onPick: _demoLogin),
                const SizedBox(height: AppSpacing.xxl),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ============================================================================
// Demo grid — one-tap sign-in for a hiring-manager walkthrough.
// ============================================================================
class _DemoDivider extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Expanded(child: Container(height: 1, color: AppColors.divider)),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: Text('or try the demo',
            style: AppTextStyles.micro(context, color: AppColors.textMuted)),
      ),
      Expanded(child: Container(height: 1, color: AppColors.divider)),
    ]);
  }
}

class _DemoGrid extends StatelessWidget {
  final bool busy;
  final Future<void> Function(String role) onPick;
  const _DemoGrid({required this.busy, required this.onPick});

  static const _order = ['parent', 'student', 'teacher', 'admin'];

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 2,
      mainAxisSpacing: AppSpacing.sm,
      crossAxisSpacing: AppSpacing.sm,
      childAspectRatio: 3.0,
      children: [for (final r in _order) _DemoPill(role: r, busy: busy, onTap: onPick)],
    );
  }
}

class _DemoPill extends StatelessWidget {
  final String role;
  final bool busy;
  final Future<void> Function(String role) onTap;
  const _DemoPill({required this.role, required this.busy, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final creds = DemoCredentials.byRole[role]!;
    final isParent = role == 'parent';
    final bg = isParent ? AppColors.accentSoft : AppColors.primarySoft;
    final fg = isParent ? AppColors.accentText : AppColors.primaryDark;
    return InkWell(
      onTap: busy ? null : () => onTap(role),
      borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          border: Border.all(color: fg.withValues(alpha: 0.25)),
        ),
        child: Center(
          child: Text(creds.label,
              style: AppTextStyles.bodyStrong(context, color: fg),
              overflow: TextOverflow.ellipsis),
        ),
      ),
    );
  }
}
