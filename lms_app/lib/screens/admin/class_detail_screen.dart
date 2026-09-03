import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../models/insight.dart';
import '../../models/school_class.dart';
import '../../models/user.dart';
import '../../providers/insight_providers.dart';
import '../../providers/school_providers.dart';
import '../../services/api_service.dart';
import 'student_detail_screen.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/failed_load.dart';
import '../../core/widgets/trailing_chevron.dart';

class ClassDetailScreen extends ConsumerWidget {
  final String classId;
  const ClassDetailScreen({super.key, required this.classId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(classDetailProvider(classId));
    return Scaffold(
      appBar: AppBar(
        title: async.maybeWhen(
          data: (c) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(c.name, style: AppTextStyles.h2(context)),
              if (c.homeroomTeacherName != null)
                Text(c.homeroomTeacherName!, style: AppTextStyles.caption(context)),
            ],
          ),
          orElse: () => const Text('Class'),
        ),
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        // Phase 29 · T1 — class detail is required-data. Losing it
        // silently leaves the admin staring at a blank pane with no
        // recovery path.
        error: (e, _) => Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: FailedLoad(
            label: "Couldn't load class",
            detail: friendlyError(e),
            onRetry: () => ref.invalidate(classDetailProvider(classId)),
          ),
        ),
        data: (schoolClass) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(classDetailProvider(classId)),
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            children: [
              _SummaryStrip(count: schoolClass.students.length),
              const SizedBox(height: AppSpacing.lg),
              _ClassCoursesSection(classId: classId),
              const SizedBox(height: AppSpacing.lg),
              Row(children: [
                Expanded(child: _AddStudentButton(classId: classId)),
                const SizedBox(width: AppSpacing.sm),
                _EndOfYearButton(schoolClass: schoolClass, onDone: () {
                  ref.invalidate(classDetailProvider(classId));
                  ref.invalidate(unassignedStudentsProvider);
                }),
              ]),
              const SizedBox(height: AppSpacing.lg),
              Text('Roster', style: AppTextStyles.h3(context)),
              const SizedBox(height: AppSpacing.sm),
              if (schoolClass.students.isEmpty)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.xl),
                    child: Center(
                      child: Text('No students yet.',
                          style: AppTextStyles.caption(context)),
                    ),
                  ),
                )
              else
                for (final s in schoolClass.students) _StudentRow(student: s, classId: classId),
            ],
          ),
        ),
      ),
    );
  }
}

class _SummaryStrip extends StatelessWidget {
  final int count;
  const _SummaryStrip({required this.count});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg, horizontal: AppSpacing.md),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceAround, children: [
          _stat('students', '$count', AppColors.primary),
        ]),
      ),
    );
  }

  Widget _stat(String label, String value, Color color) {
    return Column(children: [
      Text(value,
          style: TextStyle(fontSize: 24, fontWeight: FontWeight.w800, color: color)),
      const SizedBox(height: 2),
      Text(label.toUpperCase(),
          style: const TextStyle(
              fontSize: 10, letterSpacing: 0.8, fontWeight: FontWeight.w700,
              color: AppColors.textMuted)),
    ]);
  }
}

class _AddStudentButton extends ConsumerWidget {
  final String classId;
  const _AddStudentButton({required this.classId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return OutlinedButton.icon(
      onPressed: () async {
        final picked = await showModalBottomSheet<AppUser>(
          context: context,
          isScrollControlled: true,
          builder: (_) => _StudentSearchSheet(unassignedOnly: false),
        );
        if (picked == null) return;
        try {
          // Dry-run first to compute the diff. If it will drop existing
          // enrollments (cross-grade move), show a confirm dialog.
          final diff = await ApiService.instance.placeStudent(picked.id, classId, dryRun: true);
          if (diff.willDropEnrollments > 0 && context.mounted) {
            final ok = await _confirmCrossGradeMove(context, picked, diff);
            if (ok != true) return;
          }
          await ApiService.instance.placeStudent(picked.id, classId);
          ref.invalidate(classDetailProvider(classId));
          ref.invalidate(unassignedStudentsProvider);
        } on ApiException catch (e) {
          if (context.mounted) {
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
          }
        }
      },
      icon: const Icon(Icons.person_add_outlined),
      label: const Text('Add student to roster'),
    );
  }
}

class _StudentSearchSheet extends StatefulWidget {
  final bool unassignedOnly;
  const _StudentSearchSheet({required this.unassignedOnly});

