import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../models/quiz.dart';

/// The read-only "graded attempt" view — summary card + per-question review.
///
/// Extracted from `QuizViewerScreen._ResultsBody` (Phase 17) so the same UI
/// renders after a submission AND on the standalone attempt-review screen
/// reached from the Quizzes hub. Zero behavior change vs the original.
class QuizResultsView extends StatelessWidget {
  final QuizAttemptEnvelope env;
  const QuizResultsView({super.key, required this.env});

  double get _percent =>
      env.attempt.maxScore == 0 ? 0 : (env.attempt.finalScore ?? 0) / env.attempt.maxScore * 100;

  @override
  Widget build(BuildContext context) {
    final answerByQ = {for (final a in env.attempt.answers) a.questionId: a};
    return ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
      _SummaryCard(percent: _percent, attempt: env.attempt),
      const SizedBox(height: AppSpacing.lg),
      for (int i = 0; i < env.quiz.questions.length; i++)
        _ReviewCard(
          index: i + 1,
          question: env.quiz.questions[i],
          answer: answerByQ[env.quiz.questions[i].id],
        ),
    ]);
  }
}

class _SummaryCard extends StatelessWidget {
  final double percent;
  final QuizAttempt attempt;
  const _SummaryCard({required this.percent, required this.attempt});

  @override
  Widget build(BuildContext context) {
    final passed = attempt.passed;
    final bgColor = passed ? AppColors.success : AppColors.danger;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [bgColor, bgColor.withValues(alpha: 0.75)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
      ),
      child: Row(children: [
        Icon(passed ? Icons.check_circle_rounded : Icons.info_outline,
            color: Colors.white, size: 48),
        const SizedBox(width: AppSpacing.lg),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(passed ? 'Passed' : 'Not yet passing',
                style: const TextStyle(
                    fontSize: 20, fontWeight: FontWeight.w800, color: Colors.white)),
            const SizedBox(height: 2),
            Text(
              '${(attempt.finalScore ?? 0).toStringAsFixed(1)} / ${attempt.maxScore.toStringAsFixed(1)} — ${percent.toStringAsFixed(1)}%',
              style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.w600),
            ),
            if (attempt.needsManualReview) ...[
              const SizedBox(height: AppSpacing.sm),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 2),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                ),
                child: const Text('Some questions pending teacher review',
                    style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
              ),
            ],
          ]),
        ),
      ]),
    );
  }
}

class _ReviewCard extends StatelessWidget {
  final int index;
  final QuizQuestion question;
  final QuizAnswerEntry? answer;
  const _ReviewCard({required this.index, required this.question, this.answer});

  @override
  Widget build(BuildContext context) {
    final scored = answer?.perQuestionScore;
    final isEssay = question.type == 'essay';
    final pending = isEssay && !(answer?.isManuallyGraded ?? false);
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text('Q$index', style: AppTextStyles.micro(context, color: AppColors.primary)),
            const Spacer(),
            _ScoreBadge(scored: scored, max: question.points, pending: pending),
          ]),
          const SizedBox(height: AppSpacing.sm),
          Text(question.prompt, style: AppTextStyles.body(context)),
          const SizedBox(height: AppSpacing.md),
          if (question.type == 'mc_single' ||
              question.type == 'mc_multi' ||
              question.type == 'true_false')
            _optionReview(context)
          else if (question.type == 'short_answer')
            _shortAnswerReview(context)
          else if (question.type == 'essay')
            _essayReview(context),
          if (answer?.manualFeedback != null && answer!.manualFeedback!.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: AppColors.infoSoft,
                borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
              ),
              child: Row(children: [
                const Icon(Icons.comment_outlined, color: AppColors.info),
                const SizedBox(width: AppSpacing.sm),
                Expanded(child: Text('Teacher: ${answer!.manualFeedback}',
                    style: AppTextStyles.caption(context))),
              ]),
            ),
          ],
        ]),
      ),
    );
  }

  Widget _optionReview(BuildContext context) {
    final selected = (answer?.selectedOptionIds ?? const <String>[]).toSet();
    return Column(children: [
      for (final o in question.options)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(children: [
            Icon(
              _iconForOption(selected.contains(o.id), o.isCorrect ?? false),
              color: _colorForOption(selected.contains(o.id), o.isCorrect ?? false),
              size: 18,
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(child: Text(o.text,
                style: AppTextStyles.body(context,
                    color: (o.isCorrect ?? false) ? AppColors.success : null))),
          ]),
        ),
    ]);
  }

  IconData _iconForOption(bool sel, bool correct) {
    if (sel && correct) return Icons.check_circle_rounded;
    if (sel && !correct) return Icons.cancel_rounded;
    if (!sel && correct) return Icons.circle_outlined;
    return Icons.circle_outlined;
  }

  Color _colorForOption(bool sel, bool correct) {
    if (sel && correct) return AppColors.success;
    if (sel && !correct) return AppColors.danger;
    if (!sel && correct) return AppColors.textMuted;
    return AppColors.border;
  }

  Widget _shortAnswerReview(BuildContext context) {
    final response = answer?.responseText ?? '';
    final acceptable = question.acceptableAnswers ?? const <AcceptableAnswer>[];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Your answer:', style: AppTextStyles.caption(context)),
      const SizedBox(height: 2),
      Text(response.isEmpty ? '(no answer)' : response,
          style: AppTextStyles.bodyStrong(context)),
      if (acceptable.isNotEmpty) ...[
        const SizedBox(height: AppSpacing.sm),
        Text('Accepted:', style: AppTextStyles.caption(context)),
        const SizedBox(height: 2),
        Wrap(spacing: AppSpacing.sm, children: [
          for (final a in acceptable)
            Chip(
              label: Text(a.text),
              backgroundColor: AppColors.successSoft,
              labelStyle: const TextStyle(color: AppColors.success, fontSize: 12),
            ),
        ]),
      ],
    ]);
  }

  Widget _essayReview(BuildContext context) {
    final response = answer?.responseText ?? '';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Your answer:', style: AppTextStyles.caption(context)),
      const SizedBox(height: 2),
      Text(response.isEmpty ? '(no answer)' : response,
          style: AppTextStyles.body(context)),
    ]);
  }
}

class _ScoreBadge extends StatelessWidget {
  final double? scored;
  final int max;
  final bool pending;
  const _ScoreBadge({required this.scored, required this.max, this.pending = false});

  @override
  Widget build(BuildContext context) {
    if (pending) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 3),
        decoration: BoxDecoration(
          color: AppColors.warningSoft,
          borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
        ),
        child: const Text('Pending review',
            style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.warning)),
      );
    }
    final s = scored ?? 0;
    final full = s >= max && max > 0;
    final zero = s == 0;
    final color = full ? AppColors.success : (zero ? AppColors.danger : AppColors.warning);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(
        '${s.toStringAsFixed(s == s.roundToDouble() ? 0 : 1)} / $max',
        style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color),
      ),
    );
  }
}
