import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/auth_provider.dart';
import '../../screens/auth/change_password_screen.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../theme/app_text_styles.dart';

/// The signed-in user's avatar, with the actions that belong to the account
/// itself rather than to any one role's home screen.
///
/// Admin, teacher and parent home screens each carried their own bare
/// "Sign out" `IconButton`, and the student screen a private popup menu — so
/// adding "Change password" meant touching four places and getting four
/// slightly different results. One widget, four call sites.
class AccountMenu extends ConsumerWidget {
  const AccountMenu({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authProvider).user;
    if (user == null) return const SizedBox.shrink();

    return PopupMenuButton<String>(
      tooltip: user.name,
      onSelected: (value) async {
        switch (value) {
          case 'password':
            await Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const ChangePasswordScreen()),
            );
          case 'logout':
            await ref.read(authProvider.notifier).logout();
        }
      },
      itemBuilder: (_) => [
        PopupMenuItem<String>(
          enabled: false,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(user.name, style: AppTextStyles.bodyStrong(context)),
              Text(user.email, style: AppTextStyles.caption(context)),
              if (user.className != null) ...[
                const SizedBox(height: 2),
                Text(
                  '${user.gradeName ?? ""} · ${user.className}',
                  style: AppTextStyles.micro(context, color: AppColors.primary),
                ),
              ],
            ],
          ),
        ),
        const PopupMenuDivider(),
        const PopupMenuItem<String>(
          value: 'password',
          child: Row(children: [
            Icon(Icons.lock_reset, size: 18),
            SizedBox(width: AppSpacing.sm),
            Text('Change password'),
          ]),
        ),
        const PopupMenuItem<String>(
          value: 'logout',
          child: Row(children: [
            Icon(Icons.logout_rounded, size: 18),
            SizedBox(width: AppSpacing.sm),
            Text('Sign out'),
          ]),
        ),
      ],
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
        child: CircleAvatar(
          backgroundColor: AppColors.primary,
          child: Text(
            user.name.isNotEmpty ? user.name[0].toUpperCase() : '?',
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ),
    );
  }
}
