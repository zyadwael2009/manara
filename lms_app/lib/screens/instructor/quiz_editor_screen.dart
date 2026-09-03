import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../models/quiz.dart';
import '../../providers/quiz_providers.dart';
import '../../services/api_service.dart';
import 'quiz_attempts_screen.dart';
import '../../core/utils/friendly_error.dart';

/// Teacher's quiz editor. Cosmetic edits always allowed; the server refuses
/// structural changes (add/delete question, add/delete option, change
/// correctness) after any student attempts exist.
class QuizEditorScreen extends ConsumerWidget {
  final String quizId;
  const QuizEditorScreen({super.key, required this.quizId});

  void _reload(WidgetRef ref) => ref.invalidate(quizProvider(quizId));

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(quizProvider(quizId));
    return Scaffold(
      appBar: AppBar(
        title: async.maybeWhen(
          data: (q) => Text('Quiz — ${q.title}', style: AppTextStyles.h3(context)),
          orElse: () => const Text('Quiz'),
        ),
        actions: [
          async.maybeWhen(
            data: (q) => IconButton(
              tooltip: 'Attempts',
              icon: const Icon(Icons.people_alt_outlined),
              onPressed: () {
                Navigator.of(context).push(
                  fadeThroughRoute(QuizAttemptsScreen(quizId: q.id)),
                );
              },
            ),
            orElse: () => const SizedBox.shrink(),
          ),
          async.maybeWhen(
            data: (q) => TextButton.icon(
              onPressed: () async {
                try {
                  if (q.isPublished) {
                    await ApiService.instance.unpublishQuiz(q.id);
                  } else {
                    await ApiService.instance.publishQuiz(q.id);
                  }
                  _reload(ref);
                } on ApiException catch (e) {
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                  }
                }
              },
              icon: Icon(q.isPublished
                  ? Icons.pause_circle_outline_rounded
                  : Icons.rocket_launch_rounded),
              label: Text(q.isPublished ? 'Unpublish' : 'Publish'),
            ),
            orElse: () => const SizedBox.shrink(),
          ),
        ],
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (quiz) => _Body(quiz: quiz, onChanged: () => _reload(ref)),
      ),
      floatingActionButton: async.maybeWhen(
        data: (q) => FloatingActionButton.extended(
          onPressed: () => _addQuestion(context, q, ref),
          icon: const Icon(Icons.add),
          label: const Text('Add question'),
        ),
        orElse: () => null,
      ),
    );
  }

  Future<void> _addQuestion(BuildContext ctx, Quiz quiz, WidgetRef ref) async {
    final draft = await showModalBottomSheet<_QuestionDraft>(
      context: ctx,
      isScrollControlled: true,
      builder: (_) => const _QuestionEditorSheet(existing: null),
    );
    if (draft == null) return;
    try {
      final created = await ApiService.instance.createQuizQuestion(
        quiz.id,
        type: draft.type,
        prompt: draft.prompt,
        points: draft.points,
      );
      // Add options for MC types.
      if (draft.type == 'mc_single' || draft.type == 'mc_multi') {
        for (final o in draft.options) {
          await ApiService.instance.createQuizOption(
            created.id, text: o.$1, isCorrect: o.$2,
          );
        }
      } else if (draft.type == 'true_false') {
        // Server pre-creates True/False options; update the correctness flag.
        final full = await ApiService.instance.getQuiz(quiz.id);
        final q = full.questions.firstWhere((x) => x.id == created.id);
        final correctText = draft.options.isNotEmpty && draft.options.first.$2 ? 'True' : 'False';
        for (final o in q.options) {
          await ApiService.instance.updateQuizOption(o.id,
              {'isCorrect': o.text == correctText});
        }
      } else if (draft.type == 'short_answer') {
        for (final a in draft.acceptable) {
          await ApiService.instance.addAcceptableAnswer(created.id, text: a);
        }
      }
      _reload(ref);
    } on ApiException catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _Body extends StatelessWidget {
  final Quiz quiz;
  final VoidCallback onChanged;
  const _Body({required this.quiz, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(quiz.title, style: AppTextStyles.h2(context))),
              _StatusPill(published: quiz.isPublished),
            ]),
            const SizedBox(height: AppSpacing.sm),
            Wrap(spacing: AppSpacing.md, runSpacing: AppSpacing.xs, children: [
              _meta(context, 'Total', '${quiz.totalPoints} pts'),
              _meta(context, 'Pass', '${quiz.passingScore}%'),
              if (quiz.maxAttempts != null) _meta(context, 'Attempts', '${quiz.maxAttempts}'),
              if (quiz.timeLimitMinutes != null) _meta(context, 'Time', '${quiz.timeLimitMinutes} min'),
              _meta(context, 'Scoring', quiz.scoringMode),
            ]),
            if (quiz.description.trim().isNotEmpty) ...[
              const SizedBox(height: AppSpacing.md),
              Text(quiz.description, style: AppTextStyles.caption(context)),
            ],
          ]),
        ),
      ),
      const SizedBox(height: AppSpacing.lg),
      Text('${quiz.questions.length} question${quiz.questions.length == 1 ? "" : "s"}',
          style: AppTextStyles.micro(context, color: AppColors.textMuted)),
      const SizedBox(height: AppSpacing.sm),
      for (int i = 0; i < quiz.questions.length; i++)
        _QuestionRow(index: i + 1, question: quiz.questions[i], onChanged: onChanged),
      if (quiz.questions.isEmpty)
        Card(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Center(child: Text('No questions yet.',
                style: AppTextStyles.caption(context))),
          ),
        ),
      const SizedBox(height: AppSpacing.xxxl), // room for FAB
    ]);
  }

  Widget _meta(BuildContext context, String k, String v) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Text('$k: ', style: AppTextStyles.caption(context, color: AppColors.textMuted)),
      Text(v, style: AppTextStyles.bodyStrong(context)),
    ]);
  }
}

