import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/app_button.dart';
import '../../models/course.dart';
import '../../models/timetable.dart';
import '../../providers/school_providers.dart';
import '../../providers/timetable_provider.dart';
import '../../services/api_service.dart';
import '../shared/weekly_timetable_grid.dart';

/// Admin editor for one class's timetable.
///
/// Above: the grid, with tappable cells → confirm-delete dialog.
/// Below: an "Add period" section, an override list, and an "Add override" button.
class TimetableEditorScreen extends ConsumerStatefulWidget {
  final String classId;
  final String className;
  final String gradeId;
  const TimetableEditorScreen({
    super.key,
    required this.classId,
    required this.className,
    required this.gradeId,
  });

  @override
  ConsumerState<TimetableEditorScreen> createState() =>
      _TimetableEditorScreenState();
}

class _TimetableEditorScreenState extends ConsumerState<TimetableEditorScreen> {
  bool _busy = false;

  Future<void> _replaceWith(List<Period> desired) async {
    setState(() => _busy = true);
    try {
      await ApiService.instance.saveClassPeriods(
        widget.classId,
        desired
            .map((p) => PeriodInput(
                  courseId: p.courseId ?? '',
                  dayOfWeek: p.dayOfWeek,
                  startTime: p.startTime,
                  endTime: p.endTime,
                  room: p.room,
                  meetingUrl: p.meetingUrl,
                ))
            .where((p) => p.courseId.isNotEmpty)
            .toList(),
      );
      ref.invalidate(classTimetableProvider(widget.classId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _addPeriod(List<Course> courses, List<Period> current) async {
    final res = await _showAddPeriodDialog(context, courses: courses);
    if (res == null) return;
    final next = [
      ...current,
      Period(
        id: '',
        classId: widget.classId,
        courseId: res.courseId,
        dayOfWeek: res.dayOfWeek,
        startTime: res.startTime,
        endTime: res.endTime,
        room: res.room,
        meetingUrl: res.meetingUrl,
      ),
    ];
    await _replaceWith(next);
  }

  Future<void> _removePeriod(Period p, List<Period> current) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('Remove period'),
        content: Text(
            '${p.course?.title ?? "This period"} on ${_dayName(p.dayOfWeek)} ${p.startTime} — remove?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(d, false),
              child: const Text('Cancel')),
          ElevatedButton(
              onPressed: () => Navigator.pop(d, true),
              child: const Text('Remove')),
        ],
      ),
    );
    if (ok != true) return;
    final next = current.where((x) => x.id != p.id).toList();
    await _replaceWith(next);
  }

