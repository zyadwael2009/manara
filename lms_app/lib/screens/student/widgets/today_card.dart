import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/utils/transitions.dart';
import '../../../models/quiz.dart';
import '../../../models/today.dart';
import '../../../providers/today_provider.dart';
import '../assignment_submit_screen.dart';
import '../quiz_history_screen.dart';
import '../../../core/widgets/trailing_chevron.dart';
import '../../../core/widgets/silent_error.dart';

/// Phase 18 — inline card at the top of the student's My classes screen.
///
/// Silent on weekends / empty days. Shows three short rows when there's
/// anything worth attention today:
///   • the periods still coming up in the class schedule
///   • assignments due today
///   • open quizzes with attempts still available
class TodayCard extends ConsumerWidget {
  const TodayCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(todayProvider);
    // (Phase 26 · T9 — SilentError below turns the previous silent
    // shrink() into a visible "couldn't load — tap to retry" chip.)
    return async.when(
      loading: () => const SizedBox.shrink(),
      error: (_, __) => SilentError(
        onRetry: () => ref.invalidate(todayProvider),
      ),
      data: (t) {
        if (t.isEmpty) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.lg),
          child: Container(
            padding: const EdgeInsets.all(AppSpacing.lg),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [AppColors.primary, AppColors.primaryDark],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  const Icon(Icons.wb_sunny_outlined,
                      color: Colors.white, size: 18),
                  const SizedBox(width: AppSpacing.sm),
                  Text('TODAY',
                      style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w800,
                          fontSize: 11,
                          letterSpacing: 1.2)),
                  const SizedBox(width: AppSpacing.md),
                  Text(_prettyDate(t.date),
                      style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.85),
                          fontWeight: FontWeight.w500,
                          fontSize: 12)),
                ]),
                if (t.periods.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.md),
                  _SectionLabel(
                      icon: Icons.event_note_outlined,
                      text:
                          '${t.periods.length} period${t.periods.length == 1 ? "" : "s"} today'),
                  const SizedBox(height: 4),
                  for (final p in t.periods.take(3))
                    _PeriodRow(
                      time: p.startTime,
                      title: p.course?.title ??
                          (p.note != null && p.note!.isNotEmpty
                              ? p.note!
                              : 'Free period'),
                      room: p.room,
                    ),
                  if (t.periods.length > 3)
                    Padding(
                      padding: const EdgeInsetsDirectional.only(start: 22, top: 2),
                      child: Text('+ ${t.periods.length - 3} more',
                          style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.7),
                              fontSize: 11)),
                    ),
                ],
                if (t.assignmentsDueToday.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.md),
                  _SectionLabel(
                      icon: Icons.assignment_late_outlined,
                      text: 'Due today · ${t.assignmentsDueToday.length}'),
                  const SizedBox(height: 4),
                  for (final a in t.assignmentsDueToday.take(3))
                    _AssignmentRow(assignment: a),
                ],
                if (t.openQuizzes.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.md),
                  _SectionLabel(
                      icon: Icons.quiz_outlined,
                      text: 'Open quizzes · ${t.openQuizzes.length}'),
                  const SizedBox(height: 4),
                  for (final q in t.openQuizzes.take(3))
                    _QuizRow(quiz: q),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  static String _prettyDate(String iso) {
    final t = DateTime.tryParse(iso);
    if (t == null) return '';
    const days = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return '${days[t.weekday - 1]}, ${t.day} ${months[t.month - 1]}';
  }
}

class _SectionLabel extends StatelessWidget {
  final IconData icon;
  final String text;
  const _SectionLabel({required this.icon, required this.text});
  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Icon(icon, size: 14, color: Colors.white.withValues(alpha: 0.85)),
      const SizedBox(width: 6),
      Text(text.toUpperCase(),
          style: TextStyle(
              color: Colors.white.withValues(alpha: 0.85),
              fontWeight: FontWeight.w700,
              fontSize: 11,
              letterSpacing: 0.7)),
    ]);
  }
}

class _PeriodRow extends StatelessWidget {
  final String time;
  final String title;
  final String? room;
  const _PeriodRow({required this.time, required this.title, this.room});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(children: [
        const SizedBox(width: 20),
        SizedBox(
          width: 44,
          child: Text(time,
              style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  fontSize: 12,
                  fontFeatures: [FontFeature.tabularFigures()])),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(title,
              style: const TextStyle(color: Colors.white, fontSize: 13),
              overflow: TextOverflow.ellipsis),
        ),
        if (room != null && room!.isNotEmpty)
          Text('R.$room',
              style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.7), fontSize: 12)),
      ]),
    );
  }
}

class _AssignmentRow extends StatelessWidget {
  final TodayAssignment assignment;
  const _AssignmentRow({required this.assignment});
  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () {
        Navigator.of(context).push(fadeThroughRoute(
          AssignmentSubmitScreen(assignmentId: assignment.id),
        ));
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 20),
        child: Row(children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(assignment.title,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 13),
                    overflow: TextOverflow.ellipsis),
                Text(assignment.courseTitle,
                    style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.75),
                        fontSize: 11)),
              ],
            ),
          ),
          Text(_timeOnly(assignment.dueAt),
              style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.85),
                  fontWeight: FontWeight.w600,
                  fontSize: 12)),
          const SizedBox(width: 4),
          const TrailingChevron(color: Colors.white, size: 18),
        ]),
      ),
    );
  }

  static String _timeOnly(DateTime? d) {
    if (d == null) return '';
    final hh = d.hour.toString().padLeft(2, '0');
    final mm = d.minute.toString().padLeft(2, '0');
    return '$hh:$mm';
  }
}

class _QuizRow extends StatelessWidget {
  final TodayOpenQuiz quiz;
  const _QuizRow({required this.quiz});
  @override
  Widget build(BuildContext context) {
    final left = quiz.maxAttempts == null
        ? 'unlimited attempts'
        : '${quiz.maxAttempts! - quiz.attemptsUsed} attempt${(quiz.maxAttempts! - quiz.attemptsUsed) == 1 ? "" : "s"} left';
    return InkWell(
      onTap: () {
        // Build a minimal MyQuizRow shim to feed into the history screen.
        final stub = MyQuizRow(
          quiz: MyQuizStub(
            id: quiz.id,
            title: quiz.title,
            moduleId: '',
            moduleTitle: quiz.moduleTitle,
            totalPoints: quiz.totalPoints,
            passingScore: quiz.passingScore,
            maxAttempts: quiz.maxAttempts,
          ),
          course: MyQuizCourse(
            id: quiz.courseId ?? '',
            title: quiz.courseTitle,
            category: 'general',
          ),
          attempts: const [],
          attemptsCount: quiz.attemptsUsed,
          canRetake: true,
        );
        Navigator.of(context).push(fadeThroughRoute(
          QuizHistoryScreen(initialRow: stub),
        ));
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 20),
        child: Row(children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(quiz.title,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                        fontSize: 13),
                    overflow: TextOverflow.ellipsis),
                Text('${quiz.courseTitle}${quiz.moduleTitle.isEmpty ? "" : " · ${quiz.moduleTitle}"}',
                    style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.75),
                        fontSize: 11)),
              ],
            ),
          ),
          Text(left,
              style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.85),
                  fontWeight: FontWeight.w600,
                  fontSize: 11)),
          const SizedBox(width: 4),
          const TrailingChevron(color: Colors.white, size: 18),
        ]),
      ),
    );
  }
}
