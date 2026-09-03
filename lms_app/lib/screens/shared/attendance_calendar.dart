import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/attendance.dart';
import '../../core/widgets/trailing_chevron.dart';

/// Reusable month calendar for attendance history.
///
/// Used by:
///   - Student self-view (`myAttendanceProvider`)
///   - Parent child-view (`childAttendanceProvider`)
///   - Admin/teacher student-view (`studentAttendanceProvider`)
///
/// Days are color-coded (green present, red absent, amber late, blue excused,
/// grey unmarked). Tap a day for a detail popover. Header shows the
/// attendance rate for the visible month.
class AttendanceCalendar extends StatefulWidget {
  final List<AttendanceMark> marks;
  const AttendanceCalendar({super.key, required this.marks});

  @override
  State<AttendanceCalendar> createState() => _AttendanceCalendarState();
}

class _AttendanceCalendarState extends State<AttendanceCalendar> {
  late DateTime _cursor; // first-of-month for the currently-displayed month.

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _cursor = DateTime(now.year, now.month, 1);
  }

  Map<DateTime, AttendanceMark> get _byDate {
    final out = <DateTime, AttendanceMark>{};
    for (final m in widget.marks) {
      final d = DateTime(m.date.year, m.date.month, m.date.day);
      out[d] = m;
    }
    return out;
  }

  List<AttendanceMark> _forMonth(DateTime firstOfMonth) {
    return widget.marks.where((m) =>
        m.date.year == firstOfMonth.year &&
        m.date.month == firstOfMonth.month).toList();
  }

  void _prev() => setState(() {
        _cursor = DateTime(_cursor.year, _cursor.month - 1, 1);
      });
  void _next() {
    final now = DateTime.now();
    final nextMonth = DateTime(_cursor.year, _cursor.month + 1, 1);
    if (nextMonth.isBefore(DateTime(now.year, now.month + 1, 1))) {
      setState(() => _cursor = nextMonth);
    }
  }

  @override
  Widget build(BuildContext context) {
    final monthMarks = _forMonth(_cursor);
    final present = monthMarks.where(
        (m) => m.status == 'present' || m.status == 'excused').length;
    final total = monthMarks.length;
    final rate = total == 0 ? null : present / total;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Header
        Row(children: [
          IconButton(
            tooltip: 'Previous month',
            onPressed: _prev,
            icon: const Icon(Icons.chevron_left_rounded),
          ),
          Expanded(
            child: Text(
              DateFormat.yMMMM().format(_cursor),
              textAlign: TextAlign.center,
              style: AppTextStyles.h3(context),
            ),
          ),
          IconButton(
            tooltip: 'Next month',
            onPressed: _next,
            icon: const TrailingChevron(),
          ),
        ]),
        if (rate != null)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.md),
            child: Text(
              '${(rate * 100).toStringAsFixed(0)}% attendance · $total school days',
              textAlign: TextAlign.center,
              style: AppTextStyles.caption(context, color: AppColors.textSecondary),
            ),
          ),
        _MonthGrid(cursor: _cursor, byDate: _byDate),
        const SizedBox(height: AppSpacing.md),
        _Legend(),
      ],
    );
  }
}

// ============================================================================
// Month grid — 7 columns × N rows.
// ============================================================================
class _MonthGrid extends StatelessWidget {
  final DateTime cursor;
  final Map<DateTime, AttendanceMark> byDate;
  const _MonthGrid({required this.cursor, required this.byDate});

