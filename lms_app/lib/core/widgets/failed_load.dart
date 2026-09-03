import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../theme/app_text_styles.dart';

/// Phase 29 · T1 — canonical "required data failed to load" block.
///
/// Sibling of [SilentError] (`silent_error.dart`) — that one is for
/// above-the-fold optional widgets where a load failure should be quiet.
/// This one is for surfaces where the widget's job is to render specific
/// data and losing it MUST be visible: an admin grades filter chip that
/// can't fetch categories, an attendance strip whose data is required
/// for the day's totals, a class-average band without which the row is
/// misleading.
///
/// Renders as a full-width red-tinted card with an icon, a label, and a
/// Retry button so the user has a clear path back. Deliberately louder
/// than [SilentError]: same-shape retry callback, but here the failure
/// is the point, not an afterthought.
class FailedLoad extends StatelessWidget {
  final String label;
  final String? detail;
  final VoidCallback? onRetry;

  const FailedLoad({
    super.key,
    this.label = "Couldn't load this section",
    this.detail,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.dangerSoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.danger.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.error_outline_rounded,
              color: AppColors.danger, size: 20),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label,
                    style: AppTextStyles.body(context, color: AppColors.danger)
                        .copyWith(fontWeight: FontWeight.w700)),
                if (detail != null && detail!.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.tiny),
                  Text(detail!,
                      style: AppTextStyles.caption(context,
                          color: AppColors.textSecondary)),
                ],
              ],
            ),
          ),
          if (onRetry != null) ...[
            const SizedBox(width: AppSpacing.sm),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded, size: 16),
              label: const Text('Retry'),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.danger,
                side: const BorderSide(color: AppColors.danger),
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.md, vertical: 6),
                minimumSize: const Size(0, 32),
                visualDensity: VisualDensity.compact,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
