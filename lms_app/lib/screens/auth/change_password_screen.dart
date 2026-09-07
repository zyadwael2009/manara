import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/utils/validators.dart';
import '../../core/widgets/app_button.dart';
import '../../core/widgets/app_text_field.dart';
import '../../providers/auth_provider.dart';
import '../../services/api_service.dart';

/// Change your own password.
///
/// Reachable two ways:
///   * voluntarily, from Account settings (`forced: false`)
///   * compulsorily, right after signing in with a password somebody else
///     chose for you — a CSV bulk import or an admin reset (`forced: true`),
///     in which case there is no way past this screen but through it or out.
///
/// Until this screen existed there was no password change anywhere in the
/// product: bulk-imported accounts were stuck on the temporary password they
/// were issued, for good.
class ChangePasswordScreen extends ConsumerStatefulWidget {
  final bool forced;

  const ChangePasswordScreen({super.key, this.forced = false});

  @override
  ConsumerState<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends ConsumerState<ChangePasswordScreen> {
  final _formKey = GlobalKey<FormState>();
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();

  bool _submitting = false;
  bool _obscure = true;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _submitting = true);
    try {
      await ref.read(authProvider.notifier).changePassword(
            currentPassword: _current.text,
            newPassword: _next.text,
          );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Password changed. Your other devices were signed out.'),
        ),
      );
      // When forced, the app shell re-reads `mustChangePassword` from the
      // refreshed user and stops showing this screen on its own.
      if (!widget.forced && Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      }
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(friendlyError(e))),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Change password'),
        automaticallyImplyLeading: !widget.forced,
        actions: widget.forced
            ? [
                TextButton(
                  onPressed: _submitting
                      ? null
                      : () => ref.read(authProvider.notifier).logout(),
                  child: const Text('Sign out'),
                ),
              ]
            : null,
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (widget.forced) ...[
                      _ForcedBanner(theme: theme),
                      const SizedBox(height: AppSpacing.lg),
                    ],
                    AppTextField(
                      controller: _current,
                      label: widget.forced ? 'Temporary password' : 'Current password',
                      icon: Icons.lock_outline,
                      obscure: _obscure,
                      autofocus: true,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    AppTextField(
                      controller: _next,
                      label: 'New password',
                      hint: 'At least 8 characters',
                      icon: Icons.lock_reset,
                      obscure: _obscure,
                      validator: Validators.password,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    AppTextField(
                      controller: _confirm,
                      label: 'Confirm new password',
                      icon: Icons.check_circle_outline,
                      obscure: _obscure,
                      textInputAction: TextInputAction.done,
                      onSubmitted: (_) => _submit(),
                      validator: (v) {
                        if (v != _next.text) return 'Passwords do not match';
                        return null;
                      },
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed: () => setState(() => _obscure = !_obscure),
                        icon: Icon(
                          _obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                          size: 18,
                        ),
                        label: Text(_obscure ? 'Show passwords' : 'Hide passwords'),
                      ),
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    AppButton(
                      label: 'Change password',
                      loading: _submitting,
                      onPressed: _submitting ? null : _submit,
                    ),
                    const SizedBox(height: AppSpacing.md),
                    Text(
                      'Changing your password signs you out everywhere else.',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: AppColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ForcedBanner extends StatelessWidget {
  final ThemeData theme;

  const _ForcedBanner({required this.theme});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.warning.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.warning.withValues(alpha: 0.4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.key_outlined, color: AppColors.warning),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Choose your own password',
                  style: AppTextStyles.bodyStrong(context),
                ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'Your current password was set for you by the school office. '
                  'Pick one only you know before carrying on.',
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
