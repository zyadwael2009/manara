import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../providers/auth_provider.dart';
import '../../../providers/comm_providers.dart';
import '../../../core/widgets/silent_error.dart';

/// Phase 21 — small "Today's homework" card at the top of My classes.
/// Silent when the student has no class or no post for the last few days.
class HomeworkStrip extends ConsumerWidget {
  const HomeworkStrip({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authProvider).user;
    final classId = user?.classId;
    if (classId == null || classId.isEmpty) {
      return const SizedBox.shrink();
    }
    final async = ref.watch(classHomeworkProvider(classId));
    return async.when(
      loading: () => const SizedBox.shrink(),
      // Phase 26 · T9 — SilentError so a homework fetch failure isn't
      // invisible; the retry lives in the tile itself.
      error: (_, __) => SilentError(
        onRetry: () => ref.invalidate(classHomeworkProvider(classId)),
      ),
      data: (rows) {
        if (rows.isEmpty) return const SizedBox.shrink();
        // Show the latest post whose date is <= today.
        final now = DateTime.now();
        final past = rows.where((r) => !r.date.isAfter(now)).toList();
        if (past.isEmpty) return const SizedBox.shrink();
        final post = past.first; // list is sorted date-desc server-side
        return Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.lg),
          child: Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: AppColors.accentSoft,
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              border: Border.all(color: AppColors.accent.withValues(alpha: 0.35)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.assignment_late_outlined,
                    color: AppColors.accentText),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('HOMEWORK · ${_dateLabel(post.date)}',
                          style: AppTextStyles.micro(context,
                                  color: AppColors.accentText)
                              .copyWith(
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: 0.8)),
                      const SizedBox(height: 2),
                      Text(post.title,
                          style: AppTextStyles.body(context).copyWith(
                              fontWeight: FontWeight.w700,
                              color: AppColors.textPrimary)),
                      if (post.body.isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(post.body,
                            style: AppTextStyles.caption(context,
                                color: AppColors.textSecondary)),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  static String _dateLabel(DateTime d) {
    const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return '${days[d.weekday - 1]} ${d.day} ${months[d.month - 1]}';
  }
}
