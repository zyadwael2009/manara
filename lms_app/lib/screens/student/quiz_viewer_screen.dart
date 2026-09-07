import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/quiz.dart';
import '../../providers/enrollments_provider.dart';
import '../../providers/grading_providers.dart';
import '../../services/api_service.dart';
import 'widgets/quiz_results_view.dart';

/// Student flow: start → answer → submit → results.
///
/// Modes:
///  - `taking`: shows the questions, collects answers, timer if set.
///  - `results`: shows the graded attempt with per-question feedback.
class QuizViewerScreen extends ConsumerStatefulWidget {
  final String quizId;
  final String? courseTitle;
  const QuizViewerScreen({super.key, required this.quizId, this.courseTitle});

  @override
  ConsumerState<QuizViewerScreen> createState() => _QuizViewerScreenState();
}

class _QuizViewerScreenState extends ConsumerState<QuizViewerScreen> {
  QuizAttemptEnvelope? _env;
  bool _loading = true;
  String? _error;

  /// Per-question staged answer.
  /// - MC: `List<String>` of selected option ids
  /// - Short answer / essay: String
  final Map<String, dynamic> _answers = {};
  bool _submitting = false;

  Timer? _ticker;
  int _elapsedSeconds = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _start());
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  Future<void> _start() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final env = await ApiService.instance.startAttempt(widget.quizId);
      setState(() {
        _env = env;
        _loading = false;
      });
      if (env.quiz.timeLimitMinutes != null && env.attempt.submittedAt == null) {
        _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
          setState(() => _elapsedSeconds += 1);
          final limit = env.quiz.timeLimitMinutes! * 60;
          if (_elapsedSeconds >= limit) {
            _ticker?.cancel();
            _submit(auto: true);
          }
        });
      }
    } on ApiException catch (e) {
      setState(() {
        _loading = false;
        _error = e.message;
      });
    }
  }

  Future<void> _submit({bool auto = false}) async {
    if (_env == null || _submitting) return;
    // Simple validation: warn on unanswered required questions.
    if (!auto) {
      final missing = _env!.quiz.questions.where((q) {
        if (!q.required) return false;
        final a = _answers[q.id];
        if (a == null) return true;
        if (a is String) return a.trim().isEmpty;
        if (a is List) return a.isEmpty;
        return false;
      }).toList();
      if (missing.isNotEmpty) {
        final ok = await showDialog<bool>(
          context: context,
          builder: (d) => AlertDialog(
            title: const Text('Submit anyway?'),
            content: Text(
              '${missing.length} required question(s) still unanswered.',
              style: AppTextStyles.body(d),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Keep answering')),
              ElevatedButton(
                onPressed: () => Navigator.pop(d, true),
                style: ElevatedButton.styleFrom(backgroundColor: AppColors.warning),
                child: const Text('Submit anyway'),
              ),
            ],
          ),
        );
        if (ok != true) return;
      }
    }
    setState(() => _submitting = true);
    _ticker?.cancel();
    try {
      final answers = <Map<String, dynamic>>[];
      for (final q in _env!.quiz.questions) {
        final a = _answers[q.id];
        if (q.type == 'mc_single' || q.type == 'mc_multi' || q.type == 'true_false') {
          answers.add({
            'questionId': q.id,
            'selectedOptionIds': (a as List?)?.cast<String>() ?? const <String>[],
          });
        } else {
          answers.add({
            'questionId': q.id,
            'responseText': (a as String?)?.trim() ?? '',
          });
        }
      }
      final env = await ApiService.instance.submitAttempt(_env!.attempt.id, answers: answers);
      // Refresh dependent providers so My Classes + report card catch up.
      ref.invalidate(myEnrollmentsProvider);
      ref.invalidate(myReportCardProvider);
      if (!mounted) return;
      setState(() {
        _env = env;
        _submitting = false;
      });
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _submitting = false);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (widget.courseTitle != null)
              Text(widget.courseTitle!, style: AppTextStyles.h3(context)),
            if (_env != null)
              Text(_env!.quiz.title, style: AppTextStyles.caption(context)),
          ],
        ),
        actions: [
          if (_env != null && _env!.attempt.submittedAt == null && _env!.quiz.timeLimitMinutes != null)
            Center(child: Padding(
              padding: const EdgeInsetsDirectional.only(end: AppSpacing.md),
              child: _Timer(remainingSeconds: (_env!.quiz.timeLimitMinutes! * 60) - _elapsedSeconds),
            )),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.xl),
                  child: Text(_error!,
                      style: AppTextStyles.body(context, color: AppColors.danger),
                      textAlign: TextAlign.center),
                ))
              : _env == null
                  ? const Center(child: Text('No quiz loaded.'))
                  : _env!.attempt.submittedAt == null
                      ? _TakingBody(
                          env: _env!,
                          answers: _answers,
                          onChanged: () => setState(() {}),
                          submitting: _submitting,
                          onSubmit: () => _submit(auto: false),
                        )
                      : QuizResultsView(env: _env!),
    );
  }
}

