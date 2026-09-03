import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/grading.dart';
import '../../models/school_class.dart';
import '../../models/term.dart';
import '../../providers/grading_providers.dart';
import '../../providers/school_providers.dart';
import '../../services/api_service.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';

/// Teacher's gradebook grid — students × categories for one class × course × term.
class GradebookScreen extends ConsumerStatefulWidget {
  final String courseId;
  final String courseTitle;
  const GradebookScreen({super.key, required this.courseId, required this.courseTitle});

  @override
  ConsumerState<GradebookScreen> createState() => _GradebookScreenState();
}

class _GradebookScreenState extends ConsumerState<GradebookScreen> {
  SchoolClass? _class;
  Term? _term;
  Gradebook? _gradebook;
  bool _loading = false;
  String? _error;
  final Map<String, TextEditingController> _controllers = {};

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    if (_class == null || _term == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final g = await ApiService.instance.getGradebook(
        classId: _class!.id,
        courseId: widget.courseId,
        termId: _term!.id,
      );
      setState(() {
        _gradebook = g;
        _loading = false;
      });
      // Rebuild the controller map.
      for (final c in _controllers.values) {
        c.dispose();
      }
      _controllers.clear();
      for (final s in g.students) {
        for (final r in g.rubric) {
          final key = '${s.enrollmentId}:${r.gradeCategoryId}';
          final existing = s.entries[r.gradeCategoryId];
          _controllers[key] = TextEditingController(
            text: existing == null ? '' : _fmtScore(existing),
          );
        }
      }
    } on ApiException catch (e) {
      setState(() {
        _loading = false;
        _error = e.message;
      });
    }
  }

  String _fmtScore(double s) => s == s.roundToDouble() ? s.toInt().toString() : s.toString();

  Future<void> _saveRow(GradebookRow row) async {
    final entries = <Map<String, dynamic>>[];
    for (final r in _gradebook!.rubric) {
      final key = '${row.enrollmentId}:${r.gradeCategoryId}';
      final txt = _controllers[key]?.text.trim() ?? '';
      if (txt.isEmpty) continue;
      final n = double.tryParse(txt);
      if (n == null) continue;
      entries.add({'gradeCategoryId': r.gradeCategoryId, 'score': n});
    }
    if (entries.isEmpty) return;
    try {
      await ApiService.instance.putGrades(
        row.enrollmentId,
        termId: _gradebook!.termId,
        entries: entries,
      );
      _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Saved grades for ${row.studentName}')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final classesAsync = ref.watch(classesProvider(null));
    final schoolYearsAsync = ref.watch(schoolYearsProvider);

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Gradebook', style: AppTextStyles.h3(context)),
            Text(widget.courseTitle, style: AppTextStyles.caption(context)),
          ],
        ),
      ),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl, vertical: AppSpacing.md),
          child: Row(children: [
            Expanded(
              child: classesAsync.when(
                loading: () => const LinearProgressIndicator(),
                error: (e, _) => Text(friendlyError(e), style: AppTextStyles.caption(context)),
                data: (classes) => DropdownButtonFormField<SchoolClass>(
                  initialValue: _class,
                  decoration: const InputDecoration(labelText: 'Class'),
                  items: [
                    for (final c in classes)
                      DropdownMenuItem(
                        value: c,
                        child: Text('${c.gradeName ?? ""} · ${c.name}'),
                      ),
                  ],
                  onChanged: (v) {
                    setState(() => _class = v);
                    _load();
                  },
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: schoolYearsAsync.when(
                loading: () => const LinearProgressIndicator(),
                error: (e, _) => Text(friendlyError(e), style: AppTextStyles.caption(context)),
                data: (years) => _TermDropdown(
                  years: years,
                  onPicked: (t) {
                    setState(() => _term = t);
                    _load();
                  },
                ),
              ),
            ),
          ]),
        ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? Center(child: Text(_error!, style: AppTextStyles.body(context, color: AppColors.danger)))
                  : _gradebook == null
                      ? const Center(child: Text('Pick a class and term to see the gradebook.'))
                      : _GradebookGrid(
                          gradebook: _gradebook!,
                          controllers: _controllers,
                          onSave: _saveRow,
                        ),
        ),
      ]),
    );
  }
}

