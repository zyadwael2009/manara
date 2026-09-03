import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/category_palette.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/timetable.dart';

// Column widths for the weekly grid. See build() note in WeeklyTimetableGrid
// on why Expanded cannot be used inside a horizontal SingleChildScrollView.
const double _kDayColWidth = 132;
const double _kTimeColWidth = 68;

/// Weekly grid — 5 columns Mon..Fri, N rows (one per time slot).
///
/// Cells show course + teacher/class + room. Empty slots render as
/// faint placeholders so the grid rhythm stays consistent. Long-press
/// (or the `onCellTap` callback) surfaces the period for the admin
/// editor's delete flow.
class WeeklyTimetableGrid extends StatelessWidget {
  final TimetableWeek week;
  final bool showClassName; // true for teacher view (multi-class)
  final void Function(Period period)? onCellTap;
  const WeeklyTimetableGrid({
    super.key,
    required this.week,
    this.showClassName = false,
    this.onCellTap,
  });

  static const _dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];

  @override
  Widget build(BuildContext context) {
    // Bucket periods by day.
    final byDay = <int, List<Period>>{for (var d = 0; d < 5; d++) d: []};
    for (final p in week.periods) {
      if (p.dayOfWeek >= 0 && p.dayOfWeek <= 4) {
        byDay[p.dayOfWeek]!.add(p);
      }
    }
    // Discover unique start-time rows across the week.
    final slots = <String>{
      for (final p in week.periods) p.startTime,
    }.toList()..sort();

    if (slots.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Center(
          child: Text('No periods scheduled yet.',
              style: AppTextStyles.body(context, color: AppColors.textMuted)),
        ),
      );
    }

    // Bug fix — the horizontal SingleChildScrollView gives its child
    // UNBOUNDED width. `Expanded` in each cell then crashes at layout
    // ("non-zero flex but incoming width constraints are unbounded")
    // and the whole body renders blank. Fix by giving each column a
    // fixed width and sizing the whole grid explicitly so horizontal
    // scroll only kicks in on narrow viewports.
    final totalWidth = _kTimeColWidth + _kDayColWidth * _dayNames.length;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SizedBox(
        width: totalWidth,
        child: Column(children: [
          // Header row: blank corner + Mon..Fri.
          Row(children: [
            const _TimeHeaderCell(text: ''),
            for (final d in _dayNames) _DayHeaderCell(text: d),
          ]),
          for (final slot in slots)
            Row(children: [
              _TimeHeaderCell(text: slot),
              for (var d = 0; d < 5; d++)
                _cellFor(byDay[d]!, slot),
            ]),
        ]),
      ),
    );
  }

  Widget _cellFor(List<Period> dayPeriods, String slot) {
    final match = dayPeriods.where((p) => p.startTime == slot).toList();
    if (match.isEmpty) {
      return const _EmptyCell();
    }
    return _PeriodCell(
      period: match.first,
      showClassName: showClassName,
      onTap: onCellTap,
    );
  }
}

// ============================================================================
// Cells
// ============================================================================
class _TimeHeaderCell extends StatelessWidget {
  final String text;
  const _TimeHeaderCell({required this.text});
  @override
  Widget build(BuildContext context) => Container(
        width: _kTimeColWidth,
        padding: const EdgeInsets.all(AppSpacing.sm),
        decoration: const BoxDecoration(
          border: Border(right: BorderSide(color: AppColors.border)),
        ),
        alignment: Alignment.centerRight,
        child: Text(text,
            style: AppTextStyles.micro(context, color: AppColors.textMuted)),
      );
}

class _DayHeaderCell extends StatelessWidget {
  final String text;
  const _DayHeaderCell({required this.text});
  @override
  Widget build(BuildContext context) => SizedBox(
        width: _kDayColWidth,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
          decoration: BoxDecoration(
            color: AppColors.primarySoft,
            border: const Border(right: BorderSide(color: AppColors.border)),
          ),
          alignment: Alignment.center,
          child: Text(text,
              style: AppTextStyles.bodyStrong(context,
                  color: AppColors.primaryDark)),
        ),
      );
}

class _EmptyCell extends StatelessWidget {
  const _EmptyCell();
  @override
  Widget build(BuildContext context) => SizedBox(
        width: _kDayColWidth,
        child: Container(
          height: 72,
          decoration: BoxDecoration(
            color: AppColors.surfaceMuted,
            border: Border.all(color: AppColors.border, width: 0.5),
          ),
        ),
      );
}

class _PeriodCell extends StatelessWidget {
  final Period period;
  final bool showClassName;
  final void Function(Period period)? onTap;
  const _PeriodCell({
    required this.period,
    required this.showClassName,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final title = period.course?.title
        ?? (period.isOverride ? (period.note ?? 'Custom') : 'Free');
    final sub = <String>[
      if (period.endTime.isNotEmpty) 'ends ${period.endTime}',
      if (showClassName && period.className != null) period.className!,
      if (period.room != null && period.room!.isNotEmpty) 'R.${period.room}',
    ].join(' · ');

    return SizedBox(
      width: _kDayColWidth,
      child: InkWell(
        onTap: onTap == null ? null : () => onTap!(period),
        child: Container(
          height: 72,
          padding: const EdgeInsets.all(AppSpacing.sm),
          decoration: BoxDecoration(
            color: _bgFor(period.course?.category),
            border: Border.all(color: AppColors.border, width: 0.5),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(
                  child: Text(title,
                      style: AppTextStyles.bodyStrong(context,
                          color: _fgFor(period.course?.category)),
                      overflow: TextOverflow.ellipsis,
                      maxLines: 1),
                ),
                // Phase 27 — small camera dot when a Meet URL is set.
                // Just an affordance hint; the actual Join button lives
                // on the Now/Next card so students only click during a
                // live period.
                if (period.meetingUrl != null &&
                    period.meetingUrl!.isNotEmpty)
                  const Padding(
                    padding: EdgeInsetsDirectional.only(start: AppSpacing.hair),
                    child: Icon(Icons.videocam_outlined,
                        size: 12, color: AppColors.primary),
                  ),
              ]),
              const SizedBox(height: 2),
              if (sub.isNotEmpty)
                Text(sub,
                    style: AppTextStyles.micro(context,
                        color: AppColors.textMuted),
                    overflow: TextOverflow.ellipsis,
                    maxLines: 1),
              if (period.teacherName != null && !showClassName)
                Text(period.teacherName!,
                    style: AppTextStyles.micro(context,
                        color: AppColors.textMuted),
                    overflow: TextOverflow.ellipsis,
                    maxLines: 1),
            ],
          ),
        ),
      ),
    );
  }

  // Phase 26 · T1 — swatches now pulled from the shared
  // `CategoryPalette` so a rebrand touches one file, and English no
  // longer hardcodes the amber-900 literal that had already drifted.
  static Color _bgFor(String? category) =>
      CategoryPalette.forCategory(category).softBg;

  static Color _fgFor(String? category) =>
      CategoryPalette.forCategory(category).textOnSoft;
}
