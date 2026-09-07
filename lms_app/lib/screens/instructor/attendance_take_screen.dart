import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/app_button.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/attendance.dart';
import '../../providers/attendance_provider.dart';
import '../../services/api_service.dart';

/// Homeroom + admin flow for marking a class's daily attendance.
///
/// Design goals from the plan:
///   - "Mark all present" one-tap → then flip individual absentees.
///   - 4 status chips (P/A/L/E) per row, taps toggle without a dialog.
///   - Reason field appears inline when status is `late` or `excused`.
///   - Sticky Save bar shows unsaved-count and confirms on success.
///   - Same-day writes free; past-day requires admin (server enforces).
class AttendanceTakeScreen extends ConsumerStatefulWidget {
  final String classId;
  final String? className;
  final DateTime? initialDate;

  const AttendanceTakeScreen({
    super.key,
    required this.classId,
    this.className,
    this.initialDate,
  });

  @override
  ConsumerState<AttendanceTakeScreen> createState() => _AttendanceTakeScreenState();
}

class _AttendanceTakeScreenState extends ConsumerState<AttendanceTakeScreen> {
  late DateTime _date;
  // Local edit buffer: studentId → (status, reason). Populated on data load,
  // mutated by chip taps + reason edits, flushed to backend on Save.
  final Map<String, ({String status, String? reason})> _local = {};
  final Map<String, TextEditingController> _reasonCtrls = {};
  bool _saving = false;
  int _dirtyCount = 0;

  @override
  void initState() {
    super.initState();
    _date = widget.initialDate ?? DateTime.now();
  }

  @override
  void dispose() {
    for (final c in _reasonCtrls.values) {
      c.dispose();
    }
    super.dispose();
  }

  ClassAttendanceKey get _key => ClassAttendanceKey(widget.classId, _date);

  void _seedLocalFromServer(ClassAttendance data) {
    if (_local.isNotEmpty) return; // already seeded
    for (final row in data.rows) {
      _local[row.student.id] = (
        status: row.mark?.status ?? 'present',
        reason: row.mark?.reason,
      );
      _reasonCtrls[row.student.id] =
          TextEditingController(text: row.mark?.reason ?? '');
    }
    _dirtyCount = data.rows.where((r) => r.mark == null).length;
  }

  void _setStatus(String studentId, String status) {
    setState(() {
      final prev = _local[studentId];
      _local[studentId] = (status: status, reason: prev?.reason);
      _dirtyCount++;
    });
  }

  void _markAllPresent() {
    setState(() {
      for (final k in _local.keys.toList()) {
        _local[k] = (status: 'present', reason: null);
        _reasonCtrls[k]?.clear();
      }
      _dirtyCount = _local.length;
    });
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now(),
    );
    if (picked != null && picked != _date) {
      setState(() {
        _date = picked;
        _local.clear();
        for (final c in _reasonCtrls.values) {
          c.dispose();
        }
        _reasonCtrls.clear();
        _dirtyCount = 0;
      });
    }
  }

  Future<void> _save() async {
    if (_saving || _local.isEmpty) return;
    setState(() => _saving = true);
    try {
      final marks = _local.entries.map((e) {
        final reason = _reasonCtrls[e.key]?.text.trim();
        return AttendanceMarkInput(
          studentId: e.key,
          status: e.value.status,
          reason: (e.value.status == 'late' || e.value.status == 'excused')
              ? (reason == null || reason.isEmpty ? null : reason)
              : null,
        );
      }).toList();
      await ApiService.instance.saveClassAttendance(widget.classId, _date, marks);
      ref.invalidate(classAttendanceProvider(_key));
      if (mounted) {
        setState(() => _dirtyCount = 0);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Attendance saved ✓')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(classAttendanceProvider(_key));
    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.className != null ? '${widget.className} attendance' : 'Attendance',
          style: AppTextStyles.h3(context),
        ),
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (data) {
          _seedLocalFromServer(data);
          return Column(children: [
            _DateHeader(
              date: _date,
              isToday: data.isToday,
              canWrite: data.canWrite,
              onPickDate: _pickDate,
              onMarkAllPresent: data.canWrite ? _markAllPresent : null,
            ),
            const Divider(height: 1, color: AppColors.divider),
            Expanded(
              child: data.rows.isEmpty
                  ? const EmptyState(
                      icon: Icons.groups_outlined,
                      title: 'No students in this class',
                      message: 'Add students to this class before marking '
                          'attendance.',
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
                      itemCount: data.rows.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 4),
                      itemBuilder: (context, i) {
                        final row = data.rows[i];
                        final local = _local[row.student.id];
                        return _StudentRow(
                          name: row.student.name,
                          selected: local?.status ?? 'present',
                          reasonCtrl: _reasonCtrls[row.student.id],
                          onSelect: data.canWrite
                              ? (s) => _setStatus(row.student.id, s)
                              : null,
                        );
                      },
                    ),
            ),
          ]);
        },
      ),
      bottomNavigationBar: async.maybeWhen(
        data: (data) => data.canWrite ? _SaveBar(
          dirtyCount: _dirtyCount,
          saving: _saving,
          onSave: _save,
        ) : _ReadOnlyBar(canWrite: false),
        orElse: () => null,
      ),
    );
  }
}

// ============================================================================
// Header — date picker + "Mark all present"
// ============================================================================
class _DateHeader extends StatelessWidget {
  final DateTime date;
  final bool isToday;
  final bool canWrite;
  final VoidCallback onPickDate;
  final VoidCallback? onMarkAllPresent;

