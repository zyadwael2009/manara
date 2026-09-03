import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../models/certificate.dart';
import '../../models/enrollment.dart';
import '../../models/parent_link.dart';
import '../../services/api_service.dart';
import '../../models/quiz.dart';
import '../../providers/parent_provider.dart';
import '../../providers/attendance_provider.dart';
import '../../providers/timetable_provider.dart';
import '../catalog/course_detail_screen.dart';
import '../shared/attendance_calendar.dart';
import '../shared/student_fees_screen.dart';
import '../shared/weekly_timetable_grid.dart';
import '../student/widgets/fees_due_chip.dart';
import '../student/certificate_screen.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/trailing_chevron.dart';

/// One child's dashboard, from a parent's read-only session.
///
/// Three stacked sections — Courses, Certificates, Quiz results — plus a
/// header pill with class/grade.
class ChildDashboardScreen extends ConsumerWidget {
  final String childId;
  final String childName;

  const ChildDashboardScreen({
    super.key,
    required this.childId,
    required this.childName,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(childSummaryProvider(childId));
    return Scaffold(
      appBar: AppBar(
        title: Text(childName, style: AppTextStyles.h3(context)),
        actions: [
          // Phase 23 — parent can download the child's PDF report card + transcript.
          IconButton(
            tooltip: 'Report card PDF',
            icon: const Icon(Icons.picture_as_pdf_outlined),
            onPressed: () => launchUrl(
              Uri.parse(ApiService.instance.reportCardPdfUrl(childId)),
              mode: LaunchMode.platformDefault,
            ),
          ),
          IconButton(
            tooltip: 'Transcript PDF',
            icon: const Icon(Icons.description_outlined),
            onPressed: () => launchUrl(
              Uri.parse(ApiService.instance.transcriptPdfUrl(childId)),
              mode: LaunchMode.platformDefault,
            ),
          ),
          // Phase 28 — parent can see (read-only) the child's fees.
          IconButton(
            tooltip: 'Fees',
            icon: const Icon(Icons.receipt_long_outlined),
            onPressed: () {
              Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => StudentFeesScreen(
                  studentId: childId,
                  studentName: childName,
                ),
              ));
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        // Phase 10 audit fix M6: await the primary refetch so the pull-to-
        // refresh spinner doesn't disappear before the new data lands.
        onRefresh: () async {
          ref.invalidate(childSummaryProvider(childId));
          ref.invalidate(childCertificatesProvider(childId));
          ref.invalidate(childQuizAttemptsProvider(childId));
          await ref.read(childSummaryProvider(childId).future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(friendlyError(e), style: AppTextStyles.body(context))),
          ]),
          data: (s) => ListView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            children: [
              _StudentHeader(student: s.student, certCount: s.activeCertificateCount),
              const SizedBox(height: AppSpacing.md),
              // Phase 31 · T2 — parent-portal fee chip. Same widget as
              // the student home; silent when the child owes nothing.
              FeesDueChip(studentId: childId, studentName: childName),
              const SizedBox(height: AppSpacing.md),
              _SectionTitle('Courses'),
              const SizedBox(height: AppSpacing.sm),
              if (s.enrollments.isEmpty)
                _EmptyPanel('No active courses yet.')
              else
                for (final e in s.enrollments)
                  _CourseTile(enrollment: e, childName: childName),
              const SizedBox(height: AppSpacing.xl),
              _SectionTitle('Certificates'),
              const SizedBox(height: AppSpacing.sm),
              _CertificatesSection(childId: childId),
              const SizedBox(height: AppSpacing.xl),
              _SectionTitle('Attendance'),
              const SizedBox(height: AppSpacing.sm),
              _AttendanceSection(childId: childId),
              const SizedBox(height: AppSpacing.xl),
              _SectionTitle('Quiz results'),
              const SizedBox(height: AppSpacing.sm),
              _QuizAttemptsSection(childId: childId),
            ],
          ),
        ),
      ),
    );
  }
}

// ============================================================================
// Header
// ============================================================================
class _StudentHeader extends StatelessWidget {
  final ChildStudentStub student;
  final int certCount;
  const _StudentHeader({required this.student, required this.certCount});

