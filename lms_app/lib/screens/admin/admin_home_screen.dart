import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../core/widgets/account_menu.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/grade.dart';
import '../../models/school_class.dart';
import '../../models/section.dart';
import '../../models/user.dart';
import '../../providers/school_providers.dart';
import '../../services/api_service.dart';
import '../instructor/attendance_take_screen.dart';
import '../shared/announcement_composer_sheet.dart';
import '../shared/inbox_screen.dart';
import '../shared/notifications_bell.dart';
import '../shared/search_screen.dart';
import 'bulk_import_screen.dart';
import 'data_export_screen.dart';
import 'admin_dashboard_screen.dart';
import 'class_detail_screen.dart';
import 'timetable_editor_screen.dart';
import 'department_leaders_screen.dart';
import 'grade_curriculum_screen.dart';
import 'grading_admin_screen.dart';
import 'student_detail_screen.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/trailing_chevron.dart';

class AdminHomeScreen extends ConsumerStatefulWidget {
  const AdminHomeScreen({super.key});
  @override
  ConsumerState<AdminHomeScreen> createState() => _AdminHomeScreenState();
}

class _AdminHomeScreenState extends ConsumerState<AdminHomeScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tab;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 7, vsync: this);
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('School office', style: AppTextStyles.h2(context)),
        actions: [
          IconButton(
            tooltip: 'Search',
            icon: const Icon(Icons.search_rounded),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const SearchScreen()),
              );
            },
          ),
          // Phase 26 · T6 — admin was missing the Messages entry every
          // other role has. Same InboxScreen + same tooltip so muscle
          // memory carries across roles.
          IconButton(
            tooltip: 'Messages',
            icon: const Icon(Icons.chat_bubble_outline_rounded),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const InboxScreen()),
              );
            },
          ),
          const NotificationsBell(),
          const AccountMenu(),
        ],
        bottom: TabBar(
          controller: _tab,
          isScrollable: true,
          tabs: const [
            Tab(text: 'Dashboard'),
            Tab(text: 'Sections'),
            Tab(text: 'Grades'),
            Tab(text: 'Classes'),
            Tab(text: 'Students'),
            Tab(text: 'Departments'),
            Tab(text: 'Grading'),
          ],
        ),
      ),
      body: TabBarView(controller: _tab, children: const [
        AdminDashboardScreen(),
        _SectionsTab(),
        _GradesTab(),
        _ClassesTab(),
        _StudentsTab(),
        DepartmentLeadersScreen(),
        GradingAdminScreen(),
      ]),
      // Phase 19 — admin can broadcast school-wide, class-wide, or
      // course-wide from anywhere in the office.
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => AnnouncementComposerSheet.open(context),
        icon: const Icon(Icons.campaign_outlined),
        label: const Text('Announce'),
      ),
    );
  }
}

// ============================================================================
// Sections tab
// ============================================================================
class _SectionsTab extends ConsumerWidget {
  const _SectionsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(sectionsProvider);
    return Scaffold(
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (sections) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(sectionsProvider),
          child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
            _SummaryStrip(label: 'sections', value: '${sections.length}'),
            const SizedBox(height: AppSpacing.md),
            for (final s in sections) _SectionRow(section: s),
          ]),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          final name = await _promptText(context, title: 'New section', hint: 'e.g. Elementary');
          if (name == null || name.trim().isEmpty) return;
          try {
            await ApiService.instance.createSection(name: name.trim());
            ref.invalidate(sectionsProvider);
          } on ApiException catch (e) {
            if (context.mounted) _snack(context, e.message);
          }
        },
        icon: const Icon(Icons.add),
        label: const Text('Add section'),
      ),
    );
  }
}

class _SectionRow extends ConsumerWidget {
  final Section section;
  const _SectionRow({required this.section});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: AppColors.primarySoft,
          child: Text('${section.orderIndex}',
              style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700)),
        ),
        title: Text(section.name, style: AppTextStyles.bodyStrong(context)),
        trailing: PopupMenuButton<String>(
          onSelected: (v) async {
            if (v == 'delete') {
              try {
                await ApiService.instance.deleteSection(section.id);
                ref.invalidate(sectionsProvider);
              } on ApiException catch (e) {
                if (context.mounted) _snack(context, e.message);
              }
            } else if (v == 'rename') {
              final name = await _promptText(context,
                  title: 'Rename section', hint: section.name);
              if (name == null || name.trim().isEmpty) return;
              try {
                await ApiService.instance.updateSection(section.id, name: name.trim());
                ref.invalidate(sectionsProvider);
              } on ApiException catch (e) {
                if (context.mounted) _snack(context, e.message);
              }
            }
          },
          itemBuilder: (_) => const [
            PopupMenuItem(value: 'rename', child: Text('Rename')),
            PopupMenuItem(value: 'delete', child: Text('Delete')),
          ],
        ),
      ),
    );
  }
}

