import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/dashboard.dart';
import '../../providers/dashboard_provider.dart';
import '../../core/utils/friendly_error.dart';

/// Per-course drill-down: completion histogram, per-module completion,
/// per-quiz pass rate, top 5, at-risk list.
class CourseDrilldownScreen extends ConsumerWidget {
  final String courseId;
  final String courseTitle;
  const CourseDrilldownScreen({
    super.key,
    required this.courseId,
    required this.courseTitle,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(instructorCourseDrilldownProvider(courseId));
    return Scaffold(
      appBar: AppBar(title: Text(courseTitle, style: AppTextStyles.h3(context))),
      body: RefreshIndicator(
        // Phase 10 audit fix M6.
        onRefresh: () async {
          ref.invalidate(instructorCourseDrilldownProvider(courseId));
          await ref.read(instructorCourseDrilldownProvider(courseId).future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(friendlyError(e), style: AppTextStyles.body(context))),
          ]),
          data: (d) => ListView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            children: [
              _StatChip(
                label: '${d.enrollmentCount} enrolled · '
                    'certificate threshold ${d.minCertificatePercent}%',
              ),
              const SizedBox(height: AppSpacing.xl),
              _Section(
                title: 'Completion distribution',
                child: _CompletionHistogram(bins: d.completionHistogram),
              ),
              const SizedBox(height: AppSpacing.xl),
              _Section(
                title: 'Per-module completion',
                child: d.moduleCompletion.isEmpty
                    ? _EmptyLine(text: 'This course has no modules yet.')
                    : _ModuleBars(rows: d.moduleCompletion),
              ),
              const SizedBox(height: AppSpacing.xl),
              _Section(
                title: 'Per-quiz pass rate',
                child: d.quizPassRates.isEmpty
                    ? _EmptyLine(text: 'No published quizzes yet.')
                    : _QuizBars(rows: d.quizPassRates),
              ),
              const SizedBox(height: AppSpacing.xl),
              _Section(
                title: 'Top students',
                child: d.topStudents.isEmpty
                    ? _EmptyLine(text: 'No grades entered yet.')
                    : _TopList(rows: d.topStudents),
              ),
              const SizedBox(height: AppSpacing.xl),
              _Section(
                title: 'At-risk students',
                child: d.atRisk.isEmpty
                    ? _EmptyLine(text: 'No students are currently at risk. 🎉')
                    : _AtRiskList(rows: d.atRisk),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ============================================================================
// Small building blocks
// ============================================================================
class _Section extends StatelessWidget {
  final String title;
  final Widget child;
  const _Section({required this.title, required this.child});
  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title.toUpperCase(),
              style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
          const SizedBox(height: AppSpacing.sm),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: child,
            ),
          ),
        ],
      );
}

class _StatChip extends StatelessWidget {
  final String label;
  const _StatChip({required this.label});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: 6),
        decoration: BoxDecoration(
          color: AppColors.primarySoft,
          borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
        ),
        child: Text(label,
            style: AppTextStyles.caption(context, color: AppColors.primaryDark)),
      );
}

class _EmptyLine extends StatelessWidget {
  final String text;
  const _EmptyLine({required this.text});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
        child: Text(text,
            style: AppTextStyles.caption(context, color: AppColors.textMuted)),
      );
}

// ============================================================================
// Histogram — 5 buckets
// ============================================================================
class _CompletionHistogram extends StatelessWidget {
  final List<HistogramBin> bins;
  const _CompletionHistogram({required this.bins});

  @override
  Widget build(BuildContext context) {
    final maxY = (bins.map((b) => b.count).fold<int>(0, (a, b) => a > b ? a : b))
        .toDouble();
    final yMax = maxY < 1 ? 1.0 : maxY.ceilToDouble();
    return SizedBox(
      height: 200,
      child: BarChart(
        BarChartData(
          alignment: BarChartAlignment.spaceAround,
          maxY: yMax,
          borderData: FlBorderData(show: false),
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            getDrawingHorizontalLine: (_) =>
                FlLine(color: AppColors.border, strokeWidth: 0.5),
          ),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 28,
                interval: (yMax / 4).ceilToDouble().clamp(1.0, double.infinity),
                getTitlesWidget: (v, _) => Text(
                  v.toInt().toString(),
                  style: AppTextStyles.micro(context, color: AppColors.textMuted),
                ),
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 24,
                getTitlesWidget: (v, _) {
                  final idx = v.toInt();
                  if (idx < 0 || idx >= bins.length) return const SizedBox.shrink();
                  return Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      bins[idx].label,
                      style: AppTextStyles.micro(context, color: AppColors.textMuted),
                    ),
                  );
                },
              ),
            ),
          ),
          barGroups: [
            for (int i = 0; i < bins.length; i++)
              BarChartGroupData(
                x: i,
                barRods: [
                  BarChartRodData(
                    toY: bins[i].count.toDouble(),
                    color: AppColors.primary,
                    width: 20,
                    borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(4)),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

// ============================================================================
// Per-module bar rows (horizontal-style: label + progress bar)
// ============================================================================
class _ModuleBars extends StatelessWidget {
  final List<ModuleCompletion> rows;
  const _ModuleBars({required this.rows});
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (final r in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: _HRow(
              label: r.title,
              pct: r.avgCompletion / 100.0,
              display: '${r.avgCompletion.toStringAsFixed(0)}%',
              color: AppColors.primary,
            ),
          ),
      ],
    );
  }
}