  @override
  Widget build(BuildContext context) {
    final classLine = [
      if (student.gradeName != null) student.gradeName!,
      if (student.className != null) student.className!,
    ].join(' · ');
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.primary, AppColors.primaryDark],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('VIEWING', style: AppTextStyles.micro(context, color: Colors.white70)),
          const SizedBox(height: 2),
          Text(student.name,
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.w800,
                color: Colors.white,
              )),
          if (classLine.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(classLine,
                  style: TextStyle(color: Colors.white70, fontSize: 12)),
            ),
          const SizedBox(height: AppSpacing.md),
          Row(children: [
            _Chip(icon: Icons.workspace_premium_rounded,
                  label: '$certCount certificate${certCount == 1 ? "" : "s"}'),
            if (student.classId != null) ...[
              const SizedBox(width: AppSpacing.sm),
              _TimetableChip(classId: student.classId!, className: student.className),
            ],
          ]),
        ],
      ),
    );
  }
}

class _TimetableChip extends ConsumerWidget {
  final String classId;
  final String? className;
  const _TimetableChip({required this.classId, required this.className});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return InkWell(
      onTap: () {
        Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => _ChildTimetableScreen(
            classId: classId, className: className ?? 'Timetable',
          ),
        ));
      },
      borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.16),
          borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: const [
          Icon(Icons.event_note_rounded, size: 14, color: Colors.white),
          SizedBox(width: 6),
          Text('Timetable',
              style: TextStyle(color: Colors.white, fontSize: 12)),
        ]),
      ),
    );
  }
}

class _ChildTimetableScreen extends ConsumerWidget {
  final String classId;
  final String className;
  const _ChildTimetableScreen({required this.classId, required this.className});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(classTimetableProvider(classId));
    return Scaffold(
      appBar: AppBar(title: Text('$className timetable',
          style: AppTextStyles.h3(context))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (week) => ListView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: WeeklyTimetableGrid(week: week),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final IconData icon;
  final String label;
  const _Chip({required this.icon, required this.label});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.16),
          borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: Colors.white),
            const SizedBox(width: 6),
            Text(label,
                style: const TextStyle(color: Colors.white, fontSize: 12)),
          ],
        ),
      );
}

// ============================================================================
// Small building blocks
// ============================================================================
class _SectionTitle extends StatelessWidget {
  final String label;
  const _SectionTitle(this.label);
  @override
  Widget build(BuildContext context) => Text(label.toUpperCase(),
      style: AppTextStyles.micro(context, color: AppColors.textSecondary));
}

/// Phase 20 — softer, more graphical empty panel used for the child
/// dashboard sections. Cardless so multiple sections stacked don't
/// double up the border.
class _EmptyPanel extends StatelessWidget {
  final String text;
  const _EmptyPanel(this.text);
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg, vertical: AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.surfaceMuted,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          border: Border.all(color: AppColors.border),
        ),
        child: Row(children: [
          const Icon(Icons.hourglass_empty_rounded,
              color: AppColors.textMuted, size: 18),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(text,
                style: AppTextStyles.caption(context,
                    color: AppColors.textMuted)),
          ),
        ]),
      );
}

// ============================================================================
// Course tile
// ============================================================================
class _CourseTile extends StatelessWidget {
  final Enrollment enrollment;
  final String childName;
  const _CourseTile({required this.enrollment, required this.childName});

  @override
  Widget build(BuildContext context) {
    final course = enrollment.course;
    final pct = (enrollment.progressPercent).clamp(0, 100);
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        onTap: course == null
            ? null
            : () {
                Navigator.of(context).push(fadeThroughRoute(
                  CourseDetailScreen(
                    courseId: course.id,
                    parentViewChildName: childName,
                  ),
                ));
              },
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(
                  child: Text(course?.title ?? 'Course',
                      style: AppTextStyles.bodyStrong(context)),
                ),
                if (enrollment.cachedLetter != null)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppColors.successSoft,
                      borderRadius:
                          BorderRadius.circular(AppSpacing.radiusPill),
                    ),
                    child: Text(
                      enrollment.cachedPercent == null
                          ? enrollment.cachedLetter!
                          : '${enrollment.cachedPercent!.toStringAsFixed(0)}% · ${enrollment.cachedLetter!}',
                      style: AppTextStyles.micro(context,
                          color: AppColors.success),
                    ),
                  ),
              ]),
              const SizedBox(height: 8),
              Stack(children: [
                Container(
                  height: 6,
                  decoration: BoxDecoration(
                    color: AppColors.surfaceMuted,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ),
                FractionallySizedBox(
                  widthFactor: pct / 100.0,
                  child: Container(
                    height: 6,
                    decoration: BoxDecoration(
                      color: pct >= 100 ? AppColors.success : AppColors.primary,
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ),
                ),
              ]),
              const SizedBox(height: 6),
              Text('$pct% complete',
                  style: AppTextStyles.micro(context, color: AppColors.textMuted)),
            ],
          ),
        ),
      ),
    );
  }
}