// ============================================================================
// Grades tab
// ============================================================================
class _GradesTab extends ConsumerWidget {
  const _GradesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final gradesAsync = ref.watch(gradesProvider);
    final sectionsAsync = ref.watch(sectionsProvider);
    return Scaffold(
      body: gradesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (grades) {
          if (grades.isEmpty) {
            return const EmptyState(
              icon: Icons.grade_outlined,
              title: 'No grades yet',
              message: 'Add a grade to start building the school curriculum.',
            );
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(gradesProvider),
            child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
              for (final g in grades) _GradeRow(grade: g),
            ]),
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          final sections = sectionsAsync.value ?? const <Section>[];
          final res = await _promptGrade(context, sections: sections);
          if (res == null) return;
          try {
            await ApiService.instance.createGrade(
              name: res.$1,
              sectionId: res.$2,
              orderIndex: res.$3,
            );
            ref.invalidate(gradesProvider);
          } on ApiException catch (e) {
            if (context.mounted) _snack(context, e.message);
          }
        },
        icon: const Icon(Icons.add),
        label: const Text('Add grade'),
      ),
    );
  }
}

class _GradeRow extends ConsumerWidget {
  final Grade grade;
  const _GradeRow({required this.grade});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        title: Text(grade.name, style: AppTextStyles.bodyStrong(context)),
        subtitle: Text(grade.sectionName ?? 'no section', style: AppTextStyles.caption(context)),
        trailing: TextButton.icon(
          onPressed: () {
            Navigator.of(context).push(
              fadeThroughRoute(GradeCurriculumScreen(gradeId: grade.id, gradeName: grade.name)),
            );
          },
          icon: const Icon(Icons.school_outlined, size: 18),
          label: const Text('Curriculum'),
        ),
      ),
    );
  }
}

// ============================================================================
// Classes tab
// ============================================================================
class _ClassesTab extends ConsumerStatefulWidget {
  const _ClassesTab();
  @override
  ConsumerState<_ClassesTab> createState() => _ClassesTabState();
}

class _ClassesTabState extends ConsumerState<_ClassesTab> {
  String? _gradeFilter;

  @override
  Widget build(BuildContext context) {
    final gradesAsync = ref.watch(gradesProvider);
    final classesAsync = ref.watch(classesProvider(_gradeFilter));
    return Scaffold(
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl, vertical: AppSpacing.md),
          child: gradesAsync.when(
            loading: () => const SizedBox.shrink(),
            error: (_, _) => const SizedBox.shrink(),
            data: (grades) => Wrap(
              spacing: AppSpacing.sm,
              children: [
                FilterChip(
                  label: const Text('All'),
                  selected: _gradeFilter == null,
                  onSelected: (_) => setState(() => _gradeFilter = null),
                ),
                for (final g in grades)
                  FilterChip(
                    label: Text(g.name),
                    selected: _gradeFilter == g.id,
                    onSelected: (_) => setState(() => _gradeFilter = g.id),
                  ),
              ],
            ),
          ),
        ),
        Expanded(
          child: classesAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text(friendlyError(e))),
            data: (classes) {
              if (classes.isEmpty) {
                return const EmptyState(
                  icon: Icons.class_outlined,
                  title: 'No classes yet',
                  message: 'Create a class under a grade to start building your roster.',
                );
              }
              return RefreshIndicator(
                onRefresh: () async => ref.invalidate(classesProvider),
                child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
                  for (final c in classes) _ClassRow(schoolClass: c),
                ]),
              );
            },
          ),
        ),
      ]),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          final grades = gradesAsync.value ?? const <Grade>[];
          if (grades.isEmpty) {
            _snack(context, 'Create a grade first.');
            return;
          }
          final instructors = await ApiService.instance.listInstructors();
          // Phase 10 audit fix M5: guard context after the await.
          if (!context.mounted) return;
          final res = await _promptClass(context, grades: grades, instructors: instructors);
          if (res == null) return;
          try {
            await ApiService.instance.createClass(
              gradeId: res.$1,
              name: res.$2,
              homeroomTeacherId: res.$3,
            );
            ref.invalidate(classesProvider);
          } on ApiException catch (e) {
            if (context.mounted) _snack(context, e.message);
          }
        },
        icon: const Icon(Icons.add),
        label: const Text('Add class'),
      ),
    );
  }
}

