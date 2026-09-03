import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/utils/transitions.dart';
import '../../models/dashboard.dart';
import '../../providers/dashboard_provider.dart';
import '../../services/api_service.dart';
import 'attendance_patterns_screen.dart';
import 'cohort_comparison_screen.dart';
import '../../core/widgets/trailing_chevron.dart';

/// Admin dashboard — the "how healthy is the platform?" view.
///
/// Four top-line KPI tiles, two leaderboards, two line trends, one donut.
class AdminDashboardScreen extends ConsumerWidget {
  const AdminDashboardScreen({super.key});

  Future<void> _sendOverdueReminders(
      BuildContext context, WidgetRef ref) async {
    // Phase 31 · T1 — one-tap overdue-fee reminder sweep. Idempotent
    // by the day server-side, so repeat presses are safe.
    try {
      final count =
          await ApiService.instance.sendOverdueFeeReminders();
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(
                'Sent $count overdue fee reminder${count == 1 ? "" : "s"}.')),
      );
      ref.invalidate(adminDashboardProvider);
    } on ApiException catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(friendlyError(e))));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(adminDashboardProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text('Dashboard', style: AppTextStyles.h3(context)),
        actions: [
          IconButton(
            tooltip: 'Send overdue fee reminders',
            icon: const Icon(Icons.notifications_active_outlined),
            onPressed: () => _sendOverdueReminders(context, ref),
          ),
        ],
      ),
      body: RefreshIndicator(
        // Phase 10 audit fix M6.
        onRefresh: () async {
          ref.invalidate(adminDashboardProvider);
          await ref.read(adminDashboardProvider.future);
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
              _KpiGrid(t: d.topline),
              const SizedBox(height: AppSpacing.xl),
              _RoleBreakdown(t: d.topline),
              const SizedBox(height: AppSpacing.xl),
              // Phase 22 — link into the attendance-patterns view.
              Card(
                elevation: 0,
                color: AppColors.primary,
                child: InkWell(
                  borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                  onTap: () {
                    Navigator.of(context).push(fadeThroughRoute(
                      const AttendancePatternsScreen(),
                    ));
                  },
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: Row(children: [
                      const Icon(Icons.insights_rounded,
                          color: Colors.white, size: 24),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Attendance patterns',
                                style: AppTextStyles.h3(context,
                                    color: Colors.white)),
                            const SizedBox(height: 2),
                            Text(
                                'Chronic absentees, tardy trends, class rankings',
                                style: TextStyle(
                                    color: Colors.white.withValues(alpha: 0.85),
                                    fontSize: 12)),
                          ],
                        ),
                      ),
                      const TrailingChevron(color: Colors.white),
                    ]),
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              // Phase 28 — link into the cohort / semester comparison view.
              Card(
                elevation: 0,
                color: AppColors.accent,
                child: InkWell(
                  borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                  onTap: () {
                    Navigator.of(context).push(fadeThroughRoute(
                      const CohortComparisonScreen(),
                    ));
                  },
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.lg),
                    child: Row(children: [
                      const Icon(Icons.compare_arrows_rounded,
                          color: Colors.white, size: 24),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Cohort comparison',
                                style: AppTextStyles.h3(context,
                                    color: Colors.white)),
                            const SizedBox(height: 2),
                            Text(
                                'Side-by-side term metrics: attendance, %s, pass rate, certs',
                                style: TextStyle(
                                    color: Colors.white.withValues(alpha: 0.85),
                                    fontSize: 12)),
                          ],
                        ),
                      ),
                      const TrailingChevron(color: Colors.white),
                    ]),
                  ),
                ),
              ),
              const SizedBox(height: AppSpacing.xl),
              _SectionCard(
                title: 'Most popular courses',
                child: d.mostPopular.isEmpty
                    ? _EmptyLine(text: 'No enrollments yet.')
                    : _CourseLeaderboard(
                        rows: [
                          for (final r in d.mostPopular)
                            _LeaderRow(
                                title: r.title,
                                value: '${r.enrollmentCount}',
                                pct: _fracOfMax(
                                    r.enrollmentCount.toDouble(),
                                    d.mostPopular
                                        .map((x) => x.enrollmentCount.toDouble())
                                        .fold<double>(
                                            0, (a, b) => a > b ? a : b))),
                        ],
                        color: AppColors.primary,
                      ),
              ),
              const SizedBox(height: AppSpacing.xl),
              _SectionCard(
                title: 'Highest completion rate',
                subtitle: 'Courses with 5+ enrollments',
                child: d.highestCompletion.isEmpty
                    ? _EmptyLine(text: 'No qualifying courses yet.')
                    : _CourseLeaderboard(
                        rows: [
                          for (final r in d.highestCompletion)
                            _LeaderRow(
                                title: r.title,
                                value: '${r.avgCompletion.toStringAsFixed(0)}%',
                                pct: r.avgCompletion / 100.0),
                        ],
                        color: AppColors.accent,
                      ),
              ),
              const SizedBox(height: AppSpacing.xl),
              _SectionCard(
                title: 'Certificates issued · last 6 months',
                child: _MonthLine(
                    series: d.certsPerMonth, color: AppColors.success),
              ),
              const SizedBox(height: AppSpacing.xl),
              _SectionCard(
                title: 'New users · last 6 months',
                child: _MonthLine(
                    series: d.usersPerMonth, color: AppColors.primary),
              ),
              const SizedBox(height: AppSpacing.xl),
              _SectionCard(
                title: 'Grade band distribution',
                child: _GradeBandDonut(bands: d.gradeBands),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

double _fracOfMax(double v, double max) => max <= 0 ? 0.0 : v / max;

// ============================================================================
// KPI tiles
// ============================================================================
/// Phase 30 · T2 — abbreviate 4-digit-plus money to keep the KPI tile
/// legible: 12,345 → "12.3k"; 1,234,567 → "1.23M".
String _fmtMoney(double v) {
  if (v.abs() >= 1_000_000) return '${(v / 1_000_000).toStringAsFixed(2)}M';
  if (v.abs() >= 1_000) return '${(v / 1_000).toStringAsFixed(1)}k';
  return v.toStringAsFixed(0);
}

class _KpiGrid extends StatelessWidget {
  final AdminTopline t;
  const _KpiGrid({required this.t});
  @override
  Widget build(BuildContext context) {
    final tiles = <_Kpi>[
      _Kpi('Total users', '${t.totalUsers}', Icons.people_alt_rounded,
          AppColors.primary),
      _Kpi('Active enrollments', '${t.activeEnrollments}',
          Icons.school_rounded, AppColors.accent),
      _Kpi('Platform completion',
          '${(t.platformCompletionRate * 100).toStringAsFixed(0)}%',
          Icons.check_circle_rounded, AppColors.success),
      _Kpi('Certs · 30 days', '${t.certsIssuedLast30d}',
          Icons.workspace_premium_rounded, AppColors.primaryDark),
      // Phase 30 · T2 — fee KPIs. Outstanding total is the sum of
      // (billed - paid) across every fee item; overdue count is the
      // number of DISTINCT students who have at least one past-due
      // fee with a positive balance.
      _Kpi(
        'Fees outstanding',
        '\$${_fmtMoney(t.feeOutstandingTotal)}',
        Icons.request_quote_outlined,
        t.feeOutstandingTotal > 0 ? AppColors.warning : AppColors.textMuted,
      ),
      _Kpi(
        'Overdue students',
        '${t.studentsWithOverdueFees}',
        Icons.pending_actions_outlined,
        t.studentsWithOverdueFees > 0 ? AppColors.danger : AppColors.textMuted,
      ),
    ];
    return LayoutBuilder(builder: (context, cx) {
      final cols = cx.maxWidth > 720 ? 4 : 2;
      return GridView.count(
        crossAxisCount: cols,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: AppSpacing.md,
        crossAxisSpacing: AppSpacing.md,
        childAspectRatio: 2.0,
        children: [for (final k in tiles) _KpiTile(kpi: k)],
      );
    });
  }
}

class _Kpi {
  final String label;
  final String value;
  final IconData icon;
  final Color color;
  _Kpi(this.label, this.value, this.icon, this.color);
}

class _KpiTile extends StatelessWidget {
  final _Kpi kpi;
  const _KpiTile({required this.kpi});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          border: Border.all(color: AppColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Icon(kpi.icon, size: 18, color: kpi.color),
              const SizedBox(width: 6),
              Expanded(
                child: Text(kpi.label,
                    style: AppTextStyles.micro(context,
                        color: AppColors.textSecondary)),
              ),
            ]),
            const Spacer(),
            Text(
              kpi.value,
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.w800,
                color: AppColors.textPrimary,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ],
        ),
      );
}