// ============================================================================
// Certificates section
// ============================================================================
class _CertificatesSection extends ConsumerWidget {
  final String childId;
  const _CertificatesSection({required this.childId});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(childCertificatesProvider(childId));
    return async.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: LinearProgressIndicator(minHeight: 2),
      ),
      error: (e, _) => _EmptyPanel(friendlyError(e)),
      data: (certs) => certs.isEmpty
          ? _EmptyPanel('No certificates yet.')
          : Column(children: [
              for (final c in certs) _CertificateTile(cert: c),
            ]),
    );
  }
}

class _CertificateTile extends StatelessWidget {
  final Certificate cert;
  const _CertificateTile({required this.cert});
  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        onTap: () {
          Navigator.of(context).push(fadeThroughRoute(
              CertificateScreen(certificateId: cert.id)));
        },
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(children: [
            Container(
              width: 40, height: 40,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: cert.revoked ? AppColors.dangerSoft : AppColors.accentSoft,
                shape: BoxShape.circle,
              ),
              child: Icon(
                cert.revoked
                    ? Icons.block_rounded
                    : Icons.workspace_premium_rounded,
                color: cert.revoked ? AppColors.danger : AppColors.accent,
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(cert.courseTitle ?? '—',
                      style: AppTextStyles.bodyStrong(context)),
                  Text(
                    cert.issuedAt == null
                        ? cert.certificateNumber
                        : '${DateFormat.yMMMd().format(cert.issuedAt!)} · ${cert.certificateNumber}',
                    style: AppTextStyles.micro(context, color: AppColors.textMuted),
                  ),
                ],
              ),
            ),
            const TrailingChevron(color: AppColors.textMuted),
          ]),
        ),
      ),
    );
  }
}

// ============================================================================
// Quiz results section
// ============================================================================
class _QuizAttemptsSection extends ConsumerWidget {
  final String childId;
  const _QuizAttemptsSection({required this.childId});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(childQuizAttemptsProvider(childId));
    return async.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: LinearProgressIndicator(minHeight: 2),
      ),
      error: (e, _) => _EmptyPanel(friendlyError(e)),
      data: (attempts) {
        final finalized = attempts.where((a) => a.submittedAt != null).toList();
        if (finalized.isEmpty) return _EmptyPanel('No quiz results yet.');
        return Card(
          child: Column(children: [
            for (int i = 0; i < finalized.length; i++) ...[
              _AttemptRow(attempt: finalized[i]),
              if (i != finalized.length - 1)
                const Divider(height: 1, color: AppColors.divider),
            ],
          ]),
        );
      },
    );
  }
}

class _AttemptRow extends StatelessWidget {
  final QuizAttempt attempt;
  const _AttemptRow({required this.attempt});
  @override
  Widget build(BuildContext context) {
    final pct = (attempt.finalScore == null || attempt.maxScore == 0)
        ? null
        : (attempt.finalScore! / attempt.maxScore * 100.0);
    final passed = attempt.passed;
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(children: [
        Icon(
          passed ? Icons.check_circle_rounded : Icons.cancel_rounded,
          color: passed ? AppColors.success : AppColors.danger,
          size: 18,
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Quiz attempt #${attempt.attemptNumber}',
                  style: AppTextStyles.bodyStrong(context)),
              if (attempt.submittedAt != null &&
                  DateTime.tryParse(attempt.submittedAt!) != null)
                Text(
                  DateFormat.yMMMd()
                      .add_jm()
                      .format(DateTime.parse(attempt.submittedAt!)),
                  style: AppTextStyles.micro(context, color: AppColors.textMuted),
                ),
            ],
          ),
        ),
        if (pct != null)
          Text('${pct.toStringAsFixed(0)}%',
              style: AppTextStyles.bodyStrong(context,
                  color: passed ? AppColors.success : AppColors.danger)),
      ]),
    );
  }
}

// ============================================================================
// Phase 12: Attendance section for the parent portal.
// ============================================================================
class _AttendanceSection extends ConsumerWidget {
  final String childId;
  const _AttendanceSection({required this.childId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(childAttendanceProvider(childId));
    return async.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: LinearProgressIndicator(minHeight: 2),
      ),
      error: (e, _) => _EmptyPanel(friendlyError(e)),
      data: (marks) => marks.isEmpty
          ? _EmptyPanel('No attendance records yet.')
          : Card(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.md),
                child: AttendanceCalendar(marks: marks),
              ),
            ),
    );
  }
}
