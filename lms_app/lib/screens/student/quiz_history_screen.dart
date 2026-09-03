import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/utils/transitions.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/quiz.dart';
import '../../providers/quiz_providers.dart';
import 'quiz_attempt_review_screen.dart';
import 'quiz_viewer_screen.dart';
import '../../core/widgets/trailing_chevron.dart';

/// Phase 17 — the guarded landing screen for a quiz from the Quizzes hub.
///
/// Shows the caller's attempt history for one quiz, and offers a
/// **Retry** (or **Start**) button ONLY when attempts remain (as
/// determined by the server-computed `canRetake` flag).
///
/// This exists so a student never accidentally consumes a `max_attempts`
/// slot by opening the quiz — they see the prior attempts first, then
/// consciously choose to retake.
class QuizHistoryScreen extends ConsumerWidget {
  final MyQuizRow initialRow;

  const QuizHistoryScreen({super.key, required this.initialRow});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Watch the hub provider so retries done in this session refresh the
    // history in place. Fall back to the row we were pushed with while the
    // provider is still loading (avoids flicker on first render).
    final async = ref.watch(myQuizzesAllProvider);
    final row = async.maybeWhen(
      data: (rows) => rows.firstWhere(
        (r) => r.quiz.id == initialRow.quiz.id,
        orElse: () => initialRow,
      ),
      orElse: () => initialRow,
    );

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(row.course.title, style: AppTextStyles.h3(context)),
            Text(row.quiz.title,
                style: AppTextStyles.caption(context, color: AppColors.textMuted)),
          ],
        ),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(myQuizzesAllProvider);
          await ref.read(myQuizzesAllProvider.future);
        },
        child: async.when(
          loading: () => _bodyList(context, row),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(friendlyError(e))),
          ]),
          data: (_) => _bodyList(context, row),
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: _RetryButton(row: row),
        ),
      ),
    );
  }

  Widget _bodyList(BuildContext context, MyQuizRow row) {
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        _HeaderCard(row: row),
        const SizedBox(height: AppSpacing.xl),
        Text('YOUR ATTEMPTS',
            style: AppTextStyles.caption(context, color: AppColors.textMuted)
                .copyWith(letterSpacing: 0.8, fontWeight: FontWeight.w700)),
        const SizedBox(height: AppSpacing.sm),
        if (row.attempts.isEmpty)
          _EmptyAttempts()
        else
          for (final a in row.attempts.reversed)
            _AttemptCard(row: row, attempt: a),
      ],
    );
  }
}

class _HeaderCard extends StatelessWidget {
  final MyQuizRow row;
  const _HeaderCard({required this.row});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        side: const BorderSide(color: AppColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.primarySoft,
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(row.quiz.moduleTitle,
                  style: AppTextStyles.caption(context, color: AppColors.primaryDark)
                      .copyWith(fontWeight: FontWeight.w700)),
            ),
            const Spacer(),
            _BestBadge(row: row),
          ]),
          const SizedBox(height: AppSpacing.md),
          Text(row.quiz.title,
              style: AppTextStyles.h2(context)
                  .copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: AppSpacing.sm),
          Wrap(
            spacing: AppSpacing.lg,
            runSpacing: AppSpacing.xs,
            children: [
              _MetaItem(icon: Icons.stars_outlined,
                  label: '${row.quiz.totalPoints} pts'),
              _MetaItem(icon: Icons.flag_outlined,
                  label: 'Pass ≥ ${row.quiz.passingScore}%'),
              _MetaItem(
                icon: Icons.replay_rounded,
                label: _attemptCapLabel(row),
              ),
              if (row.quiz.timeLimitMinutes != null)
                _MetaItem(icon: Icons.timer_outlined,
                    label: '${row.quiz.timeLimitMinutes} min'),
            ],
          ),
        ]),
      ),
    );
  }

  static String _attemptCapLabel(MyQuizRow row) {
    if (row.quiz.maxAttempts == null) {
      return row.attemptsCount == 0
          ? 'Unlimited attempts'
          : '${row.attemptsCount} attempt${row.attemptsCount == 1 ? "" : "s"}';
    }
    return '${row.attemptsCount} / ${row.quiz.maxAttempts} attempts';
  }
}

class _MetaItem extends StatelessWidget {
  final IconData icon;
  final String label;
  const _MetaItem({required this.icon, required this.label});
  @override
  Widget build(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(icon, size: 14, color: AppColors.textMuted),
      const SizedBox(width: 4),
      Text(label,
          style: AppTextStyles.caption(context, color: AppColors.textSecondary)),
    ]);
  }
}

class _BestBadge extends StatelessWidget {
  final MyQuizRow row;
  const _BestBadge({required this.row});
  @override
  Widget build(BuildContext context) {
    if (row.bestPercent == null) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: AppColors.surfaceMuted,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text('New',
            style: AppTextStyles.caption(context, color: AppColors.textSecondary)
                .copyWith(fontWeight: FontWeight.w600, letterSpacing: 0.4)),
      );
    }
    final passed = row.bestPercent! >= row.quiz.passingScore;
    final bg = passed ? AppColors.successSoft : AppColors.dangerSoft;
    final fg = passed ? AppColors.success : AppColors.danger;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(passed ? Icons.check_circle_rounded : Icons.error_outline_rounded,
            size: 14, color: fg),
        const SizedBox(width: 6),
        Text('Best ${row.bestPercent!.round()}%',
            style: AppTextStyles.caption(context, color: fg)
                .copyWith(fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

class _EmptyAttempts extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    // Phase 26 · T2 — use the canonical EmptyState so this history
    // page reads like every other "nothing here yet" screen.
    return const EmptyState(
      icon: Icons.history_toggle_off,
      title: 'No attempts yet',
      message: 'Take the quiz to see your history here.',
    );
  }
}

