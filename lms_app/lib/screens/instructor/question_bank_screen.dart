import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../models/gamify.dart';
import '../../providers/gamify_providers.dart';
import '../../services/api_service.dart';

/// Phase 24 — course-scoped question bank editor.
///
/// Reusable Q&A that teachers can adopt into any quiz in the same
/// course via the quiz editor's "Add from bank" flow. This screen only
/// authors the pool — adopt is triggered from the quiz editor.
class QuestionBankScreen extends ConsumerStatefulWidget {
  final String courseId;
  final String courseTitle;
  const QuestionBankScreen({
    super.key,
    required this.courseId,
    required this.courseTitle,
  });

  @override
  ConsumerState<QuestionBankScreen> createState() =>
      _QuestionBankScreenState();
}

class _QuestionBankScreenState extends ConsumerState<QuestionBankScreen> {
  Future<void> _openComposer() async {
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: _BankComposer(courseId: widget.courseId),
      ),
    );
    ref.invalidate(questionBankProvider(widget.courseId));
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(questionBankProvider(widget.courseId));
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Question bank', style: AppTextStyles.h3(context)),
            Text(widget.courseTitle,
                style: AppTextStyles.caption(context, color: AppColors.textMuted)),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openComposer,
        icon: const Icon(Icons.add_rounded),
        label: const Text('Add question'),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(questionBankProvider(widget.courseId));
          await ref.read(questionBankProvider(widget.courseId).future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text(friendlyError(e))),
          data: (items) {
            if (items.isEmpty) {
              return ListView(children: [
                const SizedBox(height: 80),
                Center(
                  child: Text(
                      "No questions in this course's bank yet.\nTap 'Add question' to build your first.",
                      textAlign: TextAlign.center,
                      style: AppTextStyles.body(context,
                          color: AppColors.textMuted)),
                ),
              ]);
            }
            return ListView.builder(
              padding: const EdgeInsets.all(AppSpacing.lg),
              itemCount: items.length,
              itemBuilder: (context, i) => _BankItemCard(
                item: items[i],
                onDelete: () async {
                  // Resolve the messenger BEFORE the await: `context` here is
                  // the itemBuilder's, which the list can rebuild out from
                  // under us, and the `mounted` check below is the State's,
                  // not that element's.
                  final messenger = ScaffoldMessenger.of(context);
                  try {
                    await ApiService.instance.deleteBankItem(items[i].id);
                    ref.invalidate(questionBankProvider(widget.courseId));
                  } on ApiException catch (e) {
                    messenger.showSnackBar(SnackBar(content: Text(e.message)));
                  }
                },
              ),
            );
          },
        ),
      ),
    );
  }
}

class _BankItemCard extends StatelessWidget {
  final QuestionBankItem item;
  final VoidCallback onDelete;
  const _BankItemCard({required this.item, required this.onDelete});
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
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.primarySoft,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(item.type,
                    style: TextStyle(
                        color: AppColors.primaryDark,
                        fontWeight: FontWeight.w700,
                        fontSize: 10)),
              ),
              const Spacer(),
              Text('${item.points} pt',
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
              IconButton(
                tooltip: 'Remove from bank',
                onPressed: onDelete,
                icon: const Icon(Icons.delete_outline_rounded,
                    size: 18, color: AppColors.textMuted),
                visualDensity: VisualDensity.compact,
              ),
            ]),
            const SizedBox(height: AppSpacing.sm),
            Text(item.prompt, style: AppTextStyles.body(context)),
            const SizedBox(height: AppSpacing.sm),
            for (final o in item.options)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(children: [
                  Icon(
                    o.isCorrect
                        ? Icons.check_circle_rounded
                        : Icons.circle_outlined,
                    size: 16,
                    color: o.isCorrect
                        ? AppColors.success
                        : AppColors.textMuted,
                  ),
                  const SizedBox(width: 6),
                  Text(o.text,
                      style: AppTextStyles.caption(context,
                          color: o.isCorrect
                              ? AppColors.success
                              : AppColors.textSecondary)),
                ]),
              ),
          ],
        ),
      ),
    );
  }
}

