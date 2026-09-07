import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../models/course.dart';
import '../../models/lesson.dart';
import '../../models/module.dart';
import '../../models/quiz.dart';
import '../../providers/auth_provider.dart';
import '../../providers/courses_provider.dart';
import '../../models/assignment.dart';
import '../../providers/assignments_provider.dart';
import '../instructor/assignment_editor_screen.dart';
import '../instructor/assignment_grading_screen.dart';
import '../instructor/course_editor_screen.dart';
import '../student/assignment_submit_screen.dart';
import '../student/lesson_viewer_screen.dart';
import '../student/quiz_viewer_screen.dart';
import '../../core/utils/friendly_error.dart';

class CourseDetailScreen extends ConsumerWidget {
  final String courseId;
  final Course? seed;

  /// Phase 6: when a parent opens a course from their child's dashboard,
  /// pass the child's name to render the "Viewing X's course" banner and
  /// switch the CTA + module tiles into read-only mode. Non-null → parent view.
  final String? parentViewChildName;

  const CourseDetailScreen({
    super.key,
    required this.courseId,
    this.seed,
    this.parentViewChildName,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(courseDetailProvider(courseId));
    return Scaffold(
      body: async.when(
        loading: () => _Skeleton(seed: seed),
        error: (e, _) => _ErrorState(
          message: friendlyError(e),
          onRetry: () => ref.invalidate(courseDetailProvider(courseId)),
        ),
        data: (course) => _CourseBody(
          course: course,
          parentViewChildName: parentViewChildName,
        ),
      ),
    );
  }
}

class _CourseBody extends ConsumerStatefulWidget {
  final Course course;
  final String? parentViewChildName;
  const _CourseBody({required this.course, this.parentViewChildName});

  @override
  ConsumerState<_CourseBody> createState() => _CourseBodyState();
}

class _CourseBodyState extends ConsumerState<_CourseBody> {
  // Phase 19 — one key per module so the FAB → bottom-sheet jumper can
  // ensure-visible a specific module. Regenerated on module-count changes.
  late List<GlobalKey> _moduleKeys;

  @override
  void initState() {
    super.initState();
    _moduleKeys =
        List.generate(widget.course.modules.length, (_) => GlobalKey());
  }

  @override
  void didUpdateWidget(covariant _CourseBody old) {
    super.didUpdateWidget(old);
    if (widget.course.modules.length != _moduleKeys.length) {
      _moduleKeys =
          List.generate(widget.course.modules.length, (_) => GlobalKey());
    }
  }

  @override
  Widget build(BuildContext context) {
    final course = widget.course;
    final parentViewChildName = widget.parentViewChildName;
    final user = ref.watch(authProvider).user;
    final totalLessons = course.modules.fold<int>(0, (s, m) => s + m.lessons.length);
    final isEnrolled = course.myEnrollment != null && course.myEnrollment!.isActive;
    final isOwner = user != null && (user.isAdmin || user.isInstructor);
    final isParentView = parentViewChildName != null;

    final scroll = CustomScrollView(slivers: [
      SliverAppBar(
        expandedHeight: 240,
        pinned: true,
        flexibleSpace: FlexibleSpaceBar(background: _HeroImage(course: course)),
      ),
      SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.xs,
                children: [
                  if (isEnrolled)
                    _pill('ENROLLED', bg: AppColors.successSoft, fg: AppColors.success),
                  _pill(AppConstants.prettyCategory(course.category)),
                  if (course.gradeName != null) _pill(course.gradeName!),
                  _pill('${course.modules.length} mod · $totalLessons les'),
                  if (course.isElective)
                    _pill(
                      AppConstants.prettyElectiveGroup(course.electiveGroup!),
                      bg: AppColors.accentSoft,
                      fg: AppColors.accentText,
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              Text(course.title, style: AppTextStyles.h1(context)),
              if ((course.instructorName ?? '').isNotEmpty) ...[
                const SizedBox(height: AppSpacing.xs),
                Text(course.instructorName!,
                    style: AppTextStyles.caption(context, color: AppColors.textMuted)),
              ],
              const SizedBox(height: AppSpacing.lg),
              if (course.description.trim().isNotEmpty)
                Text(course.description, style: AppTextStyles.body(context)),
              const SizedBox(height: AppSpacing.lg),
              if (parentViewChildName != null)
                _ParentBanner(childName: parentViewChildName)
              else
                _CtaSection(course: course, isEnrolled: isEnrolled, isOwner: isOwner),
              const SizedBox(height: AppSpacing.xl),
              Text('Course outline', style: AppTextStyles.h2(context)),
              const SizedBox(height: AppSpacing.md),
            ],
          ),
        ),
      ),
      // Phase 19 — materialize modules eagerly (not `SliverList.builder`)
      // so the module-jump FAB can `ensureVisible` a module whose tile
      // would otherwise be lazy-built off-screen.
      SliverList(
        delegate: SliverChildListDelegate([
          for (int i = 0; i < course.modules.length; i++)
            KeyedSubtree(
              key: _moduleKeys[i],
              child: _ModuleBlock(
                course: course,
                module: course.modules[i],
                index: i,
                canOpen: isEnrolled || isOwner || isParentView,
                parentViewChildName: parentViewChildName,
              ),
            ),
        ]),
      ),
      // Phase 14: assignments live at course scope (each row shows its
      // module title) — separate from the module outline above.
      SliverToBoxAdapter(
        child: _AssignmentsSection(
          courseId: course.id,
          firstModuleId: course.modules.isNotEmpty ? course.modules.first.id : null,
          isOwner: isOwner,
          isEnrolled: isEnrolled,
          isParentView: isParentView,
        ),
      ),
      const SliverToBoxAdapter(child: SizedBox(height: AppSpacing.xxxl)),
    ]);