  Future<void> _addOverride(List<Course> courses) async {
    final res = await _showAddOverrideDialog(context, courses: courses);
    if (res == null) return;
    try {
      await ApiService.instance.addTimetableOverride(
        widget.classId,
        date: res.date,
        kind: res.kind,
        startTime: res.startTime,
        endTime: res.endTime,
        room: res.room,
        note: res.note,
      );
      ref.invalidate(classTimetableProvider(widget.classId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  Future<void> _deleteOverride(String id) async {
    try {
      await ApiService.instance.deleteTimetableOverride(id);
      ref.invalidate(classTimetableProvider(widget.classId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(classTimetableProvider(widget.classId));
    // Combine mandatory + every elective option into a flat list for the picker.
    final curriculum = ref.watch(gradeCurriculumProvider(widget.gradeId)).value;
    final courses = <Course>[
      ...?curriculum?.mandatory,
      for (final list in curriculum?.electiveGroups.values ?? const <List<Course>>[])
        ...list,
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.className} timetable',
            style: AppTextStyles.h3(context)),
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (week) => ListView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: WeeklyTimetableGrid(
                  week: week,
                  onCellTap: (p) => _removePeriod(p, week.periods),
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.md),
            Row(children: [
              Expanded(
                child: AppButton(
                  label: 'Add period',
                  loading: _busy,
                  onPressed: courses.isEmpty
                      ? null
                      : () => _addPeriod(courses, week.periods),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: courses.isEmpty
                      ? null
                      : () => _addOverride(courses),
                  icon: const Icon(Icons.event_busy_outlined),
                  label: const Text('Add override'),
                ),
              ),
            ]),
            const SizedBox(height: AppSpacing.xl),
            Text('OVERRIDES (NEXT 30 DAYS)',
                style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
            const SizedBox(height: AppSpacing.sm),
            if (week.overridesInWindow.isEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  child: Text(
                      'No cancellations or schedule swaps for this week.',
                      style: AppTextStyles.caption(context,
                          color: AppColors.textMuted)),
                ),
              )
            else
              for (final o in week.overridesInWindow)
                _OverrideTile(ov: o, onDelete: () => _deleteOverride(o.id)),
          ],
        ),
      ),
    );
  }
}

// ============================================================================
// Override tile
// ============================================================================
class _OverrideTile extends StatelessWidget {
  final TimetableOverride ov;
  final VoidCallback onDelete;
  const _OverrideTile({required this.ov, required this.onDelete});
  @override
  Widget build(BuildContext context) {
    final subtitleBits = <String>[
      ov.date,
      if (ov.startTime != null) '${ov.startTime} - ${ov.endTime ?? ""}',
      if (ov.room != null && ov.room!.isNotEmpty) 'Room ${ov.room}',
    ];
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: ListTile(
        leading: Icon(
          ov.kind == 'canceled'
              ? Icons.block_rounded
              : Icons.event_note_rounded,
          color: ov.kind == 'canceled' ? AppColors.danger : AppColors.primary,
        ),
        title: Text(
          ov.note ?? (ov.kind == 'canceled' ? 'Canceled' : 'Custom period'),
          style: AppTextStyles.bodyStrong(context),
        ),
        subtitle: Text(subtitleBits.join(' · '),
            style: AppTextStyles.caption(context, color: AppColors.textMuted)),
        trailing: IconButton(
          tooltip: 'Delete',
          icon: const Icon(Icons.close_rounded, color: AppColors.danger),
          onPressed: onDelete,
        ),
      ),
    );
  }
}

// ============================================================================
// Add-period dialog
// ============================================================================
class _AddPeriodResult {
  final String courseId;
  final int dayOfWeek;
  final String startTime;
  final String endTime;
  final String? room;
  // Phase 27 — optional Meet/Zoom URL captured on period create.
  final String? meetingUrl;
  _AddPeriodResult({
    required this.courseId,
    required this.dayOfWeek,
    required this.startTime,
    required this.endTime,
    this.room,
    this.meetingUrl,
  });
}

Future<_AddPeriodResult?> _showAddPeriodDialog(
  BuildContext ctx, {
  required List<Course> courses,
}) async {
  final roomCtrl = TextEditingController();
  // Phase 27 — Meet URL controller for the add-period dialog.
  final meetingUrlCtrl = TextEditingController();
  String? courseId = courses.isNotEmpty ? courses.first.id : null;
  int day = 0;
  TimeOfDay start = const TimeOfDay(hour: 9, minute: 0);
  TimeOfDay end = const TimeOfDay(hour: 9, minute: 45);
  try {
    return await showDialog<_AddPeriodResult>(
      context: ctx,
      builder: (d) => StatefulBuilder(builder: (d, setState) {
        return AlertDialog(
          title: const Text('Add period'),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              DropdownButtonFormField<String>(
                initialValue: courseId,
                decoration: const InputDecoration(labelText: 'Course'),
                items: [
                  for (final c in courses)
                    DropdownMenuItem(value: c.id, child: Text(c.title)),
                ],
                onChanged: (v) => setState(() => courseId = v),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<int>(
                initialValue: day,
                decoration: const InputDecoration(labelText: 'Day'),
                items: const [
                  DropdownMenuItem(value: 0, child: Text('Monday')),
                  DropdownMenuItem(value: 1, child: Text('Tuesday')),
                  DropdownMenuItem(value: 2, child: Text('Wednesday')),
                  DropdownMenuItem(value: 3, child: Text('Thursday')),
                  DropdownMenuItem(value: 4, child: Text('Friday')),
                ],
                onChanged: (v) => setState(() => day = v ?? 0),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () async {
                      final t = await showTimePicker(
                          context: d, initialTime: start);
                      if (t != null) setState(() => start = t);
                    },
                    child: Text('Start: ${_fmt(start)}'),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: OutlinedButton(
                    onPressed: () async {
                      final t = await showTimePicker(
                          context: d, initialTime: end);
                      if (t != null) setState(() => end = t);
                    },
                    child: Text('End: ${_fmt(end)}'),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: roomCtrl,
                decoration: const InputDecoration(labelText: 'Room (optional)'),
              ),
              const SizedBox(height: AppSpacing.sm),
              // Phase 27 — optional Meet/Zoom URL for this period.
              // Server validates the scheme (must be http/https).
              TextField(
                controller: meetingUrlCtrl,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'Meet/Zoom URL (optional)',
                  hintText: 'https://meet.google.com/...',
                ),
              ),
            ]),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
            ElevatedButton(
              onPressed: courseId == null
                  ? null
                  : () => Navigator.pop(
                        d,
                        _AddPeriodResult(
                          courseId: courseId!,
                          dayOfWeek: day,
                          startTime: _fmt(start),
                          endTime: _fmt(end),
                          room: roomCtrl.text.trim().isEmpty
                              ? null
                              : roomCtrl.text.trim(),
                          meetingUrl: meetingUrlCtrl.text.trim().isEmpty
                              ? null
                              : meetingUrlCtrl.text.trim(),
                        ),
                      ),
              child: const Text('Add'),
            ),
          ],
        );
      }),
    );
  } finally {
    roomCtrl.dispose();
    meetingUrlCtrl.dispose();
  }
}

