import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/course.dart';
import '../../models/lesson.dart';
import '../../models/module.dart';
import '../../core/utils/transitions.dart';
import '../../providers/courses_provider.dart';
import '../../services/api_service.dart';
import 'gradebook_screen.dart';
import 'question_bank_screen.dart';
import 'lesson_editor_sheet.dart';
import 'quiz_editor_screen.dart';
import 'rubric_editor_screen.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/trailing_chevron.dart';

/// Author view for a course: add/rename/delete modules and lessons, publish.
///
/// The server enforces `can_edit_course_content` (admin + department leader).
/// The client just shows this screen; on 403 it surfaces the error and
/// leaves state untouched.
class CourseEditorScreen extends ConsumerWidget {
  final String courseId;
  const CourseEditorScreen({super.key, required this.courseId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(courseDetailProvider(courseId));
    return Scaffold(
      appBar: AppBar(
        title: async.maybeWhen(
          data: (c) => Text('Edit — ${c.title}', style: AppTextStyles.h3(context)),
          orElse: () => const Text('Edit course'),
        ),
        actions: [
          async.maybeWhen(
            data: (c) => IconButton(
              tooltip: 'Rubric',
              icon: const Icon(Icons.rule_outlined),
              onPressed: () {
                Navigator.of(context).push(
                  fadeThroughRoute(RubricEditorScreen(
                    courseId: c.id, courseTitle: c.title,
                  )),
                );
              },
            ),
            orElse: () => const SizedBox.shrink(),
          ),
          async.maybeWhen(
            data: (c) => IconButton(
              tooltip: 'Question bank',
              icon: const Icon(Icons.quiz_outlined),
              onPressed: () {
                Navigator.of(context).push(
                  fadeThroughRoute(QuestionBankScreen(
                    courseId: c.id, courseTitle: c.title,
                  )),
                );
              },
            ),
            orElse: () => const SizedBox.shrink(),
          ),
          async.maybeWhen(
            data: (c) => IconButton(
              tooltip: 'Gradebook',
              icon: const Icon(Icons.grid_on_outlined),
              onPressed: () {
                Navigator.of(context).push(
                  fadeThroughRoute(GradebookScreen(
                    courseId: c.id, courseTitle: c.title,
                  )),
                );
              },
            ),
            orElse: () => const SizedBox.shrink(),
          ),
          async.maybeWhen(
            data: (c) => _PublishButton(course: c, onChanged: () => _reload(ref)),
            orElse: () => const SizedBox.shrink(),
          ),
        ],
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (course) => RefreshIndicator(
          onRefresh: () async => _reload(ref),
          child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
            _CourseHeaderCard(course: course),
            const SizedBox(height: AppSpacing.lg),
            for (int i = 0; i < course.modules.length; i++)
              _ModuleCard(
                course: course,
                module: course.modules[i],
                index: i,
                onChanged: () => _reload(ref),
              ),
            const SizedBox(height: AppSpacing.md),
            OutlinedButton.icon(
              onPressed: () => _addModule(context, ref, course),
              icon: const Icon(Icons.add),
              label: const Text('Add module'),
            ),
          ]),
        ),
      ),
    );
  }

  void _reload(WidgetRef ref) => ref.invalidate(courseDetailProvider(courseId));

  Future<void> _addModule(BuildContext ctx, WidgetRef ref, Course course) async {
    // Phase 10 audit fix M4: dispose controller on dialog close.
    final ctrl = TextEditingController();
    String? title;
    try {
      title = await showDialog<String>(
        context: ctx,
        builder: (d) => AlertDialog(
          title: const Text('New module'),
          content: TextField(
            controller: ctrl,
            autofocus: true,
            decoration: const InputDecoration(hintText: 'e.g. Foundations'),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
            ElevatedButton(
              onPressed: () => Navigator.pop(d, ctrl.text.trim()),
              child: const Text('Create'),
            ),
          ],
        ),
      );
    } finally {
      ctrl.dispose();
    }
    if (title == null || title.isEmpty) return;
    try {
      await ApiService.instance.createModule(course.id, title: title);
      _reload(ref);
    } on ApiException catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

// ============================================================================
// Header card
// ============================================================================
class _CourseHeaderCard extends StatelessWidget {
  final Course course;
  const _CourseHeaderCard({required this.course});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(course.title, style: AppTextStyles.h2(context))),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
              decoration: BoxDecoration(
                color: course.isPublished ? AppColors.successSoft : AppColors.warningSoft,
                borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
              ),
              child: Text(
                course.isPublished ? 'PUBLISHED' : 'DRAFT',
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.6,
                  color: course.isPublished ? AppColors.success : AppColors.warning,
                ),
              ),
            ),
          ]),
          const SizedBox(height: AppSpacing.xs),
          Text(
            '${course.gradeName ?? "no grade"} · ${AppConstants.prettyCategory(course.category)}${course.electiveGroup != null ? " · ${AppConstants.prettyElectiveGroup(course.electiveGroup!)}" : ""}',
            style: AppTextStyles.caption(context),
          ),
          if (course.enrolledCount != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Text('${course.enrolledCount} enrolled', style: AppTextStyles.caption(context)),
          ],
        ]),
      ),
    );
  }
}