class _StatusPill extends StatelessWidget {
  final bool published;
  const _StatusPill({required this.published});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
      decoration: BoxDecoration(
        color: published ? AppColors.successSoft : AppColors.warningSoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(
        published ? 'PUBLISHED' : 'DRAFT',
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.6,
          color: published ? AppColors.success : AppColors.warning,
        ),
      ),
    );
  }
}

class _QuestionRow extends StatelessWidget {
  final int index;
  final QuizQuestion question;
  final VoidCallback onChanged;
  const _QuestionRow({required this.index, required this.question, required this.onChanged});

  IconData get _typeIcon => switch (question.type) {
        'mc_single' => Icons.radio_button_checked_rounded,
        'mc_multi' => Icons.check_box_rounded,
        'true_false' => Icons.rule_rounded,
        'short_answer' => Icons.short_text_rounded,
        'essay' => Icons.article_rounded,
        _ => Icons.help_outline_rounded,
      };

  String get _typeLabel => switch (question.type) {
        'mc_single' => 'MC (one)',
        'mc_multi' => 'MC (many)',
        'true_false' => 'True/False',
        'short_answer' => 'Short answer',
        'essay' => 'Essay',
        _ => question.type,
      };

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(_typeIcon, size: 18, color: AppColors.primary),
            const SizedBox(width: AppSpacing.sm),
            Text('Q$index · $_typeLabel · ${question.points} pt${question.points == 1 ? "" : "s"}',
                style: AppTextStyles.caption(context)),
            const Spacer(),
            IconButton(
              tooltip: 'Delete question',
              icon: const Icon(Icons.delete_outline_rounded, size: 20),
              color: AppColors.danger,
              onPressed: () async {
                try {
                  await ApiService.instance.deleteQuizQuestion(question.id);
                  onChanged();
                } on ApiException catch (e) {
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                  }
                }
              },
            ),
          ]),
          const SizedBox(height: AppSpacing.sm),
          Text(question.prompt, style: AppTextStyles.bodyStrong(context)),
          if (question.options.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            for (final o in question.options)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  Icon(
                    (o.isCorrect ?? false)
                        ? Icons.check_circle_rounded
                        : Icons.radio_button_unchecked,
                    size: 16,
                    color: (o.isCorrect ?? false) ? AppColors.success : AppColors.textMuted,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(child: Text(o.text, style: AppTextStyles.body(context))),
                ]),
              ),
          ],
          if (question.type == 'short_answer' &&
              (question.acceptableAnswers ?? []).isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Text('Accepted answers:',
                style: AppTextStyles.caption(context, color: AppColors.textMuted)),
            Wrap(spacing: AppSpacing.sm, children: [
              for (final a in question.acceptableAnswers!)
                Chip(
                  label: Text(a.text),
                  backgroundColor: AppColors.successSoft,
                  labelStyle: const TextStyle(color: AppColors.success, fontSize: 12),
                ),
            ]),
          ],
        ]),
      ),
    );
  }
}