class _BankComposer extends ConsumerStatefulWidget {
  final String courseId;
  const _BankComposer({required this.courseId});
  @override
  ConsumerState<_BankComposer> createState() => _BankComposerState();
}

class _BankComposerState extends ConsumerState<_BankComposer> {
  final _prompt = TextEditingController();
  final _optCtrls = <TextEditingController>[
    TextEditingController(), TextEditingController(),
  ];
  final _correctIdx = ValueNotifier<int>(0);
  int _points = 1;
  bool _sending = false;

  @override
  void dispose() {
    _prompt.dispose();
    for (final c in _optCtrls) {
      c.dispose();
    }
    _correctIdx.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_prompt.text.trim().isEmpty || _sending) return;
    final options = <Map<String, dynamic>>[];
    for (int i = 0; i < _optCtrls.length; i++) {
      final t = _optCtrls[i].text.trim();
      if (t.isEmpty) continue;
      options.add({'text': t, 'isCorrect': i == _correctIdx.value});
    }
    if (options.length < 2) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Add at least 2 options.')));
      return;
    }
    setState(() => _sending = true);
    try {
      await ApiService.instance.createBankItem(
        courseId: widget.courseId,
        type: 'mc_single',
        prompt: _prompt.text.trim(),
        points: _points,
        options: options,
      );
      if (!mounted) return;
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _sending = false);
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
            AppSpacing.xl, AppSpacing.md, AppSpacing.xl, AppSpacing.xl),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Row(children: [
            Text('New bank question',
                style: AppTextStyles.h3(context)
                    .copyWith(fontWeight: FontWeight.w800)),
            const Spacer(),
            IconButton(
                tooltip: 'Close',
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.close_rounded)),
          ]),
          const SizedBox(height: AppSpacing.sm),
          TextField(
            controller: _prompt,
            minLines: 2, maxLines: 4, maxLength: 2000,
            decoration: const InputDecoration(
              labelText: 'Prompt',
              border: OutlineInputBorder(),
              alignLabelWithHint: true,
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          ValueListenableBuilder<int>(
            valueListenable: _correctIdx,
            builder: (context, correct, _) => RadioGroup<int>(
              groupValue: correct,
              onChanged: (v) => _correctIdx.value = v ?? 0,
              child: Column(children: [
                for (int i = 0; i < _optCtrls.length; i++)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(children: [
                      Radio<int>(value: i),
                      Expanded(
                        child: TextField(
                          controller: _optCtrls[i],
                          decoration: InputDecoration(
                            labelText: 'Option ${String.fromCharCode(65 + i)}',
                            border: const OutlineInputBorder(),
                            isDense: true,
                          ),
                        ),
                      ),
                    ]),
                  ),
              ]),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () {
                setState(() => _optCtrls.add(TextEditingController()));
              },
              icon: const Icon(Icons.add_rounded),
              label: const Text('Add option'),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            Text('Points:',
                style: AppTextStyles.caption(context, color: AppColors.textMuted)),
            const SizedBox(width: AppSpacing.sm),
            DropdownButton<int>(
              value: _points,
              items: const [
                DropdownMenuItem(value: 1, child: Text('1')),
                DropdownMenuItem(value: 2, child: Text('2')),
                DropdownMenuItem(value: 3, child: Text('3')),
                DropdownMenuItem(value: 5, child: Text('5')),
                DropdownMenuItem(value: 10, child: Text('10')),
              ],
              onChanged: (v) => setState(() => _points = v ?? 1),
            ),
          ]),
          const SizedBox(height: AppSpacing.md),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton.icon(
              onPressed: _sending ? null : _submit,
              icon: _sending
                  ? const SizedBox(
                      height: 18, width: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.5,
                        valueColor: AlwaysStoppedAnimation(Colors.white),
                      ),
                    )
                  : const Icon(Icons.check_rounded),
              label: Text(_sending ? 'Saving…' : 'Save question'),
            ),
          ),
        ]),
      ),
    );
  }
}
