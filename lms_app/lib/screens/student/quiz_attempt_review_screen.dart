import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../providers/quiz_providers.dart';
import 'widgets/quiz_results_view.dart';

/// Phase 17 — read-only per-attempt review. Reached from the Quizzes hub's
/// history screen when a student taps one of their past attempts.
///
/// No submit CTA, no re-answer flow; the shared `QuizResultsView` renders
/// the summary card + per-question breakdown identically to the post-submit
/// view inside `QuizViewerScreen`.
class QuizAttemptReviewScreen extends ConsumerWidget {
  final String attemptId;
  final String? courseTitle;
  final String? quizTitle;

  const QuizAttemptReviewScreen({
    super.key,
    required this.attemptId,
    this.courseTitle,
    this.quizTitle,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(attemptProvider(attemptId));
    return Scaffold(
      appBar: AppBar(
        title: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (courseTitle != null)
              Text(courseTitle!, style: AppTextStyles.h3(context)),
            if (quizTitle != null)
              Text(quizTitle!, style: AppTextStyles.caption(context)),
          ],
        ),
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Center(
            child: Text(friendlyError(e),
                style: AppTextStyles.body(context, color: AppColors.danger),
                textAlign: TextAlign.center),
          ),
        ),
        data: (env) => QuizResultsView(env: env),
      ),
    );
  }
}
