import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../providers/auth_provider.dart';

class ParentPlaceholderScreen extends ConsumerWidget {
  const ParentPlaceholderScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Parent portal', style: AppTextStyles.h2(context)),
        actions: [
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout_rounded),
            onPressed: () => ref.read(authProvider.notifier).logout(),
          ),
        ],
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xxl),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Container(
              width: 120,
              height: 120,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    AppColors.primary.withValues(alpha: 0.10),
                    AppColors.accent.withValues(alpha: 0.10),
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.family_restroom_outlined,
                  size: 56, color: AppColors.primary),
            ),
            const SizedBox(height: AppSpacing.xl),
            Text('Parent portal — coming in Phase 6',
                style: AppTextStyles.h2(context), textAlign: TextAlign.center),
            const SizedBox(height: AppSpacing.sm),
            Text(
              "Once we get to Phase 6, this is where you'll see your child's classes, progress, quiz results, and be able to view the content they're learning.",
              style: AppTextStyles.body(context, color: AppColors.textSecondary),
              textAlign: TextAlign.center,
            ),
          ]),
        ),
      ),
    );
  }
}