// ============================================================================
// Per-quiz rows
// ============================================================================
class _QuizBars extends StatelessWidget {
  final List<QuizPassRow> rows;
  const _QuizBars({required this.rows});
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (final r in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: _HRow(
              label: r.title,
              pct: r.passRate,
              display: '${(r.passRate * 100).toStringAsFixed(0)}%',
              color: AppColors.accent,
              hint: 'pass @ ${r.passingScore}% · '
                  '${(r.attemptedRate * 100).toStringAsFixed(0)}% attempted',
            ),
          ),
      ],
    );
  }
}

class _HRow extends StatelessWidget {
  final String label;
  final double pct;
  final String display;
  final Color color;
  final String? hint;
  const _HRow({
    required this.label,
    required this.pct,
    required this.display,
    required this.color,
    this.hint,
  });
  @override
  Widget build(BuildContext context) {
    final p = pct.clamp(0.0, 1.0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          Expanded(
            child: Text(label,
                style: AppTextStyles.body(context, color: AppColors.textPrimary)),
          ),
          Text(display, style: AppTextStyles.bodyStrong(context)),
        ]),
        if (hint != null)
          Padding(
            padding: const EdgeInsets.only(top: 2, bottom: 4),
            child: Text(hint!,
                style: AppTextStyles.micro(context, color: AppColors.textMuted)),
          ),
        const SizedBox(height: 4),
        Stack(children: [
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
      ],
    );
  }
}

// ============================================================================
// Top students / at-risk
// ============================================================================
class _TopList extends StatelessWidget {
  final List<TopStudent> rows;
  const _TopList({required this.rows});
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (int i = 0; i < rows.length; i++)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(children: [
              Container(
                width: 24,
                height: 24,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: i == 0 ? AppColors.accentSoft : AppColors.primarySoft,
                  shape: BoxShape.circle,
                ),
                child: Text('${i + 1}',
                    style: AppTextStyles.micro(context,
                        color:
                            i == 0 ? AppColors.accent : AppColors.primaryDark)),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(rows[i].studentName ?? '—',
                    style: AppTextStyles.bodyStrong(context)),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.successSoft,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                ),
                child: Text(
                  '${rows[i].percent.toStringAsFixed(0)}% · ${rows[i].letter ?? "—"}',
                  style: AppTextStyles.micro(context, color: AppColors.success),
                ),
              ),
            ]),
          ),
      ],
    );
  }
}

class _AtRiskList extends StatelessWidget {
  final List<AtRiskStudent> rows;
  const _AtRiskList({required this.rows});
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (final r in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const Icon(Icons.warning_amber_rounded,
                    color: AppColors.warning, size: 20),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(r.studentName ?? '—',
                          style: AppTextStyles.bodyStrong(context)),
                      Text(
                        _reasonsLine(r),
                        style: AppTextStyles.micro(context,
                            color: AppColors.textMuted),
                      ),
                    ],
                  ),
                ),
                Wrap(
                  spacing: 4,
                  children: [
                    for (final reason in r.reasons)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppColors.dangerSoft,
                          borderRadius:
                              BorderRadius.circular(AppSpacing.radiusPill),
                        ),
                        child: Text(_reasonChip(reason),
                            style: AppTextStyles.micro(context,
                                color: AppColors.danger)),
                      ),
                  ],
                ),
              ],
            ),
          ),
      ],
    );
  }

  static String _reasonChip(String r) => switch (r) {
        'low_progress' => 'behind',
        'below_grade_threshold' => 'low grade',
        _ => r,
      };

  static String _reasonsLine(AtRiskStudent r) {
    final parts = <String>[];
    parts.add('progress ${r.progressPercent}%');
    if (r.cachedPercent != null) {
      parts.add('grade ${r.cachedPercent!.toStringAsFixed(0)}%');
    }
    return parts.join(' · ');
  }
}