// ============================================================================
// Role breakdown chip row
// ============================================================================
class _RoleBreakdown extends StatelessWidget {
  final AdminTopline t;
  const _RoleBreakdown({required this.t});
  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        _RoleChip(label: 'Admins', count: t.usersByRole['admin'] ?? 0),
        _RoleChip(label: 'Instructors', count: t.usersByRole['instructor'] ?? 0),
        _RoleChip(label: 'Students', count: t.usersByRole['student'] ?? 0),
        _RoleChip(label: 'Parents', count: t.usersByRole['parent'] ?? 0),
        _RoleChip(
            label: 'Published courses', count: t.publishedCourses),
        _RoleChip(label: 'Draft courses', count: t.draftCourses),
      ],
    );
  }
}

class _RoleChip extends StatelessWidget {
  final String label;
  final int count;
  const _RoleChip({required this.label, required this.count});
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: AppColors.primarySoft,
          borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
        ),
        child: Text('$label · $count',
            style: AppTextStyles.caption(context, color: AppColors.primaryDark)),
      );
}

// ============================================================================
// Section wrapper
// ============================================================================
class _SectionCard extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Widget child;
  const _SectionCard({required this.title, this.subtitle, required this.child});
  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title.toUpperCase(),
              style:
                  AppTextStyles.micro(context, color: AppColors.textSecondary)),
          if (subtitle != null)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(subtitle!,
                  style:
                      AppTextStyles.micro(context, color: AppColors.textMuted)),
            ),
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