// ============================================================================
// Add-override dialog (custom only for this MVP)
// ============================================================================
class _AddOverrideResult {
  final DateTime date;
  final String kind;
  final String? startTime;
  final String? endTime;
  final String? room;
  final String? note;
  _AddOverrideResult({
    required this.date,
    required this.kind,
    this.startTime,
    this.endTime,
    this.room,
    this.note,
  });
}

Future<_AddOverrideResult?> _showAddOverrideDialog(
  BuildContext ctx, {
  required List<Course> courses,
}) async {
  final noteCtrl = TextEditingController();
  final roomCtrl = TextEditingController();
  DateTime date = DateTime.now();
  TimeOfDay start = const TimeOfDay(hour: 9, minute: 0);
  TimeOfDay end = const TimeOfDay(hour: 10, minute: 0);
  try {
    return await showDialog<_AddOverrideResult>(
      context: ctx,
      builder: (d) => StatefulBuilder(builder: (d, setState) {
        return AlertDialog(
          title: const Text('Add override'),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              OutlinedButton(
                onPressed: () async {
                  final picked = await showDatePicker(
                    context: d,
                    initialDate: date,
                    firstDate: DateTime.now(),
                    lastDate: DateTime.now().add(const Duration(days: 365)),
                  );
                  if (picked != null) setState(() => date = picked);
                },
                child: Text('Date: ${DateFormat.yMMMd().format(date)}'),
              ),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () async {
                      final t = await showTimePicker(
                          context: d, initialTime: start);
                      if (t != null) setState(() => start = t);
                    },
                    child: Text('Start: ${_fmt(start)}'),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: OutlinedButton(
                    onPressed: () async {
                      final t = await showTimePicker(
                          context: d, initialTime: end);
                      if (t != null) setState(() => end = t);
                    },
                    child: Text('End: ${_fmt(end)}'),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: noteCtrl,
                decoration: const InputDecoration(
                    labelText: 'Note (e.g. All-school assembly)'),
              ),
              const SizedBox(height: AppSpacing.sm),
              TextField(
                controller: roomCtrl,
                decoration: const InputDecoration(labelText: 'Room (optional)'),
              ),
            ]),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
            ElevatedButton(
              onPressed: () => Navigator.pop(
                d,
                _AddOverrideResult(
                  date: date,
                  kind: 'custom',
                  startTime: _fmt(start),
                  endTime: _fmt(end),
                  room: roomCtrl.text.trim().isEmpty ? null : roomCtrl.text.trim(),
                  note: noteCtrl.text.trim().isEmpty ? null : noteCtrl.text.trim(),
                ),
              ),
              child: const Text('Add'),
            ),
          ],
        );
      }),
    );
  } finally {
    noteCtrl.dispose();
    roomCtrl.dispose();
  }
}

String _fmt(TimeOfDay t) =>
    '${t.hour.toString().padLeft(2, "0")}:${t.minute.toString().padLeft(2, "0")}';

String _dayName(int d) => const ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d];
