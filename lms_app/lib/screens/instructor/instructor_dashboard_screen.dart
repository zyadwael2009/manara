import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/dashboard.dart';
import '../../providers/dashboard_provider.dart';
import 'course_drilldown_screen.dart';
import '../../core/utils/friendly_error.dart';

/// Instructor dashboard — landing view.
///
/// One row per course the signed-in user teaches (via ClassCourseTeacher),
/// with the three headline KPIs: enrollment count, average completion,
/// quiz pass rate. Tap a row for the drill-down.
class InstructorDashboardScreen extends ConsumerWidget {
  const InstructorDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(instructorDashboardProvider);
    return Scaffold(
      appBar: AppBar(title: Text('Dashboard', style: AppTextStyles.h3(context))),
      body: RefreshIndicator(
        // Phase 10 audit fix M6.
        onRefresh: () async {
          ref.invalidate(instructorDashboardProvider);
          await ref.read(instructorDashboardProvider.future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(friendlyError(e), style: AppTextStyles.body(context))),
          ]),
          data: (d) => d.courses.isEmpty
              ? ListView(children: const [
                  SizedBox(height: 80),
                  EmptyState(
                    icon: Icons.insights_rounded,
                    title: 'No courses to report on',
                    message:
                        'You are not assigned as a course teacher on any class yet. Ask your school office to add you.',
                  ),
                ])
              : ListView(
                  padding: const EdgeInsets.all(AppSpacing.xl),
                  children: [
                    _SummaryStrip(summary: d.summary),
                    const SizedBox(height: AppSpacing.xl),
                    Text('MY COURSES',
                        style: AppTextStyles.micro(context,
                            color: AppColors.textSecondary)),
                    const SizedBox(height: AppSpacing.sm),
                    for (final row in d.courses)
                      _CourseCard(row: row),
                  ],
                ),
        ),
      ),
    );
  }
}

class _SummaryStrip extends StatelessWidget {
  final InstructorDashboardSummary summary;
  const _SummaryStrip({required this.summary});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.primary, AppColors.primaryDark],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
        boxShadow: const [
          BoxShadow(color: Color(0x33000000), blurRadius: 20, offset: Offset(0, 8)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('AT A GLANCE',
              style: AppTextStyles.micro(context, color: Colors.white70)),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            _SummaryTile(
              label: 'Students',
              value: '${summary.totalStudents}',
            ),
            _SummaryTile(
              label: 'Courses',
              value: '${summary.courseCount}',
            ),
            _SummaryTile(
              label: 'Avg completion',
              value: '${summary.avgCompletion.toStringAsFixed(0)}%',
            ),
            _SummaryTile(
              label: 'Quiz pass',
              value: '${(summary.avgQuizPassRate * 100).toStringAsFixed(0)}%',
            ),
          ]),
        ],
      ),
    );
  }
}

class _SummaryTile extends StatelessWidget {
  final String label;
  final String value;
  const _SummaryTile({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value,
              style: TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.w800,
                fontFeatures: const [FontFeature.tabularFigures()],
              )),
          const SizedBox(height: 2),
          Text(label,
              style: TextStyle(color: Colors.white70, fontSize: 11)),
        ],
      ),
    );
  }
}

class _CourseCard extends StatelessWidget {
  final InstructorCourseRow row;
  const _CourseCard({required this.row});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        onTap: () {
          Navigator.of(context).push(fadeThroughRoute(
              CourseDrilldownScreen(courseId: row.id, courseTitle: row.title)));
        },
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(row.title, style: AppTextStyles.h3(context)),
                      const SizedBox(height: 2),
                      Text(
                        '${row.gradeName ?? "—"} · ${row.category}',
                        style: AppTextStyles.caption(context,
                            color: AppColors.textMuted),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.primarySoft,
                    borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                  ),
                  child: Text(
                    '${row.enrollmentCount} students',
                    style: AppTextStyles.caption(context,
                        color: AppColors.primaryDark),
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.md),
              _MetricBar(
                label: 'Avg completion',
                pct: row.avgCompletion / 100.0,
                display: '${row.avgCompletion.toStringAsFixed(0)}%',
                color: AppColors.primary,
              ),
              const SizedBox(height: AppSpacing.sm),
              _MetricBar(
                label: 'Quiz pass rate',
                pct: row.quizPassRate,
                display: '${(row.quizPassRate * 100).toStringAsFixed(0)}%',
                color: AppColors.accent,
                hint: row.quizCount == 0 ? 'no quizzes yet' : null,
              ),
              const SizedBox(height: AppSpacing.sm),
              _MetricBar(
                label: 'Certificates issued',
                pct: row.certRate,
                display: '${row.certCount} of ${row.enrollmentCount}',
                color: AppColors.success,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MetricBar extends StatelessWidget {
  final String label;
  final double pct; // 0..1
  final String display;
  final Color color;
  final String? hint;
  const _MetricBar({
    required this.label,
    required this.pct,
    required this.display,
    required this.color,
    this.hint,
  });

  @override
  Widget build(BuildContext context) {
    final p = pct.clamp(0.0, 1.0);
    return Row(children: [
      SizedBox(
        width: 140,
        child: Text(label,
            style: AppTextStyles.caption(context, color: AppColors.textSecondary)),
      ),
      Expanded(
        child: Stack(children: [
          Container(
            height: 8,
            decoration: BoxDecoration(
              color: AppColors.surfaceMuted,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          FractionallySizedBox(
            widthFactor: p,
            child: Container(
              height: 8,
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(4),
              ),
            ),
          ),
        ]),
      ),
      const SizedBox(width: AppSpacing.sm),
      SizedBox(
        width: 88,
        child: Text(
          hint ?? display,
          textAlign: TextAlign.right,
          style: AppTextStyles.caption(context,
              color: hint != null ? AppColors.textMuted : AppColors.textPrimary),
        ),
      ),
    ]);
  }
}