class _ClassRow extends StatelessWidget {
  final SchoolClass schoolClass;
  const _ClassRow({required this.schoolClass});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: AppColors.primary,
          child: Text(
            schoolClass.name.isNotEmpty ? schoolClass.name[0].toUpperCase() : '?',
            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
          ),
        ),
        title: Text(schoolClass.name, style: AppTextStyles.bodyStrong(context)),
        subtitle: Text(
          '${schoolClass.gradeName ?? "no grade"} · ${schoolClass.homeroomTeacherName ?? "no homeroom"} · ${schoolClass.studentCount} students',
          style: AppTextStyles.caption(context),
        ),
        // Phase 12: quick-access attendance for admin (per plan §M/admin).
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
            tooltip: 'Timetable',
            icon: const Icon(Icons.event_note_rounded, color: AppColors.primary),
            onPressed: () {
              Navigator.of(context).push(fadeThroughRoute(
                TimetableEditorScreen(
                  classId: schoolClass.id,
                  className: schoolClass.name,
                  gradeId: schoolClass.gradeId,
                ),
              ));
            },
          ),
          IconButton(
            tooltip: 'Take attendance',
            icon: const Icon(Icons.fact_check_rounded, color: AppColors.accent),
            onPressed: () {
              Navigator.of(context).push(fadeThroughRoute(
                AttendanceTakeScreen(
                  classId: schoolClass.id,
                  className: schoolClass.name,
                ),
              ));
            },
          ),
          const TrailingChevron(),
        ]),
        onTap: () {
          Navigator.of(context).push(
            fadeThroughRoute(ClassDetailScreen(classId: schoolClass.id)),
          );
        },
      ),
    );
  }
}

// ============================================================================
// Students tab
// ============================================================================
class _StudentsTab extends ConsumerWidget {
  const _StudentsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final unassignedAsync = ref.watch(unassignedStudentsProvider);
    return unassignedAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text(friendlyError(e))),
      data: (unassigned) => RefreshIndicator(
        onRefresh: () async => ref.invalidate(unassignedStudentsProvider),
        child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
          // Phase 20 — CSV bulk-import entry point at the top of the tab.
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              side: const BorderSide(color: AppColors.border),
            ),
            child: ListTile(
              leading: const CircleAvatar(
                backgroundColor: AppColors.primarySoft,
                child: Icon(Icons.upload_file_outlined,
                    color: AppColors.primaryDark),
              ),
              title: Text('Bulk import users from CSV',
                  style: AppTextStyles.body(context)
                      .copyWith(fontWeight: FontWeight.w700)),
              subtitle: Text(
                  'Create or update students + teachers in one shot. '
                  'Rerunning is safe — matched rows are updated, not duplicated.',
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
              trailing: const TrailingChevron(),
              onTap: () {
                Navigator.of(context).push(fadeThroughRoute(
                  const BulkImportScreen(),
                ));
              },
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          // Phase 25 — CSV data export.
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              side: const BorderSide(color: AppColors.border),
            ),
            child: ListTile(
              leading: const CircleAvatar(
                backgroundColor: AppColors.successSoft,
                child: Icon(Icons.file_download_outlined,
                    color: AppColors.success),
              ),
              title: Text('Export data to CSV',
                  style: AppTextStyles.body(context)
                      .copyWith(fontWeight: FontWeight.w700)),
              subtitle: Text(
                  'Users, enrollments, grades, or attendance — for offline analysis.',
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
              trailing: const TrailingChevron(),
              onTap: () {
                Navigator.of(context).push(fadeThroughRoute(
                  const DataExportScreen(),
                ));
              },
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          if (unassigned.isEmpty)
            const EmptyState(
              icon: Icons.people_alt_outlined,
              title: 'Everyone is placed',
              message:
                  'No unassigned students. New rosters land in this tab first when they need a class.',
            )
          else ...[
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.md),
              child: Text('Unassigned (${unassigned.length}) — need a class',
                  style: AppTextStyles.micro(context, color: AppColors.textMuted)),
            ),
            for (final s in unassigned) _StudentRow(student: s, warn: true),
          ],
        ]),
      ),
    );
  }
}

class _StudentRow extends StatelessWidget {
  final AppUser student;
  final bool warn;
  const _StudentRow({required this.student, this.warn = false});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: warn ? AppColors.warningSoft : null,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
        side: warn
            ? BorderSide(color: AppColors.warning.withValues(alpha: 0.4))
            : BorderSide(color: AppColors.border),
      ),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: AppColors.accent,
          child: Text(student.name.isNotEmpty ? student.name[0].toUpperCase() : '?',
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
        ),
        title: Text(student.name, style: AppTextStyles.bodyStrong(context)),
        subtitle: Text(student.email, style: AppTextStyles.caption(context)),
        trailing: const TrailingChevron(),
        onTap: () {
          Navigator.of(context).push(
            fadeThroughRoute(StudentDetailScreen(studentId: student.id)),
          );
        },
      ),
    );
  }
}