// ============================================================================
// Question editor sheet
// ============================================================================
class _QuestionDraft {
  final String type;
  final String prompt;
  final int points;
  final List<(String, bool)> options; // (text, isCorrect)
  final List<String> acceptable;
  const _QuestionDraft({
    required this.type,
    required this.prompt,
    required this.points,
    this.options = const [],
    this.acceptable = const [],
  });
}

class _QuestionEditorSheet extends StatefulWidget {
  final QuizQuestion? existing;
  const _QuestionEditorSheet({required this.existing});
  @override
  State<_QuestionEditorSheet> createState() => _QuestionEditorSheetState();
}

class _QuestionEditorSheetState extends State<_QuestionEditorSheet> {
  String _type = 'mc_single';
  final _prompt = TextEditingController();
  final _points = TextEditingController(text: '1');

  // For MC: list of (controller, isCorrect)
  final List<(TextEditingController, ValueNotifier<bool>)> _options = [
    (TextEditingController(), ValueNotifier(false)),
    (TextEditingController(), ValueNotifier(false)),
  ];
  // For true/false — track which is correct (index 0 = True, 1 = False)
  int _tfCorrect = 0;
  // For short_answer: list of acceptable answer controllers.
  final List<TextEditingController> _acceptable = [TextEditingController()];

  @override
  void dispose() {
    _prompt.dispose();
    _points.dispose();
    for (final o in _options) {
      o.$1.dispose();
      o.$2.dispose();
    }
    for (final a in _acceptable) {
      a.dispose();
    }
    super.dispose();
  }