class _AttemptCard extends StatelessWidget {
  final MyQuizRow row;
  final MyQuizAttemptStub attempt;
  const _AttemptCard({required this.row, required this.attempt});

  @override
  Widget build(BuildContext context) {
    final passed = attempt.percent != null &&
        attempt.percent! >= row.quiz.passingScore;
    final pctColor = attempt.percent == null
        ? AppColors.textMuted
        : (passed ? AppColors.success : AppColors.danger);
    final pctBg = attempt.percent == null
        ? AppColors.surfaceMuted
        : (passed ? AppColors.successSoft : AppColors.dangerSoft);

    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Card(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          side: const BorderSide(color: AppColors.border),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          onTap: () {
            Navigator.of(context).push(fadeThroughRoute(
              QuizAttemptReviewScreen(
                attemptId: attempt.id,
                courseTitle: row.course.title,
                quizTitle: '${row.quiz.title} · attempt #${attempt.attemptNumber}',
              ),
            ));
          },
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Row(children: [
              Container(
                width: 36, height: 36,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: pctBg,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text('#${attempt.attemptNumber}',
                    style: TextStyle(
                        color: pctColor,
                        fontWeight: FontWeight.w800, fontSize: 12)),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Text(
                        attempt.percent == null
                            ? '—'
                            : '${attempt.percent!.round()}%',
                        style: AppTextStyles.bodyStrong(context, color: pctColor)
                            .copyWith(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      if (attempt.finalScore != null && attempt.maxScore != null)
                        Text(
                            '${_trim(attempt.finalScore!)}/${_trim(attempt.maxScore!)}',
                            style: AppTextStyles.caption(context,
                                color: AppColors.textMuted)),
                      const SizedBox(width: AppSpacing.sm),
                      if (attempt.needsManualReview)
                        Text('review pending',
                            style: AppTextStyles.caption(context,
                                    color: AppColors.warning)
                                .copyWith(fontStyle: FontStyle.italic)),
                    ]),
                    const SizedBox(height: 2),
                    Text(_dateLabel(attempt.submittedAt),
                        style: AppTextStyles.caption(context,
                            color: AppColors.textMuted)),
                  ],
                ),
              ),
              _PassChip(passed: passed, hasPct: attempt.percent != null),
              const SizedBox(width: AppSpacing.sm),
              const TrailingChevron(color: AppColors.textMuted),
            ]),
          ),
        ),
      ),
    );
  }

  static String _dateLabel(String? iso) {
    if (iso == null) return 'In progress';
    final t = DateTime.tryParse(iso);
    if (t == null) return '';
    const months = [
      'Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'
    ];
    return '${t.day} ${months[t.month - 1]} ${t.year}';
  }

  static String _trim(double d) {
    if (d == d.roundToDouble()) return d.toInt().toString();
    return d.toStringAsFixed(1);
  }
}

class _PassChip extends StatelessWidget {
  final bool passed;
  final bool hasPct;
  const _PassChip({required this.passed, required this.hasPct});
  @override
  Widget build(BuildContext context) {
    if (!hasPct) return const SizedBox.shrink();
    final fg = passed ? AppColors.success : AppColors.danger;
    final bg = passed ? AppColors.successSoft : AppColors.dangerSoft;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(passed ? 'Passed' : 'Failed',
          style: TextStyle(
              color: fg, fontWeight: FontWeight.w700, fontSize: 11)),
    );
  }
}

/// The action row at the bottom — Start / Retry / disabled with reason.
class _RetryButton extends ConsumerWidget {
  final MyQuizRow row;
  const _RetryButton({required this.row});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final canRetake = row.canRetake;
    final label = canRetake
        ? (row.attemptsCount == 0 ? 'Start quiz' : 'Retry quiz')
        : _reasonLabel(row);
    final icon =
        canRetake ? Icons.play_arrow_rounded : Icons.lock_outline_rounded;

    return Column(mainAxisSize: MainAxisSize.min, children: [
      if (!canRetake) ...[
        Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
          child: Text(
            _reasonHelp(row),
            textAlign: TextAlign.center,
            style: AppTextStyles.caption(context, color: AppColors.textMuted),
          ),
        ),
      ],
      SizedBox(
        width: double.infinity,
        height: 48,
        child: ElevatedButton.icon(
          onPressed: canRetake
              ? () async {
                  await Navigator.of(context).push(fadeThroughRoute(
                    QuizViewerScreen(
                      quizId: row.quiz.id,
                      courseTitle: row.course.title,
                    ),
                  ));
                  // The viewer already invalidates myEnrollmentsProvider +
                  // myReportCardProvider on submit; refresh the hub too so
                  // the new attempt appears in this screen's list.
                  ref.invalidate(myQuizzesAllProvider);
                }
              : null,
          icon: Icon(icon),
          label: Text(label),
        ),
      ),
    ]);
  }

  static String _reasonLabel(MyQuizRow row) {
    if (row.quiz.maxAttempts != null &&
        row.attemptsCount >= row.quiz.maxAttempts!) {
      return 'No attempts left';
    }
    return 'Not available';
  }

  static String _reasonHelp(MyQuizRow row) {
    if (row.quiz.maxAttempts != null &&
        row.attemptsCount >= row.quiz.maxAttempts!) {
      return 'You have used all ${row.quiz.maxAttempts} allowed attempts.';
    }
    return 'This quiz is not currently open. Check with your teacher for the window.';
  }
}