// ============================================================================
// Helpers
// ============================================================================
void _snack(BuildContext ctx, String msg) {
  ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(msg)));
}

/// Small stat strip used at the top of admin tabs. Matches the mockup's
/// summary bar (bold number, uppercase tiny label).
class _SummaryStrip extends StatelessWidget {
  final String label;
  final String value;
  const _SummaryStrip({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    const c = AppColors.primary;
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.md, horizontal: AppSpacing.lg),
        child: Row(children: [
          Text(value,
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.w800,
                color: c,
              )),
          const SizedBox(width: AppSpacing.md),
          Text(
            label.toUpperCase(),
            style: const TextStyle(
              fontSize: 11,
              letterSpacing: 0.9,
              fontWeight: FontWeight.w700,
              color: AppColors.textMuted,
            ),
          ),
        ]),
      ),
    );
  }
}

Future<String?> _promptText(BuildContext ctx, {required String title, String? hint}) async {
  // Phase 10 audit fix M4: dispose the controller when the dialog closes,
  // regardless of cancel/save/dismiss. Was leaking one controller per open.
  final ctrl = TextEditingController();
  try {
    return await showDialog<String>(
      context: ctx,
      builder: (d) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: InputDecoration(hintText: hint),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () => Navigator.pop(d, ctrl.text),
            child: const Text('Save'),
          ),
        ],
      ),
    );
  } finally {
    ctrl.dispose();
  }
}

Future<(String, String?, int)?> _promptGrade(BuildContext ctx, {required List<Section> sections}) async {
  // Phase 10 audit fix M4: dispose controllers on dialog close.
  final nameCtrl = TextEditingController();
  final orderCtrl = TextEditingController(text: '0');
  String? selectedSection = sections.isNotEmpty ? sections.first.id : null;
  try {
    return await showDialog<(String, String?, int)>(
    context: ctx,
    builder: (d) => StatefulBuilder(builder: (d, setState) {
      return AlertDialog(
        title: const Text('New grade'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: nameCtrl,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Name', hintText: 'e.g. Grade 9'),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String?>(
                initialValue: selectedSection,
                decoration: const InputDecoration(labelText: 'Section'),
                items: [
                  const DropdownMenuItem<String?>(value: null, child: Text('(none)')),
                  for (final s in sections) DropdownMenuItem(value: s.id, child: Text(s.name)),
                ],
                onChanged: (v) => setState(() => selectedSection = v),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: orderCtrl,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Order index'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () {
              if (nameCtrl.text.trim().isEmpty) return;
              Navigator.pop(d, (
                nameCtrl.text.trim(),
                selectedSection,
                int.tryParse(orderCtrl.text) ?? 0,
              ));
            },
            child: const Text('Create'),
          ),
        ],
      );
    }),
  );
  } finally {
    nameCtrl.dispose();
    orderCtrl.dispose();
  }
}

Future<(String, String, String?)?> _promptClass(
  BuildContext ctx, {
  required List<Grade> grades,
  required List<AppUser> instructors,
}) async {
  // Phase 10 audit fix M4: dispose controller on dialog close.
  final nameCtrl = TextEditingController();
  String selectedGrade = grades.first.id;
  String? selectedTeacher;
  try {
    return await showDialog<(String, String, String?)>(
    context: ctx,
    builder: (d) => StatefulBuilder(builder: (d, setState) {
      return AlertDialog(
        title: const Text('New class'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<String>(
                initialValue: selectedGrade,
                decoration: const InputDecoration(labelText: 'Grade'),
                items: [for (final g in grades) DropdownMenuItem(value: g.id, child: Text(g.name))],
                onChanged: (v) => setState(() => selectedGrade = v ?? selectedGrade),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: nameCtrl,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Name', hintText: 'e.g. 9-A'),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String?>(
                initialValue: selectedTeacher,
                decoration: const InputDecoration(labelText: 'Homeroom teacher (optional)'),
                items: [
                  const DropdownMenuItem<String?>(value: null, child: Text('(none)')),
                  for (final t in instructors) DropdownMenuItem(value: t.id, child: Text(t.name)),
                ],
                onChanged: (v) => setState(() => selectedTeacher = v),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () {
              if (nameCtrl.text.trim().isEmpty) return;
              Navigator.pop(d, (selectedGrade, nameCtrl.text.trim(), selectedTeacher));
            },
            child: const Text('Create'),
          ),
        ],
      );
    }),
  );
  } finally {
    nameCtrl.dispose();
  }
}