/// Phase 20 — the dashboard has many small "no data yet" gaps (donut,
/// leaderboards, sparklines). Give them a consistent muted-line look
/// with a small icon so they scan as empty-by-design, not as errors.
class _EmptyLine extends StatelessWidget {
  final String text;
  const _EmptyLine({required this.text});
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
        child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          const Icon(Icons.insights_outlined,
              size: 14, color: AppColors.textMuted),
          const SizedBox(width: AppSpacing.sm),
          Flexible(
            child: Text(text,
                style: AppTextStyles.caption(context,
                    color: AppColors.textMuted)),
          ),
        ]),
      );
}

// ============================================================================
// Course leaderboard (bar list)
// ============================================================================
class _LeaderRow {
  final String title;
  final String value;
  final double pct; // 0..1
  _LeaderRow({required this.title, required this.value, required this.pct});
}

class _CourseLeaderboard extends StatelessWidget {
  final List<_LeaderRow> rows;
  final Color color;
  const _CourseLeaderboard({required this.rows, required this.color});
  @override
  Widget build(BuildContext context) => Column(
        children: [
          for (final r in rows)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Expanded(
                      child: Text(r.title,
                          style: AppTextStyles.body(context,
                              color: AppColors.textPrimary)),
                    ),
                    Text(r.value, style: AppTextStyles.bodyStrong(context)),
                  ]),
                  const SizedBox(height: 4),
                  Stack(children: [
                    Container(
                      height: 6,
                      decoration: BoxDecoration(
                        color: AppColors.surfaceMuted,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                    FractionallySizedBox(
                      widthFactor: r.pct.clamp(0.0, 1.0),
                      child: Container(
                        height: 6,
                        decoration: BoxDecoration(
                          color: color,
                          borderRadius: BorderRadius.circular(3),
                        ),
                      ),
                    ),
                  ]),
                ],
              ),
            ),
        ],
      );
}

// ============================================================================
// Line chart for 6-month trends
// ============================================================================
class _MonthLine extends StatelessWidget {
  final List<MonthBucket> series;
  final Color color;
  const _MonthLine({required this.series, required this.color});

