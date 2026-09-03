import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/friendly_error.dart';
import '../../../models/comm.dart';
import '../../../providers/auth_provider.dart';
import '../../../providers/comm_providers.dart';
import '../../../services/api_service.dart';

/// Phase 21 — Q&A panel appended to the bottom of a lesson body.
///
/// One deep: each question has 0+ answers. Anyone who can view the lesson
/// can post; teachers + admins render their name with an "answer" tag so
/// authoritative answers pop.
class LessonCommentsPanel extends ConsumerStatefulWidget {
  final String lessonId;
  const LessonCommentsPanel({super.key, required this.lessonId});

  @override
  ConsumerState<LessonCommentsPanel> createState() =>
      _LessonCommentsPanelState();
}

class _LessonCommentsPanelState extends ConsumerState<LessonCommentsPanel> {
  final _questionCtrl = TextEditingController();
  final Map<String, TextEditingController> _replyCtrls = {};
  bool _postingQuestion = false;
  final Set<String> _postingReplies = {};

  @override
  void dispose() {
    _questionCtrl.dispose();
    for (final c in _replyCtrls.values) {
      c.dispose();
    }
    super.dispose();
  }

  TextEditingController _replyCtrlFor(String qid) =>
      _replyCtrls.putIfAbsent(qid, () => TextEditingController());

  Future<void> _postQuestion() async {
    final body = _questionCtrl.text.trim();
    if (body.isEmpty || _postingQuestion) return;
    setState(() => _postingQuestion = true);
    try {
      await ApiService.instance.postLessonComment(
        lessonId: widget.lessonId, body: body,
      );
      _questionCtrl.clear();
      ref.invalidate(lessonCommentsProvider(widget.lessonId));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(friendlyError(e))));
    } finally {
      if (mounted) setState(() => _postingQuestion = false);
    }
  }

  Future<void> _postReply(String parentId) async {
    final ctrl = _replyCtrlFor(parentId);
    final body = ctrl.text.trim();
    if (body.isEmpty || _postingReplies.contains(parentId)) return;
    setState(() => _postingReplies.add(parentId));
    try {
      await ApiService.instance.postLessonComment(
        lessonId: widget.lessonId, body: body, parentCommentId: parentId,
      );
      ctrl.clear();
      ref.invalidate(lessonCommentsProvider(widget.lessonId));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(friendlyError(e))));
    } finally {
      if (mounted) setState(() => _postingReplies.remove(parentId));
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(lessonCommentsProvider(widget.lessonId));
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xxl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Divider(color: AppColors.divider),
          const SizedBox(height: AppSpacing.md),
          Text('QUESTIONS & ANSWERS',
              style: AppTextStyles.micro(context, color: AppColors.textMuted)
                  .copyWith(fontWeight: FontWeight.w800, letterSpacing: 0.8)),
          const SizedBox(height: AppSpacing.md),
          _AskRow(
            controller: _questionCtrl,
            busy: _postingQuestion,
            onSubmit: _postQuestion,
          ),
          const SizedBox(height: AppSpacing.lg),
          async.when(
            loading: () => const Padding(
              padding: EdgeInsets.all(AppSpacing.md),
              child: Center(child: CircularProgressIndicator()),
            ),
            error: (e, _) => Text(friendlyError(e),
                style:
                    AppTextStyles.caption(context, color: AppColors.danger)),
            data: (rows) {
              final questions = rows.where((c) => c.isQuestion).toList();
              if (questions.isEmpty) {
                return Text('No questions yet — be the first to ask.',
                    style: AppTextStyles.caption(context,
                        color: AppColors.textMuted));
              }
              final answersByParent = <String, List<LessonComment>>{};
              for (final c in rows.where((c) => !c.isQuestion)) {
                answersByParent
                    .putIfAbsent(c.parentCommentId!, () => [])
                    .add(c);
              }
              return Column(children: [
                for (final q in questions) ...[
                  _CommentTile(comment: q, isAnswer: false),
                  for (final a in answersByParent[q.id] ?? const [])
                    Padding(
                      padding:
                          const EdgeInsetsDirectional.only(start: AppSpacing.xl, top: 6),
                      child: _CommentTile(comment: a, isAnswer: true),
                    ),
                  _ReplyRow(
                    controller: _replyCtrlFor(q.id),
                    busy: _postingReplies.contains(q.id),
                    onSubmit: () => _postReply(q.id),
                  ),
                  const SizedBox(height: AppSpacing.lg),
                ],
              ]);
            },
          ),
        ],
      ),
    );
  }
}

