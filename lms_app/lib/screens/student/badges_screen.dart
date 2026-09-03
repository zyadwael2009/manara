import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../models/gamify.dart' as g;
import '../../providers/gamify_providers.dart';

/// Phase 24 — badges grid + full streak state.
class BadgesScreen extends ConsumerWidget {
  const BadgesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final streakAsync = ref.watch(myStreakProvider);
    final badgesAsync = ref.watch(myBadgesProvider);
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: Text('Streak & badges', style: AppTextStyles.h2(context))),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(myStreakProvider);
          ref.invalidate(myBadgesProvider);
          await ref.read(myStreakProvider.future);
          await ref.read(myBadgesProvider.future);
        },
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          children: [
            streakAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Text(friendlyError(e)),
              data: (s) => _StreakBand(streak: s),
            ),
            const SizedBox(height: AppSpacing.xl),
            Text('BADGES',
                style: AppTextStyles.micro(context, color: AppColors.textMuted)
                    .copyWith(
                        fontWeight: FontWeight.w800, letterSpacing: 0.8)),
            const SizedBox(height: AppSpacing.sm),
            badgesAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Text(friendlyError(e)),
              data: (p) => GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: AppSpacing.md,
                crossAxisSpacing: AppSpacing.md,
                childAspectRatio: 1.6,
                children: [
                  for (final b in p.badges) _BadgeTile(badge: b),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StreakBand extends StatelessWidget {
  final g.StreakState streak;
  const _StreakBand({required this.streak});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppColors.warning, AppColors.warningDeep],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
      ),
      child: Row(children: [
        const Icon(Icons.local_fire_department_rounded,
            color: Colors.white, size: 48),
        const SizedBox(width: AppSpacing.lg),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${streak.currentStreak}',
                  style: const TextStyle(
                      color: Colors.white,
                      fontSize: 36,
                      fontWeight: FontWeight.w900)),
              const Text('Day streak',
                  style: TextStyle(
                      color: Colors.white70,
                      fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Text('Longest ${streak.longestStreak}',
                  style: const TextStyle(color: Colors.white70)),
            ],
          ),
        ),
      ]),
    );
  }
}

class _BadgeTile extends StatelessWidget {
  final g.Badge badge;
  const _BadgeTile({required this.badge});
  static const Map<String, IconData> _icons = {
    'workspace_premium': Icons.workspace_premium_outlined,
    'auto_awesome': Icons.auto_awesome_outlined,
    'event_available': Icons.event_available_outlined,
    'local_fire_department': Icons.local_fire_department_outlined,
    'star': Icons.star_outline_rounded,
  };
  @override
  Widget build(BuildContext context) {
    final icon = _icons[badge.icon] ?? Icons.star_outline_rounded;
    final earned = badge.earned;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: earned ? AppColors.successSoft : AppColors.surface,
        border: Border.all(
          color: earned ? AppColors.success.withValues(alpha: 0.35) : AppColors.border,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      ),
      child: Row(children: [
        Icon(icon,
            size: 30,
            color: earned ? AppColors.success : AppColors.textMuted),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(badge.title,
                  style: AppTextStyles.body(context)
                      .copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 2),
              Text(badge.description,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTextStyles.caption(context,
                      color: earned
                          ? AppColors.success
                          : AppColors.textMuted)),
            ],
          ),
        ),
      ]),
    );
  }
}
