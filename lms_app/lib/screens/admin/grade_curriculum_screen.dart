import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../models/course.dart';
import '../../providers/school_providers.dart';
import '../../services/api_service.dart';
import '../catalog/course_detail_screen.dart';
import '../../core/utils/friendly_error.dart';

class GradeCurriculumScreen extends ConsumerWidget {
  final String gradeId;
  final String gradeName;
  const GradeCurriculumScreen({super.key, required this.gradeId, required this.gradeName});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(gradeCurriculumProvider(gradeId));
    return Scaffold(
      appBar: AppBar(title: Text('$gradeName curriculum', style: AppTextStyles.h2(context))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (c) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(gradeCurriculumProvider(gradeId)),
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            children: [
              Text('MANDATORY',
                  style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
              const SizedBox(height: AppSpacing.sm),
              for (final course in c.mandatory) _CourseRow(course: course),
              if (c.mandatory.isEmpty)
                _EmptyCard(text: 'No mandatory subjects yet.'),
              const SizedBox(height: AppSpacing.xl),
              Text('ELECTIVE GROUPS',
                  style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
              const SizedBox(height: AppSpacing.sm),
              for (final entry in c.electiveGroups.entries)
                _ElectiveGroupCard(group: entry.key, options: entry.value),
              if (c.electiveGroups.isEmpty)
                _EmptyCard(text: 'No elective groups defined yet.'),
            ],
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _createCourseFlow(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Add course'),
      ),
    );
  }

  Future<void> _createCourseFlow(BuildContext context, WidgetRef ref) async {
    final res = await _promptCourse(context);
    if (res == null) return;
    try {
      await ApiService.instance.createCourse(
        title: res.title,
        gradeId: gradeId,
        category: res.category,
        electiveGroup: res.electiveGroup,
        description: res.description,
      );
      ref.invalidate(gradeCurriculumProvider(gradeId));
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _CourseRow extends StatelessWidget {
  final Course course;
  const _CourseRow({required this.course});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: AppColors.primarySoft,
          child: Text(course.category.isNotEmpty ? course.category[0].toUpperCase() : '?',
              style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700)),
        ),
        title: Text(course.title, style: AppTextStyles.bodyStrong(context)),
        subtitle: Text(AppConstants.prettyCategory(course.category),
            style: AppTextStyles.caption(context)),
        trailing: course.isPublished
            ? const Chip(
                label: Text('Published', style: TextStyle(fontSize: 10)),
                backgroundColor: AppColors.successSoft,
              )
            : const Chip(
                label: Text('Draft', style: TextStyle(fontSize: 10)),
                backgroundColor: AppColors.warningSoft,
              ),
        onTap: () {
          Navigator.of(context).push(
            fadeThroughRoute(CourseDetailScreen(courseId: course.id)),
          );
        },
      ),
    );
  }
}

class _ElectiveGroupCard extends StatelessWidget {
  final String group;
  final List<Course> options;
  const _ElectiveGroupCard({required this.group, required this.options});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Chip(
              label: Text(AppConstants.prettyElectiveGroup(group),
                  style: const TextStyle(color: AppColors.accentText, fontWeight: FontWeight.w700)),
              backgroundColor: AppColors.accentSoft,
            ),
            const SizedBox(width: AppSpacing.sm),
            Text('Pick one', style: AppTextStyles.caption(context)),
          ]),
          const Divider(),
          for (final c in options) _CourseRow(course: c),
        ]),
      ),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  final String text;
  const _EmptyCard({required this.text});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Center(child: Text(text, style: AppTextStyles.caption(context))),
      ),
    );
  }
}

// ---- Prompt ----------------------------------------------------------------
class _CourseDraft {
  final String title;
  final String description;
  final String category;
  final String? electiveGroup;
  const _CourseDraft({
    required this.title,
    required this.description,
    required this.category,
    this.electiveGroup,
  });
}

Future<_CourseDraft?> _promptCourse(BuildContext ctx) async {
  // Phase 10 audit fix M4: dispose controllers on dialog close.
  final title = TextEditingController();
  final desc = TextEditingController();
  String category = 'general';
  String? electiveGroup;
  try {
    return await showDialog<_CourseDraft>(
    context: ctx,
    builder: (d) => StatefulBuilder(builder: (d, setState) {
      return AlertDialog(
        title: const Text('New course'),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: title, autofocus: true,
                  decoration: const InputDecoration(labelText: 'Title')),
              const SizedBox(height: AppSpacing.md),
              TextField(controller: desc, maxLines: 3,
                  decoration: const InputDecoration(labelText: 'Description')),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                initialValue: category,
                decoration: const InputDecoration(labelText: 'Department'),
                items: [
                  for (final c in AppConstants.courseCategories)
                    DropdownMenuItem(value: c, child: Text(AppConstants.prettyCategory(c))),
                ],
                onChanged: (v) => setState(() => category = v ?? 'general'),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String?>(
                initialValue: electiveGroup,
                decoration: const InputDecoration(labelText: 'Elective group (optional)'),
                items: [
                  const DropdownMenuItem<String?>(value: null, child: Text('(mandatory)')),
                  for (final g in AppConstants.electiveGroups)
                    DropdownMenuItem(value: g, child: Text(AppConstants.prettyElectiveGroup(g))),
                ],
                onChanged: (v) => setState(() => electiveGroup = v),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () {
              if (title.text.trim().isEmpty) return;
              Navigator.pop(d, _CourseDraft(
                title: title.text.trim(),
                description: desc.text.trim(),
                category: category,
                electiveGroup: electiveGroup,
              ));
            },
            child: const Text('Create'),
          ),
        ],
      );
    }),
  );
  } finally {
    title.dispose();
    desc.dispose();
  }
}