// ============================================================================
// Timer chip
// ============================================================================
class _Timer extends StatelessWidget {
  final int remainingSeconds;
  const _Timer({required this.remainingSeconds});

  @override
  Widget build(BuildContext context) {
    final s = remainingSeconds < 0 ? 0 : remainingSeconds;
    final min = (s ~/ 60).toString().padLeft(2, '0');
    final sec = (s % 60).toString().padLeft(2, '0');
    final low = remainingSeconds < 60;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
      decoration: BoxDecoration(
        color: low ? AppColors.dangerSoft : AppColors.primarySoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.timer_outlined, size: 16, color: low ? AppColors.danger : AppColors.primary),
        const SizedBox(width: 4),
        Text('$min:$sec',
            style: TextStyle(
              fontWeight: FontWeight.w700, fontSize: 13,
              color: low ? AppColors.danger : AppColors.primary,
              fontFeatures: const [FontFeature.tabularFigures()],
            )),
      ]),
    );
  }
}

// ============================================================================
// Taking body
// ============================================================================
class _TakingBody extends StatelessWidget {
  final QuizAttemptEnvelope env;
  final Map<String, dynamic> answers;
  final VoidCallback onChanged;
  final bool submitting;
  final VoidCallback onSubmit;

  const _TakingBody({
    required this.env,
    required this.answers,
    required this.onChanged,
    required this.submitting,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Expanded(
        child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
          if (env.quiz.description.trim().isNotEmpty) ...[
            Text(env.quiz.description, style: AppTextStyles.body(context)),
            const SizedBox(height: AppSpacing.lg),
          ],
          for (int i = 0; i < env.quiz.questions.length; i++)
            _QuestionCard(
              index: i + 1,
              question: env.quiz.questions[i],
              answer: answers[env.quiz.questions[i].id],
              onAnswer: (v) {
                answers[env.quiz.questions[i].id] = v;
                onChanged();
              },
            ),
        ]),
      ),
      SafeArea(
        child: Container(
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surface,
            border: Border(top: BorderSide(color: AppColors.border)),
          ),
          child: SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton.icon(
              onPressed: submitting ? null : onSubmit,
              icon: submitting
                  ? const SizedBox(
                      height: 18, width: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.5,
                        valueColor: AlwaysStoppedAnimation(Colors.white),
                      ),
                    )
                  : const Icon(Icons.send_rounded),
              label: Text(submitting ? 'Submitting…' : 'Submit quiz'),
            ),
          ),
        ),
      ),
    ]);
  }
}

// ============================================================================
// One question card
// ============================================================================
class _QuestionCard extends StatelessWidget {
  final int index;
  final QuizQuestion question;
  final dynamic answer;
  final ValueChanged<dynamic> onAnswer;