class _TermDropdown extends ConsumerStatefulWidget {
  final List<dynamic> years;
  final ValueChanged<Term> onPicked;
  const _TermDropdown({required this.years, required this.onPicked});

  @override
  ConsumerState<_TermDropdown> createState() => _TermDropdownState();
}

class _TermDropdownState extends ConsumerState<_TermDropdown> {
  Term? _selected;

  @override
  Widget build(BuildContext context) {
    // Get terms of the current year (first is_current true).
    final currentYear = widget.years.firstWhere(
      (y) => (y as dynamic).isCurrent == true,
      orElse: () => widget.years.isEmpty ? null : widget.years.first,
    );
    if (currentYear == null) return const SizedBox.shrink();
    final termsAsync = ref.watch(termsProvider(currentYear.id as String));
    return termsAsync.when(
      loading: () => const LinearProgressIndicator(),
      error: (e, _) => Text(friendlyError(e), style: AppTextStyles.caption(context)),
      data: (terms) => DropdownButtonFormField<Term>(
        initialValue: _selected,
        decoration: const InputDecoration(labelText: 'Term'),
        items: [for (final t in terms) DropdownMenuItem(value: t, child: Text(t.name))],
        onChanged: (v) {
          setState(() => _selected = v);
          if (v != null) widget.onPicked(v);
        },
      ),
    );
  }
}

class _GradebookGrid extends StatelessWidget {
  final Gradebook gradebook;
  final Map<String, TextEditingController> controllers;
  final Future<void> Function(GradebookRow row) onSave;
  const _GradebookGrid({
    required this.gradebook,
    required this.controllers,
    required this.onSave,
  });

  @override
  Widget build(BuildContext context) {
    if (gradebook.rubric.isEmpty) {
      // Phase 26 · T2 — canonical EmptyState, so the teacher sees the
      // same "empty" pattern here as everywhere else.
      return const EmptyState(
        icon: Icons.rule_folder_outlined,
        title: 'No rubric yet',
        message: 'An admin needs to set the grading rubric for this '
            'course before you can enter marks.',
      );
    }
    if (gradebook.students.isEmpty) {
      return const EmptyState(
        icon: Icons.groups_outlined,
        title: 'No students in this class',
        message: 'This class has no active students enrolled in the '
            'course yet.',
      );
    }
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: DataTable(
          columnSpacing: 24,
          columns: [
            const DataColumn(label: Text('Student')),
            for (final r in gradebook.rubric)
              DataColumn(
                label: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(r.gradeCategoryName ?? '—',
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                  Text('/${r.maxScore}',
                      style: const TextStyle(fontSize: 11, color: AppColors.textMuted)),
                ]),
              ),
            const DataColumn(label: Text('%')),
            const DataColumn(label: Text('Ltr')),
            const DataColumn(label: Text('')),
          ],
          rows: [
            for (final s in gradebook.students)
              DataRow(cells: [
                DataCell(Text(s.studentName)),
                for (final r in gradebook.rubric)
                  DataCell(
                    SizedBox(
                      width: 56,
                      child: TextField(
                        controller: controllers['${s.enrollmentId}:${r.gradeCategoryId}'],
                        enabled: gradebook.canWrite && !gradebook.termIsLocked,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        textAlign: TextAlign.center,
                        decoration: const InputDecoration(
                          isDense: true,
                          contentPadding: EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                        ),
                      ),
                    ),
                  ),
                DataCell(Text(
                  s.cachedPercent != null ? '${s.cachedPercent!.toStringAsFixed(1)}%' : '—',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                )),
                DataCell(Text(s.cachedLetter ?? '—')),
                DataCell(
                  IconButton(
                    icon: const Icon(Icons.save_outlined, size: 20),
                    tooltip: 'Save',
                    onPressed: (gradebook.canWrite && !gradebook.termIsLocked)
                        ? () => onSave(s)
                        : null,
                  ),
                ),
              ]),
          ],
        ),
      ),
    );
  }
}