  @override
  State<_StudentSearchSheet> createState() => _StudentSearchSheetState();
}

class _StudentSearchSheetState extends State<_StudentSearchSheet> {
  final _ctrl = TextEditingController();
  List<AppUser> _results = const [];
  bool _loading = false;

  Future<void> _search(String s) async {
    setState(() => _loading = true);
    try {
      final rows = await ApiService.instance.searchStudents(
        search: s,
        unassigned: widget.unassignedOnly,
      );
      setState(() => _results = rows);
    } catch (_) {
      setState(() => _results = const []);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: AppSpacing.xl,
          right: AppSpacing.xl,
          top: AppSpacing.xl,
          bottom: MediaQuery.of(context).viewInsets.bottom + AppSpacing.xl,
        ),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text('Find a student', style: AppTextStyles.h3(context)),
          const SizedBox(height: AppSpacing.md),
          TextField(
            controller: _ctrl,
            autofocus: true,
            onChanged: _search,
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'Name or email',
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          if (_loading) const LinearProgressIndicator(),
          const SizedBox(height: AppSpacing.sm),
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 320),
            child: ListView(shrinkWrap: true, children: [
              for (final s in _results)
                ListTile(
                  leading: CircleAvatar(child: Text(s.name.isNotEmpty ? s.name[0] : '?')),
                  title: Text(s.name),
                  subtitle: Text(s.email),
                  trailing: const Icon(Icons.add),
                  onTap: () => Navigator.pop(context, s),
                ),
            ]),
          ),
        ]),
      ),
    );
  }
}

// ============================================================================
// Courses in this class — teacher-per-class assignment
// ============================================================================
class _ClassCoursesSection extends ConsumerStatefulWidget {
  final String classId;
  const _ClassCoursesSection({required this.classId});

  @override
  ConsumerState<_ClassCoursesSection> createState() => _ClassCoursesSectionState();
}

class _ClassCoursesSectionState extends ConsumerState<_ClassCoursesSection> {
  Future<List<ClassCourse>>? _future;

  @override
  void initState() {
    super.initState();
    _future = ApiService.instance.listClassCourses(widget.classId);
  }

  Future<void> _reload() async {
    setState(() {
      _future = ApiService.instance.listClassCourses(widget.classId);
    });
  }

  Future<void> _assign(ClassCourse cc) async {
    final teachers = await ApiService.instance.listInstructors();
    if (!mounted) return;
    final teacher = await showDialog<AppUser>(
      context: context,
      builder: (d) => SimpleDialog(
        title: Text('Teacher for ${cc.course.title}'),
        children: [
          for (final t in teachers)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(d, t),
              child: Text(t.name),
            ),
        ],
      ),
    );
    if (teacher == null) return;
    try {
      await ApiService.instance.assignClassCourseTeacher(
        widget.classId,
        cc.course.id,
        teacher.id,
      );
      _reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<ClassCourse>>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.lg),
            child: Center(child: CircularProgressIndicator()),
          );
        }
        if (snap.hasError) {
          return Text('Failed to load courses: ${snap.error}',
              style: AppTextStyles.caption(context, color: AppColors.danger));
        }
        final rows = snap.data ?? const <ClassCourse>[];
        if (rows.isEmpty) {
          return Card(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Text(
                'No courses in this class\'s grade yet. Add courses via the grade\'s curriculum page.',
                style: AppTextStyles.caption(context),
              ),
            ),
          );
        }
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Courses in this class', style: AppTextStyles.h3(context)),
          const SizedBox(height: AppSpacing.sm),
          for (final cc in rows)
            Card(
              child: ListTile(
                title: Text(cc.course.title, style: AppTextStyles.bodyStrong(context)),
                subtitle: Text(
                  cc.classTeacher == null
                      ? 'no teacher assigned'
                      : 'Teacher: ${cc.classTeacher!["teacherName"] ?? "?"}',
                  style: AppTextStyles.caption(
                    context,
                    color: cc.classTeacher == null ? AppColors.warning : AppColors.textSecondary,
                  ),
                ),
                trailing: TextButton(
                  onPressed: () => _assign(cc),
                  child: Text(cc.classTeacher == null ? 'Assign' : 'Change'),
                ),
              ),
            ),
        ]);
      },
    );
  }
}