  const _QuestionCard({
    required this.index,
    required this.question,
    required this.answer,
    required this.onAnswer,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.lg),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text('Q$index', style: AppTextStyles.micro(context, color: AppColors.primary)),
            const SizedBox(width: AppSpacing.sm),
            Text('· ${question.points} pt${question.points == 1 ? "" : "s"}',
                style: AppTextStyles.micro(context, color: AppColors.textMuted)),
            if (question.required) ...[
              const SizedBox(width: AppSpacing.sm),
              Text('· required',
                  style: AppTextStyles.micro(context, color: AppColors.textMuted)),
            ],
          ]),
          const SizedBox(height: AppSpacing.sm),
          Text(question.prompt, style: AppTextStyles.body(context)),
          const SizedBox(height: AppSpacing.md),
          _answerWidget(context),
        ]),
      ),
    );
  }

  Widget _answerWidget(BuildContext context) {
    switch (question.type) {
      case 'mc_single':
      case 'true_false':
        final selected = (answer as List<String>?)?.firstOrNull;
        return RadioGroup<String>(
          groupValue: selected,
          onChanged: (v) {
            if (v != null) onAnswer(<String>[v]);
          },
          child: Column(children: [
            for (final o in question.options)
              RadioListTile<String>(
                value: o.id,
                title: Text(o.text),
                contentPadding: EdgeInsets.zero,
                dense: true,
              ),
          ]),
        );
      case 'mc_multi':
        final selected = (answer as List<String>?) ?? const <String>[];
        return Column(children: [
          for (final o in question.options)
            CheckboxListTile(
              value: selected.contains(o.id),
              title: Text(o.text),
              contentPadding: EdgeInsets.zero,
              dense: true,
              controlAffinity: ListTileControlAffinity.leading,
              onChanged: (v) {
                final next = <String>[...selected];
                if (v == true) {
                  if (!next.contains(o.id)) next.add(o.id);
                } else {
                  next.remove(o.id);
                }
                onAnswer(next);
              },
            ),
        ]);
      case 'short_answer':
        return _TextAnswerField(
          key: ValueKey('sa-${question.id}'),
          initial: (answer as String?) ?? '',
          hint: 'Your answer',
          onChanged: onAnswer,
        );
      case 'essay':
        return _TextAnswerField(
          key: ValueKey('essay-${question.id}'),
          initial: (answer as String?) ?? '',
          hint: 'Type your answer here…',
          minLines: 4,
          maxLines: 6,
          onChanged: onAnswer,
        );
      default:
        return Text('Unsupported question type: ${question.type}',
            style: AppTextStyles.caption(context, color: AppColors.danger));
    }
  }
}

extension _FirstOrNull<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}

// ============================================================================
// Phase 17: the graded-attempt view (summary + per-question review) has been
// extracted into `widgets/quiz_results_view.dart` so the standalone attempt-
// review screen (reached from the Quizzes hub) can render the same UI. See
// the `QuizResultsView` reference in this screen's `build` method above.
// ============================================================================


// ============================================================================
// Phase 9 audit fix F13: Stateful text-answer field.
//
// Previous implementation was inline `TextField(controller: TextEditingController(text: answer))`
// in a StatelessWidget, which recreated the controller on every keystroke and
// pinned the cursor to the end — mid-word edits were impossible in essays.
// A dedicated StatefulWidget owns the controller across rebuilds.
// ============================================================================
class _TextAnswerField extends StatefulWidget {
  final String initial;
  final String hint;
  final int? minLines;
  final int? maxLines;
  final ValueChanged<String> onChanged;

  const _TextAnswerField({
    super.key,
    required this.initial,
    required this.hint,
    required this.onChanged,
    this.minLines,
    this.maxLines,
  });

  @override
  State<_TextAnswerField> createState() => _TextAnswerFieldState();
}

class _TextAnswerFieldState extends State<_TextAnswerField> {
  late final TextEditingController _ctrl;

  @override
  void initState() {
    super.initState();
    _ctrl = TextEditingController(text: widget.initial);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: _ctrl,
      minLines: widget.minLines,
      maxLines: widget.maxLines ?? 1,
      decoration: InputDecoration(
        hintText: widget.hint,
        alignLabelWithHint: widget.maxLines != null,
      ),
      onChanged: widget.onChanged,
    );
  }
}