  @override
  Widget build(BuildContext context) {
    if (series.isEmpty) return _EmptyLine(text: 'No data.');
    final maxY = series
        .map((b) => b.count.toDouble())
        .fold<double>(0, (a, b) => a > b ? a : b);
    final yMax = maxY < 1 ? 1.0 : maxY.ceilToDouble();
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: SizedBox(
        width: series.length * 70.0 < 320 ? 320 : series.length * 70.0,
        height: 180,
        child: LineChart(
          LineChartData(
            minY: 0,
            maxY: yMax,
            gridData: FlGridData(
              show: true,
              drawVerticalLine: false,
              getDrawingHorizontalLine: (_) =>
                  FlLine(color: AppColors.border, strokeWidth: 0.5),
            ),
            borderData: FlBorderData(show: false),
            titlesData: FlTitlesData(
              topTitles:
                  const AxisTitles(sideTitles: SideTitles(showTitles: false)),
              rightTitles:
                  const AxisTitles(sideTitles: SideTitles(showTitles: false)),
              leftTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 28,
                  interval: (yMax / 4).ceilToDouble().clamp(1.0, double.infinity),
                  getTitlesWidget: (v, _) => Text(
                    v.toInt().toString(),
                    style: AppTextStyles.micro(context,
                        color: AppColors.textMuted),
                  ),
                ),
              ),
              bottomTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 24,
                  getTitlesWidget: (v, _) {
                    final idx = v.toInt();
                    if (idx < 0 || idx >= series.length) {
                      return const SizedBox.shrink();
                    }
                    return Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(_shortMonth(series[idx].month),
                          style: AppTextStyles.micro(context,
                              color: AppColors.textMuted)),
                    );
                  },
                ),
              ),
            ),
            lineBarsData: [
              LineChartBarData(
                spots: [
                  for (int i = 0; i < series.length; i++)
                    FlSpot(i.toDouble(), series[i].count.toDouble()),
                ],
                color: color,
                barWidth: 3,
                isCurved: true,
                curveSmoothness: 0.28,
                dotData: FlDotData(
                  show: true,
                  getDotPainter: (spot, xPct, bar, index) => FlDotCirclePainter(
                    radius: 3.5,
                    color: color,
                    strokeWidth: 0,
                  ),
                ),
                belowBarData: BarAreaData(
                  show: true,
                  color: color.withValues(alpha: 0.10),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _shortMonth(String yyyyMm) {
    // 'YYYY-MM' → 'Mon' short label.
    const names = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    final parts = yyyyMm.split('-');
    if (parts.length != 2) return yyyyMm;
    final m = int.tryParse(parts[1]);
    if (m == null || m < 1 || m > 12) return yyyyMm;
    return names[m - 1];
  }
}

// ============================================================================
// Grade band donut
// ============================================================================
class _GradeBandDonut extends StatelessWidget {
  final Map<String, int> bands;
  const _GradeBandDonut({required this.bands});

  @override
  Widget build(BuildContext context) {
    final entries = ['A', 'B', 'C', 'D', 'F']
        .map((k) => MapEntry(k, bands[k] ?? 0))
        .toList();
    final total = entries.fold<int>(0, (a, b) => a + b.value);
    if (total == 0) {
      return _EmptyLine(text: 'No graded enrollments yet.');
    }

    final palette = <String, Color>{
      'A': AppColors.success,
      'B': AppColors.primary,
      'C': AppColors.accent,
      'D': AppColors.warning,
      'F': AppColors.danger,
    };

    return Row(children: [
      SizedBox(
        width: 160,
        height: 160,
        child: PieChart(
          PieChartData(
            sectionsSpace: 2,
            centerSpaceRadius: 44,
            sections: [
              for (final e in entries)
                if (e.value > 0)
                  PieChartSectionData(
                    value: e.value.toDouble(),
                    color: palette[e.key],
                    title: '',
                    radius: 30,
                  ),
            ],
          ),
        ),
      ),
      const SizedBox(width: AppSpacing.lg),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final e in entries)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(children: [
                  Container(
                    width: 10, height: 10,
                    decoration: BoxDecoration(
                      color: palette[e.key],
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(e.key,
                      style: AppTextStyles.bodyStrong(context)),
                  const Spacer(),
                  Text(
                    '${e.value} · ${(100 * e.value / total).toStringAsFixed(0)}%',
                    style: AppTextStyles.caption(context,
                        color: AppColors.textSecondary),
                  ),
                ]),
              ),
          ],
        ),
      ),
    ]);
  }
}
