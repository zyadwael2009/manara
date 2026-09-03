import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../theme/app_text_styles.dart';

/// Phase 26 · T9 — tiny "couldn't load" chip for above-the-fold
/// optional widgets (announcements banner, today card, streak card,
/// homework strip, now/next card).
///
/// Before this widget every one of those `.when(error: (_, __) => SizedBox.shrink())`
/// paths silently dropped a whole card on the floor — a bad server day
/// looked identical to "nothing here today," and users had no path
/// back to trying again.
///
/// This is deliberately understated: one line of muted text + a small
/// Retry pill. It never dominates the page — if the widget it stands
/// in for is optional, the failure should feel optional too.
class SilentError extends StatelessWidget {
  final VoidCallback? onRetry;
  final String label;

  const SilentError({
    super.key,
    this.onRetry,
    this.label = "Couldn't load — tap to retry",
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: InkWell(
        onTap: onRetry,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        child: Container(
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md, vertical: AppSpacing.sm),
          decoration: BoxDecoration(
            color: AppColors.surfaceMuted,
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            border: Border.all(color: AppColors.border),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.wifi_off_rounded,
                  size: 14, color: AppColors.textMuted),
              const SizedBox(width: AppSpacing.snug),
              Text(label,
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
              if (onRetry != null) ...[
                const SizedBox(width: AppSpacing.sm),
                Icon(Icons.refresh_rounded,
                    size: 14, color: AppColors.primary),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
