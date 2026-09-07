import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/course.dart';
import '../../models/enrollment.dart';
import '../../core/utils/transitions.dart';
import '../../providers/school_providers.dart';
import '../../services/api_service.dart';
import 'admin_student_fees_screen.dart';
import 'student_parents_screen.dart';
import '../../core/widgets/trailing_chevron.dart';
import '../../core/widgets/warning_tile.dart';

/// Student detail — placement + electives.
///
/// Fetches:
///   * student's active enrollments (via listStudentEnrollments)
///   * student's pending electives (via getPendingElectives)
///   * the student's grade curriculum (to know what elective groups exist)
///
/// Then renders three sections:
///   1. Pending — no pick yet, offer alternatives
///   2. Current elective picks — with a Change button that warns before dropping
///   3. Mandatory (read-only) — auto-enrolled from placement
class StudentDetailScreen extends ConsumerStatefulWidget {
  final String studentId;
  const StudentDetailScreen({super.key, required this.studentId});
  @override
  ConsumerState<StudentDetailScreen> createState() => _StudentDetailScreenState();
}

class _StudentDetailScreenState extends ConsumerState<StudentDetailScreen> {
  Future<_Payload>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_Payload> _load() async {
    final api = ApiService.instance;
    final enrollments = await api.listStudentEnrollments(widget.studentId);
    final pending = await api.getPendingElectives(widget.studentId);
    // Any course.gradeId observed lets us fetch the curriculum. If none,
    // curriculum stays empty and we show pending/mandatory only.
    String? gradeId;
    for (final e in enrollments) {
      if (e.course?.gradeId != null && e.course!.gradeId!.isNotEmpty) {
        gradeId = e.course!.gradeId;
        break;
      }
    }
    Map<String, List<Course>> electiveOptions = const {};
    if (gradeId != null) {
      try {
        final curriculum = await api.getGradeCurriculum(gradeId);
        electiveOptions = curriculum.electiveGroups;
      } on ApiException {
        electiveOptions = const {};
      }
    }
    return _Payload(
      enrollments: enrollments,
      pending: pending,
      electiveOptions: electiveOptions,
    );
  }

  void _reload() {
    setState(() {
      _future = _load();
    });
    ref.invalidate(pendingElectivesProvider(widget.studentId));
  }

  /// Reset the student's password on their behalf.
  ///
  /// The school has no outbound email, so this is the whole of "I forgot my
  /// password": an admin generates a new one here and hands it over in
  /// person. The server signs the student out everywhere and requires them
  /// to choose their own on next sign-in.
  Future<void> _openResetPasswordDialog() async {
    final proceed = await showDialog<bool>(
      context: context,
      builder: (dctx) => AlertDialog(
        title: const Text('Reset password?'),
        content: const Text(
          'A new temporary password will be generated and shown once. The '
          'student is signed out on every device and must choose their own '
          'password the next time they sign in.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dctx, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(dctx, true),
            child: const Text('Reset'),
          ),
        ],
      ),
    );
    if (proceed != true || !mounted) return;