    // Phase 19 — module jump FAB. Only useful when there's more than one
    // module (otherwise the outline is short enough to scroll manually).
    final showFab = course.modules.length > 1;
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: scroll,
      floatingActionButton: showFab
          ? FloatingActionButton(
              tooltip: 'Jump to module',
              onPressed: () => _openModuleJumper(context, course),
              child: const Icon(Icons.list_alt_rounded),
            )
          : null,
    );
  }

  void _openModuleJumper(BuildContext context, Course course) {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (sheetCtx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
              child: Row(children: [
                Text('Jump to module',
                    style: AppTextStyles.h3(context)
                        .copyWith(fontWeight: FontWeight.w800)),
                const Spacer(),
                IconButton(
                  tooltip: 'Close',
                  onPressed: () => Navigator.of(sheetCtx).pop(),
                  icon: const Icon(Icons.close_rounded),
                ),
              ]),
            ),
            const Divider(height: 1, color: AppColors.divider),
            for (int i = 0; i < course.modules.length; i++)
              ListTile(
                leading: CircleAvatar(
                  radius: 14,
                  backgroundColor: AppColors.primarySoft,
                  child: Text('${i + 1}',
                      style: const TextStyle(
                          color: AppColors.primaryDark,
                          fontWeight: FontWeight.w800,
                          fontSize: 12)),
                ),
                title: Text(course.modules[i].title,
                    style: AppTextStyles.body(context)
                        .copyWith(fontWeight: FontWeight.w600)),
                subtitle: Text(
                    '${course.modules[i].lessons.length} lessons',
                    style: AppTextStyles.caption(context,
                        color: AppColors.textMuted)),
                onTap: () {
                  Navigator.of(sheetCtx).pop();
                  final ctx = _moduleKeys[i].currentContext;
                  if (ctx == null) return;
                  Scrollable.ensureVisible(
                    ctx,
                    duration: const Duration(milliseconds: 350),
                    curve: Curves.easeOutCubic,
                    alignment: 0.05,
                  );
                },
              ),
          ]),
        ),
      ),
    );
  }

  Widget _pill(String label, {Color? bg, Color? fg}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
      decoration: BoxDecoration(
        color: bg ?? AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(
        label.toUpperCase(),
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.6,
          color: fg ?? AppColors.textSecondary,
        ),
      ),
    );
  }
}

class _CtaSection extends StatelessWidget {
  final Course course;
  final bool isEnrolled;
  final bool isOwner;
  const _CtaSection({required this.course, required this.isEnrolled, required this.isOwner});

