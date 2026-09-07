import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/assignment.dart';
import '../../providers/assignments_provider.dart';
import '../../services/api_service.dart';

class AssignmentGradingScreen extends ConsumerWidget {
  final String assignmentId;
  final String assignmentTitle;
  final int maxPoints;
  const AssignmentGradingScreen({
    super.key,
    required this.assignmentId,
    required this.assignmentTitle,
    required this.maxPoints,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(assignmentSubmissionsProvider(assignmentId));
    return Scaffold(
      appBar: AppBar(title: Text(assignmentTitle, style: AppTextStyles.h3(context))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (subs) {
          final ungraded = subs.where((s) => !s.isGraded).length;
          if (subs.isEmpty) {
            return const EmptyState(
              icon: Icons.inbox_outlined,
              title: 'No submissions yet',
              message: 'Students will appear here once they submit.',
            );
          }
          return Column(children: [
            _SummaryHeader(total: subs.length, ungraded: ungraded, maxPoints: maxPoints),
            const Divider(height: 1, color: AppColors.divider),
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
                itemCount: subs.length,
                separatorBuilder: (_, _) => const SizedBox(height: 4),
                itemBuilder: (context, i) => _SubmissionRow(
                  sub: subs[i],
                  maxPoints: maxPoints,
                  onGrade: (score, feedback) async {
                    try {
                      await ApiService.instance.gradeSubmission(
                        subs[i].id, score: score, feedback: feedback,
                      );
                      ref.invalidate(assignmentSubmissionsProvider(assignmentId));
                    } on ApiException catch (e) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context)
                            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
                      }
                    }
                  },
                ),
              ),
            ),
          ]);
        },
      ),
    );
  }
}

class _SummaryHeader extends StatelessWidget {
  final int total;
  final int ungraded;
  final int maxPoints;
  const _SummaryHeader({
    required this.total,
    required this.ungraded,
    required this.maxPoints,
  });
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      color: AppColors.surface,
      child: Row(children: [
        _Stat(label: 'Submissions', value: '$total'),
        const SizedBox(width: AppSpacing.xl),
        _Stat(
            label: 'Ungraded',
            value: '$ungraded',
            color: ungraded > 0 ? AppColors.warning : AppColors.success),
        const Spacer(),
        Text('out of $maxPoints pts',
            style: AppTextStyles.caption(context, color: AppColors.textMuted)),
      ]),
    );
  }
}

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;
  const _Stat({required this.label, required this.value, this.color});
  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: color ?? AppColors.textPrimary,
                fontFeatures: const [FontFeature.tabularFigures()],
              )),
          Text(label,
              style: AppTextStyles.micro(context, color: AppColors.textMuted)),
        ],
      );
}

class _SubmissionRow extends StatelessWidget {
  final AssignmentSubmission sub;
  final int maxPoints;
  final Future<void> Function(double score, String? feedback) onGrade;
  const _SubmissionRow({
    required this.sub,
    required this.maxPoints,
    required this.onGrade,
  });

  @override
  Widget build(BuildContext context) {
    final preview = sub.responseText != null && sub.responseText!.isNotEmpty
        ? sub.responseText!.length > 160
            ? '${sub.responseText!.substring(0, 160)}…'
            : sub.responseText!
        : (sub.fileUrl != null ? '📎 ${sub.fileUrl!.split("/").last}' : '(empty)');
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: 4),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        onTap: () => _openGradeDialog(context),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(
                  child: Text(sub.studentName ?? '—',
                      style: AppTextStyles.bodyStrong(context)),
                ),
                if (sub.isLate)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.warningSoft,
                      borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                    ),
                    child: Text('LATE',
                        style: AppTextStyles.micro(context, color: AppColors.warning)),
                  ),
                const SizedBox(width: 6),
                if (sub.isGraded)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.successSoft,
                      borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                    ),
                    child: Text(
                      '${sub.gradedScore!.toStringAsFixed(0)}/${(sub.gradedMax ?? maxPoints).toStringAsFixed(0)}',
                      style: AppTextStyles.micro(context, color: AppColors.success),
                    ),
                  )
                else
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.primarySoft,
                      borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                    ),
                    child: Text('Grade',
                        style: AppTextStyles.micro(context, color: AppColors.primaryDark)),
                  ),
              ]),
              if (sub.submittedAt != null)
                Text(
                  'Submitted ${DateFormat.yMMMd().add_jm().format(sub.submittedAt!.toLocal())}',
                  style: AppTextStyles.micro(context, color: AppColors.textMuted),
                ),
              const SizedBox(height: 6),
              Text(preview,
                  style: AppTextStyles.body(context, color: AppColors.textSecondary),
                  overflow: TextOverflow.ellipsis,
                  maxLines: 3),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _openGradeDialog(BuildContext ctx) async {
    final scoreCtrl = TextEditingController(
        text: sub.gradedScore?.toStringAsFixed(0) ?? '');
    final feedbackCtrl = TextEditingController(text: sub.gradedFeedback ?? '');
    try {
      final r = await showDialog<({double score, String? feedback})>(
        context: ctx,
        builder: (d) => AlertDialog(
          title: Text('Grade ${sub.studentName ?? "submission"}'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            if (sub.responseText != null && sub.responseText!.isNotEmpty)
              Container(
                constraints: const BoxConstraints(maxHeight: 200),
                child: SingleChildScrollView(
                  child: Text(sub.responseText!,
                      style: AppTextStyles.body(ctx, color: AppColors.textSecondary)),
                ),
              ),
            if (sub.fileUrl != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Row(children: [
                const Icon(Icons.attach_file_rounded, size: 16, color: AppColors.primary),
                const SizedBox(width: 6),
                Expanded(
                  child: SelectableText(sub.fileUrl!,
                      style: AppTextStyles.micro(ctx, color: AppColors.primaryDark)),
                ),
              ]),
            ],
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: scoreCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(
                labelText: 'Score (0 – $maxPoints)',
                border: const OutlineInputBorder(),
              ),
              autofocus: true,
            ),
            const SizedBox(height: AppSpacing.sm),
            TextField(
              controller: feedbackCtrl,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: 'Feedback (optional)',
                border: OutlineInputBorder(),
              ),
            ),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
            ElevatedButton(
              onPressed: () {
                final n = double.tryParse(scoreCtrl.text.trim());
                if (n == null || n < 0 || n > maxPoints) return;
                Navigator.pop(d, (
                  score: n,
                  feedback: feedbackCtrl.text.trim().isEmpty
                      ? null
                      : feedbackCtrl.text.trim(),
                ));
              },
              child: const Text('Save'),
            ),
          ],
        ),
      );
      if (r != null) await onGrade(r.score, r.feedback);
    } finally {
      scoreCtrl.dispose();
      feedbackCtrl.dispose();
    }
  }
}