    try {
      final temporary = await ApiService.instance.adminResetPassword(
        userId: widget.studentId,
      );
      if (!mounted || temporary == null) return;
      await showDialog<void>(
        context: context,
        builder: (dctx) => AlertDialog(
          title: const Text('Temporary password'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Give this to the student. It is not shown again.'),
              const SizedBox(height: AppSpacing.md),
              SelectableText(
                temporary,
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: temporary));
                if (dctx.mounted) Navigator.pop(dctx);
              },
              child: const Text('Copy'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(dctx),
              child: const Text('Done'),
            ),
          ],
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    }
  }

  /// Phase 23 — confirm before soft-deleting a student. History is
  /// preserved; grades / attendance / certificates all stay searchable.
  Future<void> _openWithdrawDialog() async {
    final reasonCtrl = TextEditingController();
    final proceed = await showDialog<bool>(
      context: context,
      builder: (dctx) => AlertDialog(
        title: const Text('Withdraw student?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
                "This soft-deletes the student and drops their active enrollments. "
                "Grades, certificates, attendance, and transcript stay preserved."),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: reasonCtrl,
              maxLength: 500,
              maxLines: 3,
              decoration: const InputDecoration(
                labelText: 'Reason (optional)',
                border: OutlineInputBorder(),
                alignLabelWithHint: true,
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dctx, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
            onPressed: () => Navigator.pop(dctx, true),
            child: const Text('Withdraw'),
          ),
        ],
      ),
    );
    if (proceed != true || !mounted) return;
    try {
      await ApiService.instance.withdrawStudent(
        widget.studentId,
        reason: reasonCtrl.text.trim().isEmpty ? null : reasonCtrl.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Student withdrawn.')),
      );
      _reload();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Student', style: AppTextStyles.h2(context)),
        actions: [
          // Phase 23 — PDF report card + transcript + withdraw action.
          IconButton(
            tooltip: 'Report card PDF',
            icon: const Icon(Icons.picture_as_pdf_outlined),
            onPressed: () => launchUrl(
              Uri.parse(ApiService.instance.reportCardPdfUrl(widget.studentId)),
              mode: LaunchMode.platformDefault,
            ),
          ),
          IconButton(
            tooltip: 'Transcript PDF',
            icon: const Icon(Icons.description_outlined),
            onPressed: () => launchUrl(
              Uri.parse(ApiService.instance.transcriptPdfUrl(widget.studentId)),
              mode: LaunchMode.platformDefault,
            ),
          ),
          IconButton(
            tooltip: 'Reset password',
            icon: const Icon(Icons.lock_reset),
            onPressed: _openResetPasswordDialog,
          ),
          IconButton(
            tooltip: 'Withdraw student',
            icon: const Icon(Icons.person_off_outlined, color: AppColors.danger),
            onPressed: _openWithdrawDialog,
          ),
        ],
      ),
      body: FutureBuilder<_Payload>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text(snap.error.toString()));
          }
          final p = snap.data!;
          final active = p.enrollments.where((e) => e.status == 'active').toList();
          final mandatory = active.where((e) => e.enrolledVia == 'auto_mandatory').toList();
          final electivePicks = active.where((e) => e.enrolledVia == 'elective_choice').toList();

          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
              // ---- Pending section --------------------------------------
              if (p.pending.isNotEmpty)
                for (final pe in p.pending)
                  _PendingCard(
                    studentId: widget.studentId,
                    pending: pe,
                    onDone: _reload,
                  )
              else if (electivePicks.isNotEmpty || mandatory.isNotEmpty)
                Card(
                  color: AppColors.successSoft,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
                    side: BorderSide(color: AppColors.success.withValues(alpha: 0.35)),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: Row(children: [
                      const Icon(Icons.check_circle_outline, color: AppColors.success),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: Text('All electives assigned.',
                            style: AppTextStyles.bodyStrong(context, color: AppColors.success)),
                      ),
                    ]),
                  ),
                ),

              // ---- Current elective picks -----------------------------
              if (electivePicks.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.xl),
                Text('ELECTIVE PICKS',
                    style: AppTextStyles.micro(context, color: AppColors.textMuted)),
                const SizedBox(height: AppSpacing.sm),
                for (final e in electivePicks)
                  _CurrentElectiveCard(
                    studentId: widget.studentId,
                    enrollment: e,
                    allOptions: p.electiveOptions,
                    onDone: _reload,
                  ),
              ],

              // ---- Mandatory --------------------------------------------
              if (mandatory.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.xl),
                Text('AUTO-ENROLLED (MANDATORY)',
                    style: AppTextStyles.micro(context, color: AppColors.textMuted)),
                const SizedBox(height: AppSpacing.sm),
                for (final e in mandatory)
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.lock_outline_rounded,
                          color: AppColors.textSecondary),
                      title: Text(e.course?.title ?? '—',
                          style: AppTextStyles.bodyStrong(context)),
                      subtitle: Text(
                        e.course == null
                            ? ''
                            : AppConstants.prettyCategory(e.course!.category),
                        style: AppTextStyles.caption(context),
                      ),
                    ),
                  ),
              ],
              // ---- Phase 6: parent links -------------------------------
              const SizedBox(height: AppSpacing.xl),
              Text('LINKED PARENTS',
                  style: AppTextStyles.micro(context, color: AppColors.textMuted)),
              const SizedBox(height: AppSpacing.sm),
              Card(
                child: ListTile(
                  leading: const Icon(Icons.family_restroom_outlined,
                      color: AppColors.primary),
                  title: Text('Manage parent access',
                      style: AppTextStyles.bodyStrong(context)),
                  subtitle: Text(
                    'Add or remove parent accounts linked to this student.',
                    style: AppTextStyles.caption(context),
                  ),
                  trailing: const TrailingChevron(),
                  onTap: () {
                    Navigator.of(context).push(fadeThroughRoute(
                      StudentParentsScreen(
                        studentId: widget.studentId,
                        studentName: 'Student',
                      ),
                    ));
                  },
                ),
              ),

              // Phase 28 — fees drilldown.
              Card(
                child: ListTile(
                  leading: const Icon(Icons.receipt_long_outlined,
                      color: AppColors.primary),
                  title: Text('Fees & receipts',
                      style: AppTextStyles.bodyStrong(context)),
                  subtitle: Text(
                    'View and manage the student\'s fee items and payments.',
                    style: AppTextStyles.caption(context),
                  ),
                  trailing: const TrailingChevron(),
                  onTap: () {
                    Navigator.of(context).push(fadeThroughRoute(
                      AdminStudentFeesScreen(
                        studentId: widget.studentId,
                        studentName: 'Student',
                      ),
                    ));
                  },
                ),
              ),

              if (mandatory.isEmpty && electivePicks.isEmpty && p.pending.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpacing.xxxl),
                  child: Center(child: Text('No enrollments yet. Place this student in a class first.')),
                ),
            ]),
          );
        },
      ),
    );
  }
}