  @override
  Widget build(BuildContext context) {
    if (isEnrolled) {
      // Find first-incomplete lesson (Phase 3 gets real progress). For now,
      // just show a Continue CTA pointing at the very first lesson.
      final firstModule = course.modules.isNotEmpty ? course.modules.first : null;
      final firstLesson = firstModule?.lessons.isNotEmpty ?? false
          ? firstModule!.lessons.first
          : null;
      return SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: firstLesson == null
              ? null
              : () {
                  Navigator.of(context).push(
                    fadeThroughRoute(
                      LessonViewerScreen(
                        lessonId: firstLesson.id,
                        courseTitle: course.title,
                      ),
                    ),
                  );
                },
          icon: const Icon(Icons.play_arrow_rounded),
          label: Text(
            firstLesson == null ? 'No lessons yet' : 'Continue — "${firstLesson.title}"',
          ),
        ),
      );
    }
    if (isOwner) {
      final count = course.enrolledCount ?? 0;
      return Column(children: [
        Container(
          padding: const EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            color: AppColors.primarySoft,
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          ),
          child: Row(children: [
            const Icon(Icons.groups_rounded, color: AppColors.primary),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Text(
                '$count student${count == 1 ? "" : "s"} currently enrolled',
                style: AppTextStyles.bodyStrong(context, color: AppColors.primary),
              ),
            ),
          ]),
        ),
        const SizedBox(height: AppSpacing.md),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            onPressed: () {
              Navigator.of(context).push(
                fadeThroughRoute(CourseEditorScreen(courseId: course.id)),
              );
            },
            icon: const Icon(Icons.edit_outlined),
            label: const Text('Edit content'),
          ),
        ),
      ]);
    }
    // Student off roster.
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.border, style: BorderStyle.solid),
      ),
      child: Row(children: [
        const Icon(Icons.lock_outline_rounded, color: AppColors.textSecondary),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Text(
            "You're not enrolled in this course. Your teacher or the school office can add you.",
            style: AppTextStyles.caption(context),
          ),
        ),
      ]),
    );
  }
}

class _HeroImage extends StatelessWidget {
  final Course course;
  const _HeroImage({required this.course});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [AppColors.primary, AppColors.primaryDark],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: (course.thumbnailUrl != null && course.thumbnailUrl!.isNotEmpty)
          ? Stack(fit: StackFit.expand, children: [
              CachedNetworkImage(
                imageUrl: AppConstants.resolveMediaUrl(course.thumbnailUrl!),
                fit: BoxFit.cover,
                errorWidget: (_, _, _) => const SizedBox.shrink(),
              ),
              Container(
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    colors: [Colors.transparent, Color(0x80000000)],
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                  ),
                ),
              ),
            ])
          : const Center(
              child: Icon(Icons.menu_book_rounded, color: Colors.white54, size: 72),
            ),
    );
  }
}

class _ModuleBlock extends StatelessWidget {
  final Course course;
  final CourseModule module;
  final int index;
  final bool canOpen;
  final String? parentViewChildName;
  const _ModuleBlock({
    required this.course,
    required this.module,
    required this.index,
    required this.canOpen,
    this.parentViewChildName,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl, vertical: AppSpacing.sm),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                CircleAvatar(
                  radius: 14,
                  backgroundColor: AppColors.primarySoft,
                  child: Text('${index + 1}',
                      style: AppTextStyles.micro(context, color: AppColors.primary)),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(child: Text(module.title, style: AppTextStyles.h3(context))),
              ]),
              const SizedBox(height: AppSpacing.sm),
              for (final lesson in module.lessons)
                _LessonRow(
                  course: course, lesson: lesson, canOpen: canOpen,
                  parentViewChildName: parentViewChildName,
                ),
              for (final quiz in module.quizzes)
                _QuizRow(
                  course: course, quiz: quiz,
                  canOpen: canOpen && parentViewChildName == null,
                ),
              if (module.lessons.isEmpty && module.quizzes.isEmpty)
                Padding(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  child: Text('No lessons or quizzes yet.',
                      style: AppTextStyles.caption(context, color: AppColors.textMuted)),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _LessonRow extends StatelessWidget {
  final Course course;
  final Lesson lesson;
  final bool canOpen;
  final String? parentViewChildName;
  const _LessonRow({
    required this.course,
    required this.lesson,
    required this.canOpen,
    this.parentViewChildName,
  });

  IconData get _typeIcon => switch (lesson.type) {
        'video' => Icons.play_circle_outline_rounded,
        'pdf' => Icons.picture_as_pdf_outlined,
        _ => Icons.article_outlined,
      };

  @override
  Widget build(BuildContext context) {
    final locked = !canOpen;
    return InkWell(
      onTap: locked
          ? null
          : () {
              Navigator.of(context).push(
                fadeThroughRoute(
                  LessonViewerScreen(
                    lessonId: lesson.id,
                    courseTitle: course.title,
                    parentViewChildName: parentViewChildName,
                  ),
                ),
              );
            },
      borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          Icon(_typeIcon, size: 20, color: AppColors.textSecondary),
          const SizedBox(width: AppSpacing.md),
          Expanded(child: Text(lesson.title, style: AppTextStyles.body(context))),
          if (lesson.durationMinutes != null) ...[
            const SizedBox(width: AppSpacing.sm),
            Text('${lesson.durationMinutes}m',
                style: AppTextStyles.caption(context, color: AppColors.textMuted)),
          ],
          const SizedBox(width: AppSpacing.sm),
          Icon(
            locked ? Icons.lock_outline_rounded : Icons.play_arrow_rounded,
            size: 16,
            color: locked ? AppColors.textMuted : AppColors.success,
          ),
        ]),
      ),
    );
  }
}

