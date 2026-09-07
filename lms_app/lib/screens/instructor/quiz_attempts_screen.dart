import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../models/quiz.dart';
import '../../providers/announcements_provider.dart';
import '../../providers/enrollments_provider.dart';
import '../../providers/grading_providers.dart';
import '../../providers/quiz_providers.dart';
import '../../services/api_service.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/trailing_chevron.dart';

/// List of every student's attempts on a quiz. Tap an attempt → detail view
/// with per-question inline override + total-score override.
class QuizAttemptsScreen extends ConsumerWidget {
  final String quizId;
  const QuizAttemptsScreen({super.key, required this.quizId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(quizAttemptsProvider(quizId));
    return Scaffold(
      appBar: AppBar(title: Text('Attempts', style: AppTextStyles.h3(context))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (rows) {
          if (rows.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.xl),
                child: Text('No attempts yet.',
                    style: AppTextStyles.caption(context, color: AppColors.textMuted)),
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(quizAttemptsProvider(quizId));
              ref.invalidate(quizAttemptStatsProvider(quizId));
            },
            child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
              // Phase 19 — class-average band at the top so the teacher
              // can triage before diving into per-student rows.
              _StatsBand(quizId: quizId),
              const SizedBox(height: AppSpacing.md),
              for (final a in rows) _AttemptRow(attempt: a),
            ]),
          );
        },
      ),
    );
  }
}

class _AttemptRow extends StatelessWidget {
  final QuizAttempt attempt;
  const _AttemptRow({required this.attempt});

  @override
  Widget build(BuildContext context) {
    final passed = attempt.passed;
    final percent = attempt.maxScore == 0 ? 0 : (attempt.finalScore ?? 0) / attempt.maxScore * 100;
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: passed ? AppColors.successSoft : AppColors.dangerSoft,
          child: Text(
            attempt.studentName?.isNotEmpty == true ? attempt.studentName![0] : '?',
            style: TextStyle(
              color: passed ? AppColors.success : AppColors.danger,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        title: Text(attempt.studentName ?? attempt.studentEmail ?? '—',
            style: AppTextStyles.bodyStrong(context)),
        subtitle: Text(
          'Attempt ${attempt.attemptNumber} · ${attempt.submittedAt == null ? "In progress" : "${percent.toStringAsFixed(1)}%"}',
          style: AppTextStyles.caption(context),
        ),
        trailing: Wrap(spacing: AppSpacing.sm, children: [
          if (attempt.needsManualReview)
            const Chip(
              label: Text('Needs review', style: TextStyle(fontSize: 10)),
              backgroundColor: AppColors.warningSoft,
              labelStyle: TextStyle(color: AppColors.warning),
            ),
          const TrailingChevron(),
        ]),
        onTap: () {
          Navigator.of(context).push(
            fadeThroughRoute(_AttemptDetailScreen(attemptId: attempt.id)),
          );
        },
      ),
    );
  }
}

// ============================================================================
// One attempt — with override
// ============================================================================
class _AttemptDetailScreen extends ConsumerStatefulWidget {
  final String attemptId;
  const _AttemptDetailScreen({required this.attemptId});
  @override
  ConsumerState<_AttemptDetailScreen> createState() => _AttemptDetailScreenState();
}

class _AttemptDetailScreenState extends ConsumerState<_AttemptDetailScreen> {
  final _final = TextEditingController();
  final _reason = TextEditingController();
  final Map<String, TextEditingController> _perQ = {};
  bool _saving = false;