  void _save() {
    if (_prompt.text.trim().isEmpty) return;
    final points = int.tryParse(_points.text.trim()) ?? 1;
    List<(String, bool)> opts = const [];
    List<String> acc = const [];
    switch (_type) {
      case 'mc_single':
        opts = _options
            .where((o) => o.$1.text.trim().isNotEmpty)
            .map((o) => (o.$1.text.trim(), o.$2.value))
            .toList();
        // enforce single-correct: only the first correct one wins.
        var found = false;
        opts = [
          for (final o in opts)
            if (o.$2 && !found) ((){ found = true; return o; })() else (o.$1, false)
        ];
        // If nothing marked correct, mark first as correct so the quiz is answerable.
        if (!opts.any((o) => o.$2) && opts.isNotEmpty) {
          opts = [for (int i = 0; i < opts.length; i++) if (i == 0) (opts[i].$1, true) else opts[i]];
        }
        break;
      case 'mc_multi':
        opts = _options
            .where((o) => o.$1.text.trim().isNotEmpty)
            .map((o) => (o.$1.text.trim(), o.$2.value))
            .toList();
        break;
      case 'true_false':
        opts = [('True', _tfCorrect == 0), ('False', _tfCorrect == 1)];
        break;
      case 'short_answer':
        acc = _acceptable
            .map((c) => c.text.trim())
            .where((s) => s.isNotEmpty)
            .toList();
        break;
      case 'essay':
        // nothing
        break;
    }
    Navigator.of(context).pop(_QuestionDraft(
      type: _type,
      prompt: _prompt.text.trim(),
      points: points < 1 ? 1 : points,
      options: opts,
      acceptable: acc,
    ));
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: AppSpacing.xl,
          right: AppSpacing.xl,
          top: AppSpacing.xl,
          bottom: MediaQuery.of(context).viewInsets.bottom + AppSpacing.xl,
        ),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('New question', style: AppTextStyles.h2(context)),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                initialValue: _type,
                decoration: const InputDecoration(labelText: 'Type'),
                items: const [
                  DropdownMenuItem(value: 'mc_single', child: Text('Multiple choice — single correct')),
                  DropdownMenuItem(value: 'mc_multi', child: Text('Multiple choice — multiple correct')),
                  DropdownMenuItem(value: 'true_false', child: Text('True / false')),
                  DropdownMenuItem(value: 'short_answer', child: Text('Short answer')),
                  DropdownMenuItem(value: 'essay', child: Text('Essay')),
                ],
                onChanged: (v) => setState(() => _type = v ?? 'mc_single'),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _prompt,
                autofocus: true,
                maxLines: 3,
                minLines: 2,
                decoration: const InputDecoration(labelText: 'Question prompt'),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _points,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Points'),
              ),
              const SizedBox(height: AppSpacing.md),
              if (_type == 'mc_single' || _type == 'mc_multi') _mcOptionsUi(context),
              if (_type == 'true_false') _tfUi(),
              if (_type == 'short_answer') _shortUi(context),
              const SizedBox(height: AppSpacing.xl),
              Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
                const SizedBox(width: AppSpacing.sm),
                ElevatedButton(onPressed: _save, child: const Text('Save')),
              ]),
            ],
          ),
        ),
      ),
    );
  }

  Widget _mcOptionsUi(BuildContext context) {
    return Column(children: [
      Text('Options — check any correct answer(s)',
          style: AppTextStyles.caption(context, color: AppColors.textMuted)),
      const SizedBox(height: AppSpacing.sm),
      for (int i = 0; i < _options.length; i++)
        Row(children: [
          ValueListenableBuilder<bool>(
            valueListenable: _options[i].$2,
            builder: (_, v, __) => Checkbox(
              value: v,
              onChanged: (nv) {
                if (_type == 'mc_single' && (nv ?? false)) {
                  for (int j = 0; j < _options.length; j++) {
                    _options[j].$2.value = j == i;
                  }
                } else {
                  _options[i].$2.value = nv ?? false;
                }
              },
            ),
          ),
          Expanded(child: TextField(
            controller: _options[i].$1,
            decoration: const InputDecoration(hintText: 'Option text'),
          )),
          IconButton(
            tooltip: 'Remove option',
            icon: const Icon(Icons.remove_circle_outline, size: 20),
            onPressed: _options.length <= 2
                ? null
                : () => setState(() {
                      _options[i].$1.dispose();
                      _options[i].$2.dispose();
                      _options.removeAt(i);
                    }),
          ),
        ]),
      TextButton.icon(
        onPressed: () => setState(() => _options.add(
              (TextEditingController(), ValueNotifier(false)),
            )),
        icon: const Icon(Icons.add),
        label: const Text('Add option'),
      ),
    ]);
  }

  Widget _tfUi() {
    return Row(children: [
      Expanded(
        child: RadioListTile<int>(
          title: const Text('True is correct'),
          value: 0,
          groupValue: _tfCorrect,
          onChanged: (v) => setState(() => _tfCorrect = v ?? 0),
        ),
      ),
      Expanded(
        child: RadioListTile<int>(
          title: const Text('False is correct'),
          value: 1,
          groupValue: _tfCorrect,
          onChanged: (v) => setState(() => _tfCorrect = v ?? 1),
        ),
      ),
    ]);
  }

  Widget _shortUi(BuildContext context) {
    return Column(children: [
      Text('Accepted answers (case-insensitive)',
          style: AppTextStyles.caption(context, color: AppColors.textMuted)),
      const SizedBox(height: AppSpacing.sm),
      for (int i = 0; i < _acceptable.length; i++)
        Row(children: [
          Expanded(child: TextField(
            controller: _acceptable[i],
            decoration: const InputDecoration(hintText: 'Accepted answer'),
          )),
          IconButton(
            tooltip: 'Remove accepted answer',
            icon: const Icon(Icons.remove_circle_outline, size: 20),
            onPressed: _acceptable.length <= 1
                ? null
                : () => setState(() {
                      _acceptable[i].dispose();
                      _acceptable.removeAt(i);
                    }),
          ),
        ]),
      TextButton.icon(
        onPressed: () => setState(() => _acceptable.add(TextEditingController())),
        icon: const Icon(Icons.add),
        label: const Text('Add accepted answer'),
      ),
    ]);
  }
}