class _Skeleton extends StatelessWidget {
  final Course? seed;
  const _Skeleton({this.seed});

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(slivers: [
      SliverAppBar(
        expandedHeight: 240,
        pinned: true,
        flexibleSpace: seed != null
            ? FlexibleSpaceBar(background: _HeroImage(course: seed!))
            : const FlexibleSpaceBar(
                background: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [AppColors.primary, AppColors.primaryDark],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                  ),
                ),
              ),
      ),
      const SliverToBoxAdapter(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.xl),
          child: Center(child: CircularProgressIndicator()),
        ),
      ),
    ]);
  }
}

class _ErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorState({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xxl),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.error_outline_rounded, size: 48, color: AppColors.danger),
          const SizedBox(height: AppSpacing.md),
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.md),
          OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
        ]),
      ),
    );
  }
}

class _QuizRow extends StatelessWidget {
  final Course course;
  final QuizSummary quiz;
  final bool canOpen;
  const _QuizRow({required this.course, required this.quiz, required this.canOpen});

  @override
  Widget build(BuildContext context) {
    final locked = !canOpen;
    return InkWell(
      onTap: locked
          ? null
          : () {
              Navigator.of(context).push(
                fadeThroughRoute(
                  QuizViewerScreen(quizId: quiz.id, courseTitle: course.title),
                ),
              );
            },
      borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [
          const Icon(Icons.quiz_outlined, size: 20, color: AppColors.accent),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(quiz.title,
                style: AppTextStyles.body(context).copyWith(fontWeight: FontWeight.w600)),
          ),
          // Phase 16 — the student's last mark, shown only when they have a
          // submitted attempt. Green when they passed, red when they didn't.
          if (quiz.hasMyHistory && quiz.myLastPercent != null) ...[
            _LastMarkChip(
              percent: quiz.myLastPercent!,
              passing: quiz.passingScore,
            ),
            const SizedBox(width: AppSpacing.sm),
          ],
          Text('${quiz.totalPoints} pts',
              style: AppTextStyles.caption(context, color: AppColors.textMuted)),
          const SizedBox(width: AppSpacing.sm),
          Icon(
            locked ? Icons.lock_outline_rounded : Icons.play_arrow_rounded,
            size: 16,
            color: locked ? AppColors.textMuted : AppColors.success,
          ),
        ]),
      ),
    );
  }
}

/// Phase 6: subtle banner at the top of a course when a parent opens it
/// from the child dashboard. Sets the tone that everything below is read-only.
class _ParentBanner extends StatelessWidget {
  final String childName;
  const _ParentBanner({required this.childName});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.primarySoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.3)),
      ),
      child: Row(children: [
        const Icon(Icons.remove_red_eye_outlined,
            color: AppColors.primaryDark, size: 20),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Text(
            "Viewing $childName's course · read-only",
            style: AppTextStyles.bodyStrong(context, color: AppColors.primaryDark),
          ),
        ),
      ]),
    );
  }
}

// ============================================================================
// Phase 14 — Assignments section on the course detail screen.
// ============================================================================
class _AssignmentsSection extends ConsumerWidget {
  final String courseId;
  final String? firstModuleId;
  final bool isOwner;
  final bool isEnrolled;
  final bool isParentView;
  const _AssignmentsSection({
    required this.courseId,
    required this.firstModuleId,
    required this.isOwner,
    required this.isEnrolled,
    required this.isParentView,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!(isOwner || isEnrolled || isParentView)) {
      return const SizedBox.shrink();
    }
    final async = ref.watch(courseAssignmentsProvider(courseId));
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.xl, vertical: AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text('Assignments', style: AppTextStyles.h2(context)),
            const Spacer(),
            if (isOwner && firstModuleId != null)
              TextButton.icon(
                onPressed: () {
                  Navigator.of(context).push(fadeThroughRoute(
                    AssignmentEditorScreen(
                      moduleId: firstModuleId!,
                      courseId: courseId,
                    ),
                  ));
                },
                icon: const Icon(Icons.add, size: 18),
                label: const Text('Add'),
              ),
          ]),
          const SizedBox(height: AppSpacing.md),
          async.when(
            loading: () => const Padding(
              padding: EdgeInsets.all(AppSpacing.md),
              child: LinearProgressIndicator(minHeight: 2),
            ),
            error: (e, _) => Text(friendlyError(e),
                style: AppTextStyles.caption(context, color: AppColors.textMuted)),
            data: (list) {
              if (list.isEmpty) {
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: Text('No assignments yet.',
                        style: AppTextStyles.caption(context,
                            color: AppColors.textMuted)),
                  ),
                );
              }
              return Column(children: [
                for (final a in list)
                  _AssignmentRow(
                    assignment: a,
                    isOwner: isOwner,
                    isParentView: isParentView,
                    courseId: courseId,
                  ),
              ]);
            },
          ),
        ],
      ),
    );
  }
}

