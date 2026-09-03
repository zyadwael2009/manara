import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/utils/transitions.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/assignment.dart';
import '../../providers/my_assignments_provider.dart';
import 'assignment_submit_screen.dart';

/// Phase 18 — the student "Assignments" hub. Every published assignment
/// across every course the student is enrolled in, split into three
/// tabs (Past due / Open / Upcoming) so the pile stays scannable.
///
/// Reached from the AppBar icon on My classes.
class MyAssignmentsScreen extends ConsumerWidget {
  const MyAssignmentsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(myAssignmentsAllProvider);
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        backgroundColor: AppColors.background,
        appBar: AppBar(
          title: Text('Assignments', style: AppTextStyles.h2(context)),
          bottom: TabBar(
            labelColor: AppColors.primary,
            unselectedLabelColor: AppColors.textMuted,
            indicatorColor: AppColors.primary,
            labelStyle: const TextStyle(fontWeight: FontWeight.w700),
            tabs: [
              _buildTab(async, 'Past due', _isPastDue, AppColors.danger),
              _buildTab(async, 'Open', _isOpen, AppColors.primary),
              _buildTab(async, 'Upcoming', _isUpcoming, AppColors.textMuted),
            ],
          ),
        ),
        body: RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(myAssignmentsAllProvider);
            await ref.read(myAssignmentsAllProvider.future);
          },
          child: async.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => ListView(children: [
              const SizedBox(height: 80),
              Center(child: Text(friendlyError(e))),
            ]),
            data: (rows) {
              if (rows.isEmpty) {
                return ListView(children: const [
                  SizedBox(height: 80),
                  EmptyState(
                    icon: Icons.assignment_outlined,
                    title: 'No assignments yet',
                    message:
                        "When a teacher publishes an assignment for one of your courses, it'll show up here.",
                  ),
                ]);
              }
              return TabBarView(children: [
                _AssignmentsList(
                  rows: rows.where(_isPastDue).toList(),
                  emptyMsg: 'Nothing past due. Good work.',
                ),
                _AssignmentsList(
                  rows: rows.where(_isOpen).toList(),
                  emptyMsg: 'Nothing open right now.',
                ),
                _AssignmentsList(
                  rows: rows.where(_isUpcoming).toList(),
                  emptyMsg: 'No upcoming assignments.',
                ),
              ]);
            },
          ),
        ),
      ),
    );
  }

  Widget _buildTab(AsyncValue<List<MyAssignmentRow>> async, String label,
      bool Function(MyAssignmentRow) filter, Color color) {
    final count = async.maybeWhen(
      data: (rows) => rows.where(filter).length,
      orElse: () => null,
    );
    return Tab(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label),
          if (count != null && count > 0) ...[
            const SizedBox(width: 6),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Text('$count',
                  style: TextStyle(
                      color: color, fontWeight: FontWeight.w700, fontSize: 11)),
            ),
          ],
        ],
      ),
    );
  }

  // Bucketing predicates — client-side over the full list.
  static bool _isPastDue(MyAssignmentRow r) => r.isPastDue;
  static bool _isOpen(MyAssignmentRow r) {
    final due = r.assignment.dueAt;
    if (due == null) return !r.isSubmitted; // no deadline = "open" until submitted
    // Open = due today or in the next 3 days AND not past due, OR submitted-but-ungraded stays here for visibility
    if (r.isPastDue) return false;
    if (r.isDueSoon) return true;
    if (r.isSubmitted && !r.isGraded) return true;
    return false;
  }

  static bool _isUpcoming(MyAssignmentRow r) {
    final due = r.assignment.dueAt;
    if (due == null) return false;
    if (r.isPastDue) return false;
    if (r.isDueSoon) return false;
    return due.isAfter(DateTime.now());
  }
}

class _AssignmentsList extends StatelessWidget {
  final List<MyAssignmentRow> rows;
  final String emptyMsg;
  const _AssignmentsList({required this.rows, required this.emptyMsg});

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return ListView(children: [
        const SizedBox(height: 80),
        Center(
          child: Text(emptyMsg,
              style: AppTextStyles.body(context, color: AppColors.textMuted)),
        ),
      ]);
    }
    // Group by course for scannability.
    final groups = <String, List<MyAssignmentRow>>{};
    for (final r in rows) {
      groups.putIfAbsent(r.course.title, () => []).add(r);
    }
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        for (final entry in groups.entries) ...[
          Padding(
            padding: const EdgeInsetsDirectional.only(start: 4, bottom: AppSpacing.sm),
            child: Row(children: [
              Container(
                width: 6,
                height: 6,
                decoration: const BoxDecoration(
                    shape: BoxShape.circle, color: AppColors.accent),
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(entry.key,
                  style: AppTextStyles.h3(context)
                      .copyWith(fontWeight: FontWeight.w700)),
            ]),
          ),
          for (final row in entry.value) _AssignmentCard(row: row),
          const SizedBox(height: AppSpacing.lg),
        ],
      ],
    );
  }
}

class _AssignmentCard extends StatelessWidget {
  final MyAssignmentRow row;
  const _AssignmentCard({required this.row});