// ============================================================================
// End-of-year: Promote to next grade or Graduate (Grade 12)
// ============================================================================
class _EndOfYearButton extends StatelessWidget {
  final SchoolClass schoolClass;
  final VoidCallback onDone;
  const _EndOfYearButton({required this.schoolClass, required this.onDone});

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
      onSelected: (v) async {
        if (v == 'promote') {
          await _promote(context);
        } else if (v == 'graduate') {
          await _graduate(context);
        }
      },
      itemBuilder: (_) => const [
        PopupMenuItem(value: 'promote', child: Row(children: [
          Icon(Icons.arrow_upward_rounded, size: 18),
          SizedBox(width: AppSpacing.sm),
          Text('Promote to next grade'),
        ])),
        PopupMenuItem(value: 'graduate', child: Row(children: [
          Icon(Icons.workspace_premium_outlined, size: 18),
          SizedBox(width: AppSpacing.sm),
          Text('Graduate class'),
        ])),
      ],
      child: OutlinedButton.icon(
        onPressed: null, // popup handles it
        icon: const Icon(Icons.event_available_outlined),
        label: const Text('End of year'),
      ),
    );
  }

  Future<void> _promote(BuildContext ctx) async {
    // Fetch grades so we can pick the destination class from a next-grade class.
    final allClasses = await ApiService.instance.listClasses();
    if (!ctx.mounted) return;
    final candidates = allClasses.where((c) => c.gradeId != schoolClass.gradeId).toList();
    if (candidates.isEmpty) {
      ScaffoldMessenger.of(ctx).showSnackBar(
        const SnackBar(content: Text('No destination classes available yet. Create one first.')),
      );
      return;
    }
    final dest = await showDialog<SchoolClass>(
      context: ctx,
      builder: (d) => SimpleDialog(
        title: Text('Promote ${schoolClass.name} → …'),
        children: [
          for (final c in candidates)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(d, c),
              child: Text('${c.gradeName ?? ""} · ${c.name}'),
            ),
        ],
      ),
    );
    if (dest == null || !ctx.mounted) return;
    final ok = await showDialog<bool>(
      context: ctx,
      builder: (d) => AlertDialog(
        title: Text('Promote all of ${schoolClass.name}?'),
        content: Text(
          '${schoolClass.studentCount} student(s) will move to ${dest.name}. Their old mandatory enrollments will be soft-dropped and new ones created for the destination grade. Elective picks are carried forward when a successor course exists.',
          style: AppTextStyles.caption(d),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () => Navigator.pop(d, true),
            child: const Text('Promote'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final result = await ApiService.instance.promoteClass(
        schoolClass.id,
        toClassId: dest.id,
      );
      onDone();
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(
          content: Text(
            'Promoted ${result["promoted"]} students to ${dest.name}. Carried forward ${result["carriedForwardElectives"]} electives.',
          ),
        ));
      }
    } on ApiException catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _graduate(BuildContext ctx) async {
    final ok = await showDialog<bool>(
      context: ctx,
      builder: (d) => AlertDialog(
        title: Text('Graduate all of ${schoolClass.name}?'),
        content: Text(
          '${schoolClass.studentCount} student(s) will be marked graduated and deactivated. They lose login access; their historical enrollments, grades, and certificates are preserved.',
          style: AppTextStyles.caption(d),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () => Navigator.pop(d, true),
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
            child: const Text('Graduate'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final result = await ApiService.instance.graduateClass(schoolClass.id);
      onDone();
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(
          content: Text('Graduated ${result["graduated"]} students.'),
        ));
      }
    } on ApiException catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

Future<bool?> _confirmCrossGradeMove(
  BuildContext ctx,
  AppUser student,
  PlacementDiff diff,
) {
  return showDialog<bool>(
    context: ctx,
    builder: (d) => AlertDialog(
      title: const Text('Move student across grades?'),
      content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${student.name} is being moved to a class in a different grade.',
            style: AppTextStyles.body(ctx)),
        const SizedBox(height: AppSpacing.md),
        Row(children: [
          const Icon(Icons.arrow_downward_rounded, size: 18, color: AppColors.danger),
          const SizedBox(width: AppSpacing.sm),
          Expanded(child: Text(
            '${diff.willDropEnrollments} existing enrollment(s) will be dropped (progress preserved on record).',
            style: AppTextStyles.caption(ctx),
          )),
        ]),
        const SizedBox(height: AppSpacing.sm),
        Row(children: [
          const Icon(Icons.arrow_upward_rounded, size: 18, color: AppColors.success),
          const SizedBox(width: AppSpacing.sm),
          Expanded(child: Text(
            '${diff.willAutoEnroll} new mandatory enrollment(s) will be created.',
            style: AppTextStyles.caption(ctx),
          )),
        ]),
        const SizedBox(height: AppSpacing.md),
        Text('Electives will be back to pending.',
            style: AppTextStyles.caption(ctx, color: AppColors.textMuted)),
      ]),
      actions: [
        TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Cancel')),
        ElevatedButton(
          onPressed: () => Navigator.pop(d, true),
          style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
          child: const Text('Move student'),
        ),
      ],
    ),
  );
}

