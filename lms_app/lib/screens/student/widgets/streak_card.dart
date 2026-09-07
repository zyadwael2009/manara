import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/transitions.dart';
import '../../../models/gamify.dart';
import '../../../providers/gamify_providers.dart';
import '../badges_screen.dart';
import '../../../core/widgets/trailing_chevron.dart';
import '../../../core/widgets/silent_error.dart';

/// Phase 24 — compact streak flame + earned-badge count. Tap → the full
/// badges screen. Silent (returns SizedBox) while loading; shows even at
/// streak=0 so the student knows the feature exists.
class StreakCard extends ConsumerWidget {
  const StreakCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final streakAsync = ref.watch(myStreakProvider);
    final badgesAsync = ref.watch(myBadgesProvider);

    return streakAsync.when(
      loading: () => const SizedBox.shrink(),
      // Phase 26 · T9 — SilentError so a streak fetch failure is
      // visible without dominating the page.
      error: (_, _) => SilentError(
        onRetry: () => ref.invalidate(myStreakProvider),
      ),
      data: (streak) {
        final earned = badgesAsync.maybeWhen(
          data: (p) => p.earnedCount, orElse: () => 0);
        return Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.lg),
          child: InkWell(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            onTap: () {
              Navigator.of(context).push(fadeThroughRoute(const BadgesScreen()));
            },
            child: Container(
              padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.lg, vertical: AppSpacing.md),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                border: Border.all(color: AppColors.border),
              ),
              child: Row(children: [
                _FlameBadge(streak: streak),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                          streak.currentStreak == 0
                              ? "Start your streak"
                              : streak.currentStreak == 1
                                  ? "1 day streak · keep it up"
                                  : "${streak.currentStreak} days in a row",
                          style: AppTextStyles.body(context)
                              .copyWith(fontWeight: FontWeight.w800)),
                      Text(
                          "Longest ${streak.longestStreak}  ·  Badges $earned",
                          style: AppTextStyles.caption(context,
                              color: AppColors.textMuted)),
                    ],
                  ),
                ),
                const TrailingChevron(color: AppColors.textMuted),
              ]),
            ),
          ),
        );
      },
    );
  }
}

class _FlameBadge extends StatelessWidget {
  final StreakState streak;
  const _FlameBadge({required this.streak});
  @override
  Widget build(BuildContext context) {
    final active = streak.currentStreak > 0;
    return Container(
      width: 44, height: 44,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: active ? AppColors.warningSoft : AppColors.surfaceMuted,
        shape: BoxShape.circle,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.local_fire_department_rounded,
            color: active ? AppColors.warning : AppColors.textMuted,
            size: 20,
          ),
          const SizedBox(width: 2),
          Text('${streak.currentStreak}',
              style: TextStyle(
                  color: active ? AppColors.warning : AppColors.textMuted,
                  fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}
