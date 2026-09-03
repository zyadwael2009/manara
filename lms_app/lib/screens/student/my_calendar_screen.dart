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
import '../../providers/quiz_providers.dart';
import 'assignment_submit_screen.dart';
import 'quiz_history_screen.dart';
import '../../core/widgets/trailing_chevron.dart';

/// Phase 24 — cross-course month calendar of the student's upcoming
/// assignments (by due date) and open quizzes (with attempts left).
///
/// Client-side aggregation over `myAssignmentsAllProvider` +
/// `myQuizzesAllProvider` — no new endpoint. Data quality mirrors those
/// providers exactly.
class MyCalendarScreen extends ConsumerStatefulWidget {
  const MyCalendarScreen({super.key});

  @override
  ConsumerState<MyCalendarScreen> createState() => _MyCalendarScreenState();
}

class _MyCalendarScreenState extends ConsumerState<MyCalendarScreen> {
  late DateTime _monthCursor;
  DateTime? _selected;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _monthCursor = DateTime(now.year, now.month, 1);
    _selected = DateTime(now.year, now.month, now.day);
  }

  @override
  Widget build(BuildContext context) {
    final assignAsync = ref.watch(myAssignmentsAllProvider);
    final quizAsync = ref.watch(myQuizzesAllProvider);
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('Calendar', style: AppTextStyles.h2(context)),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(myAssignmentsAllProvider);
          ref.invalidate(myQuizzesAllProvider);
          await ref.read(myAssignmentsAllProvider.future);
          await ref.read(myQuizzesAllProvider.future);
        },
        child: assignAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text(friendlyError(e))),
          data: (assignments) => quizAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text(friendlyError(e))),
            data: (quizzes) {
              final byDay = _bucketByDay(assignments, quizzes);
              return ListView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                children: [
                  _MonthHeader(
                    monthCursor: _monthCursor,
                    onPrev: () => setState(() {
                      _monthCursor =
                          DateTime(_monthCursor.year, _monthCursor.month - 1, 1);
                    }),
                    onNext: () => setState(() {
                      _monthCursor =
                          DateTime(_monthCursor.year, _monthCursor.month + 1, 1);
                    }),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  _MonthGrid(
                    monthCursor: _monthCursor,
                    byDay: byDay,
                    selected: _selected,
                    onTapDay: (d) => setState(() => _selected = d),
                  ),
                  const SizedBox(height: AppSpacing.xl),
                  _DayList(
                    day: _selected,
                    items:
                        _selected == null ? const [] : byDay[_dayKey(_selected!)] ?? const [],
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  /// Groups assignments (by dueAt) and open quizzes (by today's date, so
  /// they show as "available now") into per-day buckets.
  Map<String, List<_CalendarItem>> _bucketByDay(
    List<MyAssignmentRow> assignments,
    List quizzes,
  ) {
    final out = <String, List<_CalendarItem>>{};
    for (final a in assignments) {
      final due = a.assignment.dueAt;
      if (due == null) continue;
      final key = _dayKey(due);
      out.putIfAbsent(key, () => []).add(_CalendarItem.assignment(a));
    }
    // Quizzes without a fixed date land in today's bucket so the user
    // sees "these are open now" alongside due-today assignments.
    final today = _dayKey(DateTime.now());
    for (final q in quizzes) {
      if (q.canRetake) {
        out.putIfAbsent(today, () => []).add(_CalendarItem.quiz(q));
      }
    }
    return out;
  }

  static String _dayKey(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}

class _CalendarItem {
  final String kind; // "assignment" | "quiz"
  final MyAssignmentRow? assignment;
  final dynamic quiz;
  const _CalendarItem._({required this.kind, this.assignment, this.quiz});
  factory _CalendarItem.assignment(MyAssignmentRow a) =>
      _CalendarItem._(kind: 'assignment', assignment: a);
  factory _CalendarItem.quiz(dynamic q) => _CalendarItem._(kind: 'quiz', quiz: q);
}

class _MonthHeader extends StatelessWidget {
  final DateTime monthCursor;
  final VoidCallback onPrev;
  final VoidCallback onNext;
  const _MonthHeader({
    required this.monthCursor,
    required this.onPrev,
    required this.onNext,
  });
  static const _months = [
    'January','February','March','April','May','June',
    'July','August','September','October','November','December',
  ];
  @override
  Widget build(BuildContext context) {
    return Row(children: [
      IconButton(
          tooltip: 'Previous month',
          icon: const Icon(Icons.chevron_left_rounded),
          onPressed: onPrev),
      Expanded(
        child: Center(
          child: Text(
              '${_months[monthCursor.month - 1]} ${monthCursor.year}',
              style: AppTextStyles.h3(context)
                  .copyWith(fontWeight: FontWeight.w800)),
        ),
      ),
      IconButton(
          tooltip: 'Next month',
          icon: const TrailingChevron(),
          onPressed: onNext),
    ]);
  }
}

class _MonthGrid extends StatelessWidget {
  final DateTime monthCursor;
  final Map<String, List<_CalendarItem>> byDay;
  final DateTime? selected;
  final ValueChanged<DateTime> onTapDay;
  const _MonthGrid({
    required this.monthCursor,
    required this.byDay,
    required this.selected,
    required this.onTapDay,
  });

  @override
  Widget build(BuildContext context) {
    // Compute the calendar's first cell (last Sun/Mon before or on the 1st).
    final first = DateTime(monthCursor.year, monthCursor.month, 1);
    // Monday-first (1..7 → shift so Mon lands in col 0).
    final leading = (first.weekday - 1) % 7;
    final gridStart = first.subtract(Duration(days: leading));
    // Always render 6 weeks so the grid height is stable.
    final cells = List.generate(42, (i) => gridStart.add(Duration(days: i)));

    const daysOfWeek = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

    return Column(children: [
      Row(children: [
        for (final d in daysOfWeek)
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Center(
                child: Text(d,
                    style: AppTextStyles.micro(context,
                            color: AppColors.textMuted)
                        .copyWith(fontWeight: FontWeight.w700)),
              ),
            ),
          ),
      ]),
      for (int week = 0; week < 6; week++)
        Row(children: [
          for (int day = 0; day < 7; day++)
            Expanded(
              child: _DayCell(
                date: cells[week * 7 + day],
                inMonth: cells[week * 7 + day].month == monthCursor.month,
                selected: selected != null &&
                    selected!.year == cells[week * 7 + day].year &&
                    selected!.month == cells[week * 7 + day].month &&
                    selected!.day == cells[week * 7 + day].day,
                items: byDay[
                    '${cells[week * 7 + day].year}-${cells[week * 7 + day].month.toString().padLeft(2, '0')}-${cells[week * 7 + day].day.toString().padLeft(2, '0')}'] ??
                    const [],
                onTap: () => onTapDay(cells[week * 7 + day]),
              ),
            ),
        ]),
    ]);
  }
}

class _DayCell extends StatelessWidget {
  final DateTime date;
  final bool inMonth;
  final bool selected;
  final List<_CalendarItem> items;
  final VoidCallback onTap;
  const _DayCell({
    required this.date,
    required this.inMonth,
    required this.selected,
    required this.items,
    required this.onTap,
  });
  @override
  Widget build(BuildContext context) {
    final isToday = _isToday(date);
    final assignCount = items.where((i) => i.kind == 'assignment').length;
    final quizCount = items.where((i) => i.kind == 'quiz').length;
    return InkWell(
      onTap: onTap,
      child: Container(
        height: 56,
        margin: const EdgeInsets.all(2),
        padding: const EdgeInsets.symmetric(vertical: 4),
        decoration: BoxDecoration(
          color: selected
              ? AppColors.primary
              : (isToday ? AppColors.primarySoft : Colors.transparent),
          borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('${date.day}',
                style: TextStyle(
                  // Phase 25 hard-audit fix D-7: pull the "in-month"
                  // text color from the theme so dark mode gets legible
                  // text on the dark scaffold. Previously hardcoded
                  // AppColors.textPrimary (slate-900) — nearly invisible
                  // on dark background.
                  color: selected
                      ? Colors.white
                      : (inMonth
                          ? (isToday
                              ? AppColors.primaryDark
                              : Theme.of(context).colorScheme.onSurface)
                          : AppColors.textMuted),
                  fontWeight: selected || isToday
                      ? FontWeight.w800
                      : FontWeight.w600,
                )),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (assignCount > 0)
                  Container(
                    width: 6, height: 6,
                    margin: const EdgeInsets.symmetric(horizontal: 1),
                    decoration: BoxDecoration(
                      color: selected ? Colors.white : AppColors.accent,
                      shape: BoxShape.circle,
                    ),
                  ),
                if (quizCount > 0)
                  Container(
                    width: 6, height: 6,
                    margin: const EdgeInsets.symmetric(horizontal: 1),
                    decoration: BoxDecoration(
                      color: selected ? Colors.white : AppColors.primary,
                      shape: BoxShape.circle,
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  static bool _isToday(DateTime d) {
    final now = DateTime.now();
    return d.year == now.year && d.month == now.month && d.day == now.day;
  }
}

class _DayList extends StatelessWidget {
  final DateTime? day;
  final List<_CalendarItem> items;
  const _DayList({required this.day, required this.items});
  @override
  Widget build(BuildContext context) {
    if (day == null) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(_prettyDate(day!),
            style: AppTextStyles.h3(context)
                .copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: AppSpacing.sm),
        if (items.isEmpty)
          const EmptyState(
            icon: Icons.event_available_outlined,
            title: 'Nothing scheduled',
            message: 'This day has no assignments or open quizzes.',
          )
        else
          for (final i in items) _ItemTile(item: i),
      ],
    );
  }

  static String _prettyDate(DateTime d) {
    const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
    const months = [
      'January','February','March','April','May','June',
      'July','August','September','October','November','December',
    ];
    return '${days[d.weekday - 1]}, ${d.day} ${months[d.month - 1]}';
  }
}

class _ItemTile extends StatelessWidget {
  final _CalendarItem item;
  const _ItemTile({required this.item});
  @override
  Widget build(BuildContext context) {
    if (item.kind == 'assignment') {
      final a = item.assignment!;
      return Card(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          side: const BorderSide(color: AppColors.border),
        ),
        child: ListTile(
          leading: const CircleAvatar(
            backgroundColor: AppColors.accentSoft,
            child: Icon(Icons.assignment_outlined,
                color: AppColors.accentText, size: 18),
          ),
          title: Text(a.assignment.title,
              style: AppTextStyles.body(context)
                  .copyWith(fontWeight: FontWeight.w700)),
          subtitle: Text('${a.course.title} · ${a.moduleTitle}',
              style: AppTextStyles.caption(context,
                  color: AppColors.textMuted)),
          trailing: const TrailingChevron(),
          onTap: () {
            Navigator.of(context).push(fadeThroughRoute(
              AssignmentSubmitScreen(assignmentId: a.assignment.id),
            ));
          },
        ),
      );
    }
    // quiz
    final q = item.quiz;
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        side: const BorderSide(color: AppColors.border),
      ),
      child: ListTile(
        leading: const CircleAvatar(
          backgroundColor: AppColors.primarySoft,
          child: Icon(Icons.quiz_outlined,
              color: AppColors.primaryDark, size: 18),
        ),
        title: Text(q.quiz.title,
            style: AppTextStyles.body(context)
                .copyWith(fontWeight: FontWeight.w700)),
        subtitle: Text('${q.course.title} · ${q.quiz.moduleTitle}',
            style: AppTextStyles.caption(context, color: AppColors.textMuted)),
        trailing: const TrailingChevron(),
        onTap: () {
          Navigator.of(context).push(fadeThroughRoute(
            QuizHistoryScreen(initialRow: q),
          ));
        },
      ),
    );
  }
}