class _StudentRow extends ConsumerWidget {
  final AppUser student;
  final String classId;
  const _StudentRow({required this.student, required this.classId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Phase 22 — the at-risk provider dedupes across every _StudentRow
    // in this class, so watching from each row costs one fetch total.
    final async = ref.watch(classAtRiskProvider(classId));
    final env = async.maybeWhen(
      data: (rows) => rows.firstWhere(
        (r) => r.studentId == student.id,
        orElse: () => AtRiskRow(
            studentId: student.id, name: student.name, email: student.email,
            atRisk: false),
      ),
      orElse: () => null,
    );
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor:
              (env?.atRisk ?? false) ? AppColors.danger : AppColors.primary,
          child: Text(
            student.name.isNotEmpty ? student.name[0].toUpperCase() : '?',
            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
          ),
        ),
        title: Text(student.name),
        subtitle: Text(student.email),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (env != null && env.atRisk) _AtRiskChip(row: env),
            const TrailingChevron(),
          ],
        ),
        onTap: () {
          Navigator.of(context).push(
            fadeThroughRoute(StudentDetailScreen(studentId: student.id)),
          );
        },
      ),
    );
  }
}

/// Phase 22 — red "Needs attention" chip; tooltip lists the reasons.
class _AtRiskChip extends StatelessWidget {
  final AtRiskRow row;
  const _AtRiskChip({required this.row});
  @override
  Widget build(BuildContext context) {
    final reasonsLabel =
        row.reasons.map(AtRiskRow.labelFor).join('\n• ');
    return Padding(
      padding: const EdgeInsetsDirectional.only(end: AppSpacing.sm),
      child: Tooltip(
        message: '• $reasonsLabel',
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: AppColors.dangerSoft,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.warning_amber_rounded,
                size: 12, color: AppColors.danger),
            const SizedBox(width: 3),
            Text('Needs attention',
                style: TextStyle(
                    color: AppColors.danger,
                    fontWeight: FontWeight.w800,
                    fontSize: 10)),
          ]),
        ),
      ),
    );
  }
}