class _AssignmentRow extends StatelessWidget {
  final Assignment assignment;
  final bool isOwner;
  final bool isParentView;
  final String courseId;
  const _AssignmentRow({
    required this.assignment,
    required this.isOwner,
    required this.isParentView,
    required this.courseId,
  });

  @override
  Widget build(BuildContext context) {
    final sub = assignment.mySubmission;
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        onTap: isParentView
            ? null
            : () {
                if (isOwner) {
                  Navigator.of(context).push(fadeThroughRoute(
                    AssignmentGradingScreen(
                      assignmentId: assignment.id,
                      assignmentTitle: assignment.title,
                      maxPoints: assignment.maxPoints,
                    ),
                  ));
                } else {
                  Navigator.of(context).push(fadeThroughRoute(
                    AssignmentSubmitScreen(assignmentId: assignment.id),
                  ));
                }
              },
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(children: [
            const Icon(Icons.assignment_outlined, color: AppColors.primary),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Expanded(
                      child: Text(assignment.title,
                          style: AppTextStyles.bodyStrong(context)),
                    ),
                    if (!assignment.isPublished)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppColors.surfaceMuted,
                          borderRadius:
                              BorderRadius.circular(AppSpacing.radiusPill),
                        ),
                        child: Text('DRAFT',
                            style: AppTextStyles.micro(context,
                                color: AppColors.textMuted)),
                      ),
                  ]),
                  if (assignment.dueAt != null)
                    Text(
                      'Due ${_fmtDate(assignment.dueAt!)}',
                      style: AppTextStyles.micro(context,
                          color: AppColors.textMuted),
                    ),
                ],
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            _statusPill(isOwner, sub),
          ]),
        ),
      ),
    );
  }

  static String _fmtDate(DateTime d) {
    final loc = d.toLocal();
    return '${loc.year}-${loc.month.toString().padLeft(2, "0")}-'
        '${loc.day.toString().padLeft(2, "0")} '
        '${loc.hour.toString().padLeft(2, "0")}:'
        '${loc.minute.toString().padLeft(2, "0")}';
  }

  Widget _statusPill(bool isOwner, AssignmentSubmission? sub) {
    if (isOwner) {
      return _pill('Grade', bg: AppColors.primarySoft, fg: AppColors.primaryDark);
    }
    if (sub == null) {
      return _pill('TO DO', bg: AppColors.dangerSoft, fg: AppColors.danger);
    }
    if (sub.isGraded) {
      return _pill(
        '${sub.gradedScore!.toStringAsFixed(0)}/${(sub.gradedMax ?? assignment.maxPoints).toStringAsFixed(0)}',
        bg: AppColors.successSoft, fg: AppColors.success,
      );
    }
    return _pill(sub.isLate ? 'SUBMITTED · LATE' : 'SUBMITTED',
        bg: sub.isLate ? AppColors.warningSoft : AppColors.primarySoft,
        fg: sub.isLate ? AppColors.warning : AppColors.primaryDark);
  }

  Widget _pill(String label, {required Color bg, required Color fg}) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
        ),
        child: Text(label,
            style: TextStyle(
                color: fg, fontSize: 11,
                fontWeight: FontWeight.w800, letterSpacing: 0.5)),
      );
}

/// Phase 16 — the student's last mark on a quiz, rendered inline next to
/// the "N pts" cell. Green when they passed, red when they didn't.
class _LastMarkChip extends StatelessWidget {
  final double percent;
  final int passing;
  const _LastMarkChip({required this.percent, required this.passing});

  @override
  Widget build(BuildContext context) {
    final passed = percent >= passing;
    final bg = passed ? AppColors.successSoft : AppColors.dangerSoft;
    final fg = passed ? AppColors.success : AppColors.danger;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text('Last ${percent.round()}%',
          style: TextStyle(
              color: fg, fontSize: 11,
              fontWeight: FontWeight.w700, letterSpacing: 0.3)),
    );
  }
}