  @override
  void dispose() {
    _final.dispose();
    _reason.dispose();
    for (final c in _perQ.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _override(String attemptId) async {
    final f = double.tryParse(_final.text.trim());
    if (f == null) return;
    setState(() => _saving = true);
    try {
      final per = <Map<String, dynamic>>[];
      _perQ.forEach((qid, ctrl) {
        final v = double.tryParse(ctrl.text.trim());
        if (v != null) per.add({'questionId': qid, 'score': v});
      });
      await ApiService.instance.overrideAttemptScore(
        attemptId,
        finalScore: f,
        reason: _reason.text.trim().isEmpty ? null : _reason.text.trim(),
        perQuestionScores: per.isEmpty ? null : per,
      );
      ref.invalidate(attemptProvider(attemptId));
      ref.invalidate(quizAttemptsProvider(_currentQuizId()));
      ref.invalidate(myEnrollmentsProvider);
      ref.invalidate(myReportCardProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Override saved.')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  String _currentQuizId() {
    final env = ref.read(attemptProvider(widget.attemptId)).asData?.value;
    return env?.quiz.id ?? '';
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(attemptProvider(widget.attemptId));
    return Scaffold(
      appBar: AppBar(title: Text('Attempt review', style: AppTextStyles.h3(context))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (env) {
          if (_final.text.isEmpty && env.attempt.finalScore != null) {
            _final.text = env.attempt.finalScore.toString();
          }
          final answers = {for (final a in env.attempt.answers) a.questionId: a};
          return ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
            _StudentHeaderCard(env: env),
            const SizedBox(height: AppSpacing.lg),
            for (int i = 0; i < env.quiz.questions.length; i++)
              _QuestionReviewCard(
                index: i + 1,
                question: env.quiz.questions[i],
                answer: answers[env.quiz.questions[i].id],
                perQ: _perQ,
              ),
            const SizedBox(height: AppSpacing.lg),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Override final score', style: AppTextStyles.h3(context)),
                  const SizedBox(height: AppSpacing.md),
                  Row(children: [
                    Expanded(child: TextField(
                      controller: _final,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      decoration: InputDecoration(
                        labelText: 'Final score',
                        suffixText: '/ ${env.attempt.maxScore.toStringAsFixed(1)}',
                      ),
                    )),
                    const SizedBox(width: AppSpacing.md),
                    ElevatedButton(
                      onPressed: _saving ? null : () => _override(env.attempt.id),
                      child: Text(_saving ? 'Saving…' : 'Save'),
                    ),
                  ]),
                  const SizedBox(height: AppSpacing.md),
                  TextField(
                    controller: _reason,
                    decoration: const InputDecoration(labelText: 'Reason (optional)'),
                  ),
                ]),
              ),
            ),
          ]);
        },
      ),
    );
  }
}

class _StudentHeaderCard extends StatelessWidget {
  final QuizAttemptEnvelope env;
  const _StudentHeaderCard({required this.env});

  @override
  Widget build(BuildContext context) {
    final percent = env.attempt.maxScore == 0 ? 0 : (env.attempt.finalScore ?? 0) / env.attempt.maxScore * 100;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Row(children: [
          CircleAvatar(
            backgroundColor: AppColors.primary,
            child: Text(
              env.attempt.studentName?.isNotEmpty == true ? env.attempt.studentName![0] : '?',
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(env.attempt.studentName ?? env.attempt.studentEmail ?? '—',
                style: AppTextStyles.bodyStrong(context)),
            Text('Attempt ${env.attempt.attemptNumber} · ${env.quiz.title}',
                style: AppTextStyles.caption(context)),
          ])),
          Text('${percent.toStringAsFixed(1)}%',
              style: AppTextStyles.h2(context,
                  color: env.attempt.passed ? AppColors.success : AppColors.danger)),
        ]),
      ),
    );
  }
}

class _QuestionReviewCard extends StatelessWidget {
  final int index;
  final QuizQuestion question;
  final QuizAnswerEntry? answer;
  final Map<String, TextEditingController> perQ;
  const _QuestionReviewCard({
    required this.index,
    required this.question,
    required this.answer,
    required this.perQ,
  });