  @override
  Widget build(BuildContext context) {
    final a = row.assignment;
    final due = a.dueAt;
    // Phase 33 fix #19 — collapse the card's Text/Icon soup into one
    // screen-reader node with the summary VoiceOver actually needs
    // ("Algebra II homework, due tomorrow, ungraded — double-tap to
    // open") instead of enumerating every widget inside.
    final srLabel = [
      'Assignment ${a.title}',
      'in ${row.course.title}',
      if (due != null) 'due ${due.toLocal().toString().split(" ").first}',
      if (row.isGraded) 'graded' else if (row.isSubmitted) 'submitted' else 'not submitted',
      'double-tap to open',
    ].join(', ');
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Semantics(
        button: true,
        container: true,
        label: srLabel,
        excludeSemantics: true,
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
              AssignmentSubmitScreen(assignmentId: a.id),
            ));
          },
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Expanded(
                    child: Text(a.title,
                        style: AppTextStyles.body(context)
                            .copyWith(fontWeight: FontWeight.w700)),
                  ),
                  _StatusBadge(row: row),
                ]),
                const SizedBox(height: 4),
                Text(row.moduleTitle,
                    style: AppTextStyles.caption(context,
                        color: AppColors.textMuted)),
                const SizedBox(height: AppSpacing.md),
                Row(children: [
                  Icon(Icons.event_outlined,
                      size: 14, color: _dueColor(row)),
                  const SizedBox(width: 4),
                  Text(_dueLabel(due, row),
                      style: AppTextStyles.caption(context,
                              color: _dueColor(row))
                          .copyWith(fontWeight: FontWeight.w600)),
                  const Spacer(),
                  Text('${a.maxPoints} pts',
                      style: AppTextStyles.caption(context,
                          color: AppColors.textMuted)),
                ]),
                if (row.isGraded) ...[
                  const SizedBox(height: AppSpacing.sm),
                  _GradeRow(row: row),
                ],
              ],
            ),
          ),
        ),
      ),
      ),
    );
  }

  static Color _dueColor(MyAssignmentRow r) {
    if (r.isPastDue) return AppColors.danger;
    if (r.isDueSoon) return AppColors.warning;
    return AppColors.textSecondary;
  }

  static String _dueLabel(DateTime? due, MyAssignmentRow r) {
    if (due == null) return 'No due date';
    final now = DateTime.now();
    final diff = due.difference(now);
    if (r.isSubmitted) {
      final s = r.assignment.mySubmission!;
      final d = s.submittedAt!;
      return 'Submitted ${_dateLabel(d)}${s.isLate ? " · late" : ""}';
    }
    if (r.isPastDue) return 'Overdue since ${_dateLabel(due)}';
    if (diff.inHours < 24) return 'Due today · ${_timeOnly(due)}';
    if (diff.inDays < 7) return 'Due ${_dateLabel(due)}';
    return 'Due ${_dateLabel(due)}';
  }

  static String _dateLabel(DateTime d) {
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return '${d.day} ${months[d.month - 1]}';
  }

  static String _timeOnly(DateTime d) =>
      '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
}

class _StatusBadge extends StatelessWidget {
  final MyAssignmentRow row;
  const _StatusBadge({required this.row});
  @override
  Widget build(BuildContext context) {
    late String label;
    late Color fg;
    late Color bg;
    if (row.isGraded) {
      label = 'Graded';
      fg = AppColors.success;
      bg = AppColors.successSoft;
    } else if (row.isSubmitted) {
      label = 'Awaiting grade';
      fg = AppColors.info;
      bg = AppColors.infoSoft;
    } else if (row.isPastDue) {
      label = 'Missing';
      fg = AppColors.danger;
      bg = AppColors.dangerSoft;
    } else if (row.isDueSoon) {
      label = 'Due soon';
      fg = AppColors.warning;
      bg = AppColors.warningSoft;
    } else {
      label = 'Not started';
      fg = AppColors.textSecondary;
      bg = AppColors.surfaceMuted;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(label,
          style:
              TextStyle(color: fg, fontWeight: FontWeight.w700, fontSize: 11)),
    );
  }
}

class _GradeRow extends StatelessWidget {
  final MyAssignmentRow row;
  const _GradeRow({required this.row});
  @override
  Widget build(BuildContext context) {
    final s = row.assignment.mySubmission!;
    final score = s.gradedScore ?? 0;
    final max = s.gradedMax ?? row.assignment.maxPoints.toDouble();
    final pct = max > 0 ? (score / max * 100.0).round() : 0;
    return Row(children: [
      const Icon(Icons.check_circle_rounded,
          size: 14, color: AppColors.success),
      const SizedBox(width: 4),
      Text('Score $pct%  ·  ${_trim(score)}/${_trim(max)}',
          style: AppTextStyles.caption(context, color: AppColors.success)
              .copyWith(fontWeight: FontWeight.w700)),
      if (s.gradedFeedback != null && s.gradedFeedback!.isNotEmpty) ...[
        const SizedBox(width: AppSpacing.sm),
        const Icon(Icons.comment_outlined,
            size: 12, color: AppColors.info),
        const SizedBox(width: 2),
        Flexible(
          child: Text(s.gradedFeedback!,
              overflow: TextOverflow.ellipsis,
              style: AppTextStyles.caption(context, color: AppColors.info)),
        ),
      ],
    ]);
  }

  static String _trim(double d) {
    if (d == d.roundToDouble()) return d.toInt().toString();
    return d.toStringAsFixed(1);
  }
}