  const _DateHeader({
    required this.date,
    required this.isToday,
    required this.canWrite,
    required this.onPickDate,
    required this.onMarkAllPresent,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Row(children: [
        InkWell(
          onTap: onPickDate,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          child: Container(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md, vertical: AppSpacing.sm),
            decoration: BoxDecoration(
              color: AppColors.primarySoft,
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            ),
            child: Row(children: [
              const Icon(Icons.calendar_month_rounded,
                  size: 18, color: AppColors.primaryDark),
              const SizedBox(width: AppSpacing.sm),
              Text(
                DateFormat.yMMMMEEEEd().format(date),
                style: AppTextStyles.bodyStrong(context,
                    color: AppColors.primaryDark),
              ),
              if (isToday) ...[
                const SizedBox(width: AppSpacing.sm),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.primaryDark,
                    borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                  ),
                  child: const Text('TODAY',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 10,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 0.6)),
                ),
              ],
            ]),
          ),
        ),
        const Spacer(),
        if (onMarkAllPresent != null)
          OutlinedButton.icon(
            onPressed: onMarkAllPresent,
            icon: const Icon(Icons.checklist_rounded, size: 18),
            label: const Text('Mark all present'),
          ),
      ]),
    );
  }
}

// ============================================================================
// Student row — name + 4 status chips + inline reason
// ============================================================================
class _StudentRow extends StatelessWidget {
  final String name;
  final String selected;
  final TextEditingController? reasonCtrl;
  final void Function(String)? onSelect;

  const _StudentRow({
    required this.name,
    required this.selected,
    required this.reasonCtrl,
    required this.onSelect,
  });

  static const _statuses = [
    ('present', 'P', Icons.check_rounded, AppColors.success),
    ('absent', 'A', Icons.close_rounded, AppColors.danger),
    ('late', 'L', Icons.schedule_rounded, AppColors.warning),
    ('excused', 'E', Icons.medical_services_rounded, AppColors.primary),
  ];

  @override
  Widget build(BuildContext context) {
    final showReason = selected == 'late' || selected == 'excused';
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
      child: Column(children: [
        Row(children: [
          Expanded(
            child: Text(name, style: AppTextStyles.bodyStrong(context)),
          ),
          const SizedBox(width: AppSpacing.sm),
          for (final s in _statuses)
            Padding(
              padding: const EdgeInsetsDirectional.only(start: 6),
              child: _StatusChip(
                value: s.$1,
                label: s.$2,
                icon: s.$3,
                color: s.$4,
                selected: selected == s.$1,
                onTap: onSelect,
              ),
            ),
        ]),
        if (showReason && reasonCtrl != null && onSelect != null)
          Padding(
            padding: const EdgeInsetsDirectional.only(top: AppSpacing.sm, start: 4),
            child: TextField(
              controller: reasonCtrl,
              maxLength: 200,
              decoration: InputDecoration(
                hintText: selected == 'excused'
                    ? 'Reason (e.g. Doctor)'
                    : 'Reason (optional)',
                isDense: true,
                counterText: '',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
                ),
              ),
              style: AppTextStyles.caption(context),
            ),
          ),
      ]),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final String value;
  final String label;
  final IconData icon;
  final Color color;
  final bool selected;
  final void Function(String)? onTap;
  const _StatusChip({
    required this.value,
    required this.label,
    required this.icon,
    required this.color,
    required this.selected,
    required this.onTap,
  });
  @override
  Widget build(BuildContext context) {
    final bg = selected ? color : Colors.transparent;
    final fg = selected ? Colors.white : color;
    final border = color.withValues(alpha: selected ? 1.0 : 0.35);
    return InkWell(
      onTap: onTap == null ? null : () => onTap!(value),
      borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 120),
        width: 40,
        height: 40,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          border: Border.all(color: border, width: 1.5),
        ),
        child: Tooltip(
          message: value[0].toUpperCase() + value.substring(1),
          child: Icon(icon, size: 20, color: fg),
        ),
      ),
    );
  }
}

// ============================================================================
// Save bar
// ============================================================================
class _SaveBar extends StatelessWidget {
  final int dirtyCount;
  final bool saving;
  final VoidCallback onSave;

  const _SaveBar({
    required this.dirtyCount,
    required this.saving,
    required this.onSave,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          border: Border(top: BorderSide(color: AppColors.border)),
        ),
        child: Row(children: [
          Icon(
            dirtyCount > 0
                ? Icons.edit_note_rounded
                : Icons.check_circle_rounded,
            color: dirtyCount > 0 ? AppColors.warning : AppColors.success,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              dirtyCount > 0
                  ? '$dirtyCount unsaved mark${dirtyCount == 1 ? "" : "s"}'
                  : 'All marks saved',
              style: AppTextStyles.body(context),
            ),
          ),
          SizedBox(
            width: 130,
            child: AppButton(
              label: 'Save',
              loading: saving,
              onPressed: dirtyCount == 0 ? null : onSave,
            ),
          ),
        ]),
      ),
    );
  }
}

class _ReadOnlyBar extends StatelessWidget {
  final bool canWrite;
  const _ReadOnlyBar({required this.canWrite});
  @override
  Widget build(BuildContext context) {
    if (canWrite) return const SizedBox.shrink();
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          border: Border(top: BorderSide(color: AppColors.border)),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.lock_outline_rounded, color: AppColors.textMuted),
            const SizedBox(width: AppSpacing.sm),
            Text('Read-only — you are not the homeroom teacher for this class.',
                style: AppTextStyles.caption(context, color: AppColors.textMuted)),
          ],
        ),
      ),
    );
  }
}