// ============================================================================
// Publish button
// ============================================================================
class _PublishButton extends StatelessWidget {
  final Course course;
  final VoidCallback onChanged;
  const _PublishButton({required this.course, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.only(end: AppSpacing.md),
      child: TextButton.icon(
        onPressed: () async {
          try {
            if (course.isPublished) {
              await ApiService.instance.unpublishCourse(course.id);
            } else {
              await ApiService.instance.publishCourse(course.id);
            }
            onChanged();
          } on ApiException catch (e) {
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
            }
          }
        },
        icon: Icon(course.isPublished ? Icons.pause_circle_outline_rounded : Icons.rocket_launch_rounded),
        label: Text(course.isPublished ? 'Unpublish' : 'Publish'),
      ),
    );
  }
}

// ============================================================================
// Module card
// ============================================================================
class _ModuleCard extends StatelessWidget {
  final Course course;
  final CourseModule module;
  final int index;
  final VoidCallback onChanged;
  const _ModuleCard({
    required this.course,
    required this.module,
    required this.index,
    required this.onChanged,
  });

  Future<void> _addLesson(BuildContext ctx) async {
    final draft = await showModalBottomSheet<LessonDraft>(
      context: ctx,
      isScrollControlled: true,
      builder: (_) => const LessonEditorSheet(),
    );
    if (draft == null) return;
    try {
      await ApiService.instance.createLesson(
        module.id,
        title: draft.title,
        type: draft.type,
        contentUrl: draft.contentUrl,
        contentText: draft.contentText,
        durationMinutes: draft.durationMinutes,
      );
      onChanged();
    } on ApiException catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _deleteModule(BuildContext ctx) async {
    final ok = await _confirm(ctx, 'Delete module "${module.title}"? All its lessons will be removed too.');
    if (ok != true) return;
    try {
      await ApiService.instance.deleteModule(module.id);
      onChanged();
    } on ApiException catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _deleteLesson(BuildContext ctx, Lesson lesson) async {
    final ok = await _confirm(ctx, 'Delete lesson "${lesson.title}"?');
    if (ok != true) return;
    try {
      await ApiService.instance.deleteLesson(lesson.id);
      onChanged();
    } on ApiException catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _editLesson(BuildContext ctx, Lesson lesson) async {
    final draft = await showModalBottomSheet<LessonDraft>(
      context: ctx,
      isScrollControlled: true,
      builder: (_) => LessonEditorSheet(existing: lesson),
    );
    if (draft == null) return;
    try {
      await ApiService.instance.updateLesson(
        lesson.id,
        title: draft.title,
        type: draft.type,
        // Only send content that matches the chosen type — null the other side.
        contentUrl: draft.type == 'text' ? '' : (draft.contentUrl ?? ''),
        contentText: draft.type == 'text' ? (draft.contentText ?? '') : '',
        durationMinutes: draft.durationMinutes,
      );
      onChanged();
    } on ApiException catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.lg),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            CircleAvatar(
              radius: 14,
              backgroundColor: AppColors.primarySoft,
              child: Text(
                '${index + 1}',
                style: const TextStyle(
                  color: AppColors.primary,
                  fontSize: 10,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(child: Text(module.title, style: AppTextStyles.h3(context))),
            IconButton(
              icon: const Icon(Icons.delete_outline_rounded, size: 20),
              color: AppColors.danger,
              tooltip: 'Delete module',
              onPressed: () => _deleteModule(context),
            ),
          ]),
          const Divider(height: 20),
          for (final l in module.lessons)
            _LessonRow(
              lesson: l,
              onEdit: () => _editLesson(context, l),
              onDelete: () => _deleteLesson(context, l),
            ),
          for (final q in module.quizzes)
            ListTile(
              contentPadding: EdgeInsets.zero,
              dense: true,
              leading: const Icon(Icons.quiz_outlined, color: AppColors.accent),
              title: Text(q.title, style: AppTextStyles.body(context)),
              subtitle: Text(
                '${q.isPublished ? "Published" : "Draft"} · ${q.totalPoints} pts',
                style: AppTextStyles.caption(context),
              ),
              trailing: const TrailingChevron(),
              onTap: () {
                Navigator.of(context).push(
                  fadeThroughRoute(QuizEditorScreen(quizId: q.id)),
                );
              },
            ),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _addLesson(context),
                icon: const Icon(Icons.add),
                label: const Text('Add lesson'),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _addQuiz(context),
                icon: const Icon(Icons.quiz_outlined),
                label: const Text('Add quiz'),
              ),
            ),
          ]),
        ]),
      ),
    );
  }

  Future<void> _addQuiz(BuildContext ctx) async {
    // Phase 10 audit fix M4: dispose controller on dialog close.
    final ctrl = TextEditingController();
    String? title;
    try {
      title = await showDialog<String>(
        context: ctx,
        builder: (d) => AlertDialog(
          title: const Text('New quiz'),
          content: TextField(
            controller: ctrl,
            autofocus: true,
            decoration: const InputDecoration(hintText: 'e.g. Pop quiz — foundations'),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
            ElevatedButton(
              onPressed: () => Navigator.pop(d, ctrl.text.trim()),
              child: const Text('Create'),
            ),
          ],
        ),
      );
    } finally {
      ctrl.dispose();
    }
    if (title == null || title.isEmpty) return;
    try {
      final q = await ApiService.instance.createQuiz(module.id, title: title);
      onChanged();
      if (ctx.mounted) {
        Navigator.of(ctx).push(
          fadeThroughRoute(QuizEditorScreen(quizId: q.id)),
        );
      }
    } on ApiException catch (e) {
      if (ctx.mounted) {
        ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}

class _LessonRow extends StatelessWidget {
  final Lesson lesson;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  const _LessonRow({
    required this.lesson,
    required this.onEdit,
    required this.onDelete,
  });

  IconData get _icon => switch (lesson.type) {
        'video' => Icons.play_circle_outline_rounded,
        'pdf' => Icons.picture_as_pdf_outlined,
        _ => Icons.article_outlined,
      };

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onEdit,
      borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      child: ListTile(
        contentPadding: EdgeInsets.zero,
        dense: true,
        leading: Icon(_icon, color: AppColors.textSecondary),
        title: Text(lesson.title, style: AppTextStyles.body(context)),
        subtitle: lesson.durationMinutes == null
            ? null
            : Text('${lesson.durationMinutes} min', style: AppTextStyles.caption(context)),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
            icon: const Icon(Icons.edit_outlined, size: 20),
            color: AppColors.textSecondary,
            tooltip: 'Edit lesson',
            onPressed: onEdit,
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline_rounded, size: 20),
            color: AppColors.danger,
            tooltip: 'Delete lesson',
            onPressed: onDelete,
          ),
        ]),
      ),
    );
  }
}

Future<bool?> _confirm(BuildContext ctx, String message) {
  return showDialog<bool>(
    context: ctx,
    builder: (d) => AlertDialog(
      content: Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Cancel')),
        ElevatedButton(
          onPressed: () => Navigator.pop(d, true),
          style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
          child: const Text('Delete'),
        ),
      ],
    ),
  );
}
