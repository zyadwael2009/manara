import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../theme/app_text_styles.dart';

/// Phase 26 · T8 — canonical "warning banner" tile.
///
/// Before this widget every warning strip was hand-rolled inline
/// (amber `Container` with a triangle icon, an amber label, and a
/// muted supporting paragraph). They had drifted apart — different
/// radii, different padding, different tone of copy.
///
/// This gives us **one** amber tile with:
///   - `Icons.warning_amber_rounded` on the leading side
///   - `title` in bold amber text
///   - optional `message` in the secondary body tone
///   - optional `action` (usually an outlined button) on the trailing end
///
/// Adopted by the electives banner on `my_classes_screen` and the
/// `student_detail_screen` pending-elective warn tile.
class WarningTile extends StatelessWidget {
  final String title;
  final String? message;
  final Widget? action;
  final EdgeInsetsGeometry padding;

  const WarningTile({
    super.key,
    required this.title,
    this.message,
    this.action,
    this.padding = const EdgeInsets.all(AppSpacing.md),
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: AppColors.accentSoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.warning_amber_rounded,
              color: AppColors.accentText),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: AppTextStyles.body(context, color: AppColors.accentText)
                        .copyWith(fontWeight: FontWeight.w700)),
                if (message != null) ...[
                  const SizedBox(height: AppSpacing.tiny),
                  Text(message!,
                      style: AppTextStyles.caption(context,
                          color: AppColors.textSecondary)),
                ],
              ],
            ),
          ),
          if (action != null) ...[
            const SizedBox(width: AppSpacing.sm),
            action!,
          ],
        ],
      ),
    );
  }
}