class _AskRow extends StatelessWidget {
  final TextEditingController controller;
  final bool busy;
  final VoidCallback onSubmit;
  const _AskRow({
    required this.controller,
    required this.busy,
    required this.onSubmit,
  });
  @override
  Widget build(BuildContext context) {
    return Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
      Expanded(
        child: TextField(
          controller: controller,
          minLines: 1, maxLines: 3,
          decoration: const InputDecoration(
            hintText: 'Ask a question about this lesson…',
            border: OutlineInputBorder(),
            isDense: true,
          ),
        ),
      ),
      const SizedBox(width: AppSpacing.sm),
      SizedBox(
        height: 48,
        child: ElevatedButton(
          onPressed: busy ? null : onSubmit,
          child: busy
              ? const SizedBox(
                  height: 18, width: 18,
                  child: CircularProgressIndicator(
                      strokeWidth: 2.5,
                      valueColor: AlwaysStoppedAnimation(Colors.white)),
                )
              : const Text('Post'),
        ),
      ),
    ]);
  }
}

class _ReplyRow extends ConsumerWidget {
  final TextEditingController controller;
  final bool busy;
  final VoidCallback onSubmit;
  const _ReplyRow({
    required this.controller,
    required this.busy,
    required this.onSubmit,
  });
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final me = ref.watch(authProvider).user;
    // Anyone can answer; the tile-side "Teacher" label distinguishes
    // authoritative replies from peer replies.
    final hint = (me?.role == 'instructor' || me?.role == 'admin')
        ? 'Answer this question…'
        : 'Reply…';
    return Padding(
      padding: const EdgeInsetsDirectional.only(start: AppSpacing.xl, top: AppSpacing.sm),
      child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Expanded(
          child: TextField(
            controller: controller,
            minLines: 1, maxLines: 3,
            decoration: InputDecoration(
              hintText: hint,
              border: const OutlineInputBorder(),
              isDense: true,
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        OutlinedButton(
          onPressed: busy ? null : onSubmit,
          child: busy
              ? const SizedBox(
                  height: 14, width: 14,
                  child: CircularProgressIndicator(strokeWidth: 2.5),
                )
              : const Text('Reply'),
        ),
      ]),
    );
  }
}

class _CommentTile extends StatelessWidget {
  final LessonComment comment;
  final bool isAnswer;
  const _CommentTile({required this.comment, required this.isAnswer});
  @override
  Widget build(BuildContext context) {
    final isTeacher = comment.authorRole == 'instructor' ||
        comment.authorRole == 'admin';
    final tone = isTeacher ? AppColors.success : AppColors.textMuted;
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: isTeacher && isAnswer
            ? AppColors.successSoft
            : AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(comment.authorName ?? 'Someone',
              style: AppTextStyles.caption(context,
                      color: AppColors.textSecondary)
                  .copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(width: 6),
          if (isTeacher)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
              decoration: BoxDecoration(
                color: tone.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text(
                comment.authorRole == 'admin' ? 'Admin' : 'Teacher',
                style: TextStyle(
                    color: tone, fontWeight: FontWeight.w700, fontSize: 10),
              ),
            ),
          const Spacer(),
          Text(_ago(comment.createdAt),
              style: AppTextStyles.micro(context, color: AppColors.textMuted)),
        ]),
        const SizedBox(height: 4),
        Text(comment.body, style: AppTextStyles.body(context)),
      ]),
    );
  }

  static String _ago(DateTime? t) {
    if (t == null) return '';
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'now';
    if (d.inHours < 1) return '${d.inMinutes}m';
    if (d.inDays < 1) return '${d.inHours}h';
    if (d.inDays < 7) return '${d.inDays}d';
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return '${t.day} ${months[t.month - 1]}';
  }
}