class _Payload {
  final List<Enrollment> enrollments;
  final List<PendingElective> pending;
  final Map<String, List<Course>> electiveOptions;
  _Payload({
    required this.enrollments,
    required this.pending,
    required this.electiveOptions,
  });
}

// ============================================================================
// Pending card — no current pick, offer alternatives
// ============================================================================
class _PendingCard extends StatelessWidget {
  final String studentId;
  final PendingElective pending;
  final VoidCallback onDone;
  const _PendingCard({
    required this.studentId,
    required this.pending,
    required this.onDone,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      color: AppColors.warningSoft,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
        side: BorderSide(color: AppColors.warning.withValues(alpha: 0.4)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.hourglass_top_rounded, color: AppColors.warning),
            const SizedBox(width: AppSpacing.md),
            Text(
              'Pending: ${AppConstants.prettyElectiveGroup(pending.group)}',
              style: AppTextStyles.bodyStrong(context, color: AppColors.accentText),
            ),
          ]),
          const SizedBox(height: AppSpacing.sm),
          Text('Pick one:', style: AppTextStyles.caption(context)),
          const SizedBox(height: AppSpacing.sm),
          for (final o in pending.options)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: OutlinedButton(
                onPressed: () async {
                  try {
                    await ApiService.instance.setElective(studentId, pending.group, o.courseId);
                    onDone();
                  } on ApiException catch (e) {
                    if (context.mounted) {
                      ScaffoldMessenger.of(context)
                          .showSnackBar(SnackBar(content: Text(e.message)));
                    }
                  }
                },
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size.fromHeight(44),
                  alignment: Alignment.centerLeft,
                ),
                child: Row(children: [
                  Expanded(child: Text(o.title)),
                  if (o.instructorName != null)
                    Text(o.instructorName!, style: AppTextStyles.caption(context)),
                  const SizedBox(width: AppSpacing.sm),
                  const Icon(Icons.add, size: 18),
                ]),
              ),
            ),
        ]),
      ),
    );
  }
}

// ============================================================================
// Current elective card — has a pick, offer Change with destructive warning
// ============================================================================
class _CurrentElectiveCard extends StatelessWidget {
  final String studentId;
  final Enrollment enrollment;
  final Map<String, List<Course>> allOptions;
  final VoidCallback onDone;
  const _CurrentElectiveCard({
    required this.studentId,
    required this.enrollment,
    required this.allOptions,
    required this.onDone,
  });

  @override
  Widget build(BuildContext context) {
    final course = enrollment.course;
    if (course == null || course.electiveGroup == null) return const SizedBox.shrink();
    final group = course.electiveGroup!;
    final options = allOptions[group] ?? const <Course>[];
    final others = options.where((c) => c.id != course.id).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 3),
              decoration: BoxDecoration(
                color: AppColors.accentSoft,
                borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
              ),
              child: Text(
                AppConstants.prettyElectiveGroup(group).toUpperCase(),
                style: const TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.6,
                  color: AppColors.accentText,
                ),
              ),
            ),
            const Spacer(),
            if (enrollment.progressPercent > 0)
              Text('${enrollment.progressPercent}% done',
                  style: AppTextStyles.caption(context)),
          ]),
          const SizedBox(height: AppSpacing.sm),
          Text(course.title, style: AppTextStyles.bodyStrong(context)),
          const SizedBox(height: AppSpacing.md),
          if (others.isEmpty)
            Text(
              'No alternatives available in this group.',
              style: AppTextStyles.caption(context, color: AppColors.textMuted),
            )
          else
            Wrap(
              spacing: AppSpacing.sm,
              children: [
                for (final alt in others)
                  TextButton.icon(
                    onPressed: () => _tryChange(context, alt),
                    icon: const Icon(Icons.swap_horiz_rounded, size: 18),
                    label: Text('Switch to ${alt.title}'),
                  ),
              ],
            ),
        ]),
      ),
    );
  }

  Future<void> _tryChange(BuildContext context, Course to) async {
    final hasProgress = enrollment.progressPercent > 0;
    final ok = await showDialog<bool>(
      context: context,
      builder: (d) => AlertDialog(
        title: Text('Switch elective to ${to.title}?'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
            'This will drop ${enrollment.course!.title}.',
            style: AppTextStyles.body(d),
          ),
          if (hasProgress) ...[
            const SizedBox(height: AppSpacing.md),
            // Phase 26 · T8 — canonical WarningTile so the switch
            // dialog reads the same as every other warn strip.
            WarningTile(
              title: 'Progress will be locked away',
              message:
                  'Student has ${enrollment.progressPercent}% progress in ${enrollment.course!.title}. '
                  'Progress is preserved on record but access to that course is lost.',
            ),
          ],
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () => Navigator.pop(d, true),
            style: hasProgress
                ? ElevatedButton.styleFrom(backgroundColor: AppColors.danger)
                : null,
            child: Text('Switch to ${to.title}'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.instance.setElective(studentId, enrollment.course!.electiveGroup!, to.id);
      onDone();
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}
