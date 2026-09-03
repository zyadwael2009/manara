import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../core/utils/validators.dart';
import '../../core/widgets/app_button.dart';
import '../../core/widgets/app_text_field.dart';
import '../../providers/auth_provider.dart';
import '../../services/api_service.dart';
import 'login_screen.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  String _role = 'student';
  bool _submitting = false;

  // Phase 6: parent accounts are created by the school office (see
  // `POST /api/users`). Self-registration is limited to students and
  // instructors; the server refuses role='parent' on the register path.
  static const _roles = <(String, String, IconData)>[
    ('student', 'Student', Icons.school_outlined),
    ('instructor', 'Instructor', Icons.record_voice_over_outlined),
  ];

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _submitting = true);
    try {
      await ref.read(authProvider.notifier).register(
            name: _name.text.trim(),
            email: _email.text.trim(),
            password: _password.text,
            role: _role,
          );
      // No pop needed — LmsApp watches authProvider and swaps the home.
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
                Text('Welcome to Manara', style: AppTextStyles.display(context)),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Create an account — pick your role to get started.',
                  style: AppTextStyles.body(context, color: AppColors.textSecondary),
                ),
                const SizedBox(height: AppSpacing.xxl),
                _RolePicker(
                  roles: _roles,
                  selected: _role,
                  onChanged: (r) => setState(() => _role = r),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Parent accounts are created by the school office.',
                  style: AppTextStyles.caption(context, color: AppColors.textMuted),
                ),
                const SizedBox(height: AppSpacing.xl),
                AppTextField(
                  controller: _name,
                  label: 'Full name',
                  hint: 'Ada Lovelace',
                  icon: Icons.person_outline_rounded,
                  validator: (v) => Validators.required(v, field: 'Name'),
                ),
                const SizedBox(height: AppSpacing.lg),
                AppTextField(
                  controller: _email,
                  label: 'Email',
                  hint: 'you@example.com',
                  icon: Icons.mail_outline_rounded,
                  keyboardType: TextInputType.emailAddress,
                  validator: Validators.email,
                ),
                const SizedBox(height: AppSpacing.lg),
                AppTextField(
                  controller: _password,
                  label: 'Password',
                  hint: 'at least 8 characters',
                  icon: Icons.lock_outline_rounded,
                  obscure: true,
                  validator: Validators.password,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _submit(),
                ),
                const SizedBox(height: AppSpacing.xl),
                AppButton(
                  label: 'Create account',
                  loading: _submitting,
                  onPressed: _submit,
                ),
                const SizedBox(height: AppSpacing.xl),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text('Already have an account?', style: AppTextStyles.body(context)),
                    TextButton(
                      onPressed: () {
                        Navigator.of(context).pushReplacement(
                          fadeThroughRoute(const LoginScreen()),
                        );
                      },
                      child: const Text('Sign in'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RolePicker extends StatelessWidget {
  final List<(String, String, IconData)> roles;
  final String selected;
  final ValueChanged<String> onChanged;

  const _RolePicker({
    required this.roles,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (final (key, label, icon) in roles) ...[
          Expanded(child: _RoleTile(
            keyValue: key,
            label: label,
            icon: icon,
            selected: selected == key,
            onTap: () => onChanged(key),
          )),
          if (key != roles.last.$1) const SizedBox(width: AppSpacing.sm),
        ],
      ],
    );
  }
}

class _RoleTile extends StatelessWidget {
  final String keyValue;
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  const _RoleTile({
    required this.keyValue,
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
        decoration: BoxDecoration(
          color: selected ? AppColors.primarySoft : Theme.of(context).colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          border: Border.all(
            color: selected ? AppColors.primary : Colors.transparent,
            width: 1.5,
          ),
        ),
        child: Column(
          children: [
            Icon(icon, color: selected ? AppColors.primary : AppColors.textSecondary),
            const SizedBox(height: AppSpacing.xs),
            Text(
              label,
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: selected ? AppColors.primary : AppColors.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