  @override
  Widget build(BuildContext context) {
    perQ.putIfAbsent(
      question.id,
      () => TextEditingController(
        text: answer?.perQuestionScore == null ? '' : '${answer!.perQuestionScore}',
      ),
    );
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text('Q$index', style: AppTextStyles.micro(context, color: AppColors.primary)),
            const Spacer(),
            SizedBox(
              width: 70,
              child: TextField(
                controller: perQ[question.id],
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                textAlign: TextAlign.center,
                decoration: InputDecoration(
                  isDense: true,
                  suffixText: '/ ${question.points}',
                  contentPadding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                ),
              ),
            ),
          ]),
          const SizedBox(height: AppSpacing.sm),
          Text(question.prompt, style: AppTextStyles.body(context)),
          const SizedBox(height: AppSpacing.md),
          _answerReview(context),
        ]),
      ),
    );
  }

  Widget _answerReview(BuildContext context) {
    if (answer == null) {
      return Text('(no answer submitted)',
          style: AppTextStyles.caption(context, color: AppColors.textMuted));
    }
    if (question.type == 'essay' || question.type == 'short_answer') {
      return Text(answer!.responseText ?? '(no answer)',
          style: AppTextStyles.body(context));
    }
    final selected = answer!.selectedOptionIds.toSet();
    return Column(children: [
      for (final o in question.options)
        Row(children: [
          Icon(
            selected.contains(o.id)
                ? ((o.isCorrect ?? false) ? Icons.check_circle_rounded : Icons.cancel_rounded)
                : Icons.circle_outlined,
            size: 16,
            color: selected.contains(o.id)
                ? ((o.isCorrect ?? false) ? AppColors.success : AppColors.danger)
                : AppColors.textMuted,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(child: Text(o.text, style: AppTextStyles.body(context))),
        ]),
    ]);
  }
}

/// Phase 19 — top-of-screen class-average band on the attempts list.
/// Watches `quizAttemptStatsProvider` so it refreshes independently of
/// the roster provider on pull-to-refresh.
class _StatsBand extends ConsumerWidget {
  final String quizId;
  const _StatsBand({required this.quizId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(quizAttemptStatsProvider(quizId));
    return async.when(
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
      data: (s) {
        if (!s.hasSubmissions) {
          return _bareContainer(
            child: Text(
              s.count == 0
                  ? 'No attempts yet.'
                  : '${s.count} attempt${s.count == 1 ? "" : "s"} started · none submitted yet.',
              style: AppTextStyles.caption(context, color: AppColors.textMuted),
            ),
          );
        }
        return _bareContainer(
          child: Row(children: [
            _stat(context, 'Avg', '${s.avgPercent!.round()}%',
                _colorForPct(s.avgPercent!)),
            _sep(),
            _stat(context, 'Min', '${s.minPercent!.round()}%',
                AppColors.danger),
            _sep(),
            _stat(context, 'Max', '${s.maxPercent!.round()}%',
                AppColors.success),
            _sep(),
            _stat(context, 'Passed',
                '${s.passRate!.round()}%',
                _colorForPct(s.passRate!)),
            _sep(),
            _stat(context, 'Submitted',
                '${s.submittedCount}/${s.count}',
                AppColors.textPrimary),
          ]),
        );
      },
    );
  }

  Widget _bareContainer({required Widget child}) => Container(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg, vertical: AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.primarySoft,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
        child: child,
      );

  Widget _sep() => Container(
        width: 1,
        height: 28,
        margin: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
        color: AppColors.border,
      );

  Widget _stat(BuildContext ctx, String label, String value, Color color) =>
      Expanded(
        child: Column(children: [
          Text(value,
              style: TextStyle(
                  color: color, fontWeight: FontWeight.w800, fontSize: 16)),
          const SizedBox(height: 2),
          Text(label.toUpperCase(),
              style: AppTextStyles.micro(ctx, color: AppColors.textMuted)
                  .copyWith(letterSpacing: 0.6, fontWeight: FontWeight.w700)),
        ]),
      );

  Color _colorForPct(double pct) {
    if (pct >= 80) return AppColors.success;
    if (pct >= 60) return AppColors.primary;
    if (pct >= 40) return AppColors.warning;
    return AppColors.danger;
  }
}