  @override
  Widget build(BuildContext context) {
    final daysInMonth =
        DateTime(cursor.year, cursor.month + 1, 0).day;
    // Weekday of the 1st: Dart uses 1 (Mon) - 7 (Sun). Grid starts Sun.
    // Convert so column 0 = Sunday.
    final firstDayCol = cursor.weekday == 7 ? 0 : cursor.weekday; // Mon=1..Sat=6, Sun=0
    final today = DateTime.now();
    final todayNoon = DateTime(today.year, today.month, today.day);

    final cells = <Widget>[];
    for (final w in const ['S', 'M', 'T', 'W', 'T', 'F', 'S']) {
      cells.add(Center(
        child: Text(w,
            style: AppTextStyles.micro(context, color: AppColors.textMuted)),
      ));
    }
    for (var i = 0; i < firstDayCol; i++) {
      cells.add(const SizedBox.shrink());
    }
    for (var d = 1; d <= daysInMonth; d++) {
      final date = DateTime(cursor.year, cursor.month, d);
      final mark = byDate[date];
      final isFuture = date.isAfter(todayNoon);
      cells.add(_DayCell(
        day: d,
        mark: mark,
        isToday: date == todayNoon,
        isFuture: isFuture,
      ));
    }
    return GridView.count(
      crossAxisCount: 7,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      childAspectRatio: 1.0,
      children: cells,
    );
  }
}

class _DayCell extends StatelessWidget {
  final int day;
  final AttendanceMark? mark;
  final bool isToday;
  final bool isFuture;
  const _DayCell({
    required this.day,
    required this.mark,
    required this.isToday,
    required this.isFuture,
  });

  @override
  Widget build(BuildContext context) {
    final palette = _paletteFor(mark?.status);
    return Padding(
      padding: const EdgeInsets.all(2),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        onTap: mark == null
            ? null
            : () => _showDetail(context, mark!),
        child: Container(
          decoration: BoxDecoration(
            color: palette.$1,
            borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            border: isToday
                ? Border.all(color: AppColors.primary, width: 1.5)
                : null,
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                '$day',
                style: TextStyle(
                  color: isFuture ? AppColors.textMuted : palette.$2,
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                ),
              ),
              if (mark != null)
                Text(
                  _shortStatus(mark!.status),
                  style: TextStyle(
                    color: palette.$2,
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  static String _shortStatus(String s) => switch (s) {
        'present' => 'P',
        'absent' => 'A',
        'late' => 'L',
        'excused' => 'E',
        _ => '',
      };

  static (Color, Color) _paletteFor(String? status) => switch (status) {
        'present' => (AppColors.successSoft, AppColors.success),
        'absent' => (AppColors.dangerSoft, AppColors.danger),
        'late' => (AppColors.warningSoft, AppColors.warning),
        'excused' => (AppColors.primarySoft, AppColors.primary),
        _ => (Colors.transparent, AppColors.textMuted),
      };

  static void _showDetail(BuildContext context, AttendanceMark m) {
    showDialog<void>(
      context: context,
      builder: (d) => AlertDialog(
        title: Text(DateFormat.yMMMMEEEEd().format(m.date)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              _StatusPill(status: m.status),
            ]),
            if (m.reason != null && m.reason!.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.md),
              Text(m.reason!,
                  style: AppTextStyles.body(context, color: AppColors.textSecondary)),
            ],
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d), child: const Text('Close')),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String status;
  const _StatusPill({required this.status});
  @override
  Widget build(BuildContext context) {
    final (bg, fg) = _DayCell._paletteFor(status);
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md, vertical: 6),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(
        status[0].toUpperCase() + status.substring(1),
        style: AppTextStyles.bodyStrong(context, color: fg),
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: 6,
      alignment: WrapAlignment.center,
      children: const [
        _LegendDot(color: AppColors.success, label: 'Present'),
        _LegendDot(color: AppColors.danger, label: 'Absent'),
        _LegendDot(color: AppColors.warning, label: 'Late'),
        _LegendDot(color: AppColors.primary, label: 'Excused'),
      ],
    );
  }
}

class _LegendDot extends StatelessWidget {
  final Color color;
  final String label;
  const _LegendDot({required this.color, required this.label});
  @override
  Widget build(BuildContext context) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8, height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(label,
              style: AppTextStyles.micro(context, color: AppColors.textMuted)),
        ],
      );
}
