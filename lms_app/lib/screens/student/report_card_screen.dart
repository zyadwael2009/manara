import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/mini_sparkline.dart';
import '../../models/grading.dart';
import '../../models/insight.dart';
import '../../providers/auth_provider.dart';
import '../../providers/grading_providers.dart';
import '../../providers/insight_providers.dart';
import '../../services/api_service.dart';

/// Student's own report card. Layout mirrors the Cognia-style reference:
/// per-subject row shows categories → percentage → letter → GPA, with a
/// cumulative row at the bottom.
class ReportCardScreen extends ConsumerWidget {
  const ReportCardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(myReportCardProvider);
    final me = ref.watch(authProvider).user;
    return Scaffold(
      appBar: AppBar(
        title: Text('Report card', style: AppTextStyles.h2(context)),
        actions: [
          if (me != null && me.role == 'student') ...[
            IconButton(
              tooltip: 'Download report card PDF',
              icon: const Icon(Icons.picture_as_pdf_outlined),
              onPressed: () => launchUrl(
                Uri.parse(ApiService.instance.reportCardPdfUrl(me.id)),
                mode: LaunchMode.platformDefault,
              ),
            ),
            IconButton(
              tooltip: 'Download transcript PDF',
              icon: const Icon(Icons.description_outlined),
              onPressed: () => launchUrl(
                Uri.parse(ApiService.instance.transcriptPdfUrl(me.id)),
                mode: LaunchMode.platformDefault,
              ),
            ),
          ],
        ],
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (rc) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(myReportCardProvider),
          child: _Body(rc: rc),
        ),
      ),
    );
  }
}

class _Body extends StatelessWidget {
  final ReportCard rc;
  const _Body({required this.rc});

  @override
  Widget build(BuildContext context) {
    if (rc.subjects.isEmpty) {
      return ListView(children: const [
        SizedBox(height: 80),
        EmptyState(
          icon: Icons.assessment_outlined,
          title: 'No report card yet',
          message:
              "You haven't been enrolled in any courses yet — once you are, "
              "your grades and cumulative report will land here.",
        ),
      ]);
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (rc.cumulative != null) _CumulativeHeader(cumulative: rc.cumulative!),
          const SizedBox(height: AppSpacing.lg),
          for (final s in rc.subjects) _SubjectCard(subject: s),
        ],
      ),
    );
  }
}

class _CumulativeHeader extends StatelessWidget {
  final ReportCardCumulative cumulative;
  const _CumulativeHeader({required this.cumulative});

  @override
  Widget build(BuildContext context) {
    final pct = cumulative.percent;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppColors.primary, AppColors.primaryDark],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('CUMULATIVE',
              style: AppTextStyles.micro(context, color: Colors.white.withValues(alpha: 0.85))),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            Expanded(child: _stat('Percentage',
                pct != null ? '${pct.toStringAsFixed(2)}%' : '—')),
            Expanded(child: _stat('Grade', cumulative.letter ?? '—')),
            Expanded(child: _stat('GPA',
                cumulative.gpaValue != null ? cumulative.gpaValue!.toStringAsFixed(2) : '—')),
          ]),
        ],
      ),
    );
  }

  Widget _stat(String label, String value) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label.toUpperCase(),
          style: const TextStyle(
            color: Colors.white70, fontSize: 10, letterSpacing: 0.6,
            fontWeight: FontWeight.w700,
          )),
      const SizedBox(height: 2),
      Text(value,
          style: const TextStyle(
            color: Colors.white, fontSize: 22, fontWeight: FontWeight.w800,
          )),
    ]);
  }
}

class _SubjectCard extends StatelessWidget {
  final ReportCardSubject subject;
  const _SubjectCard({required this.subject});

  @override
  Widget build(BuildContext context) {
    final ungradedCount = subject.rubric.where((r) => !subject.entries.containsKey(r.gradeCategoryId)).length;
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(subject.courseTitle, style: AppTextStyles.h3(context))),
            if (subject.letter != null)
              _LetterBadge(letter: subject.letter!, gpa: subject.gpaValue),
          ]),
          const SizedBox(height: AppSpacing.sm),
          Row(children: [
            _kv('Percentage',
                subject.percent != null ? '${subject.percent!.toStringAsFixed(2)}%' : '—'),
            const SizedBox(width: AppSpacing.lg),
            _kv('GPA', subject.gpaValue != null ? subject.gpaValue!.toStringAsFixed(2) : '—'),
            const Spacer(),
            // Phase 18 — per-category earned-fraction sparkline. Reveals
            // where the score is coming from (heavy on quizzes, light on
            // participation, etc.) at a glance.
            _CategorySparkline(subject: subject),
          ]),
          if (ungradedCount > 0) ...[
            const SizedBox(height: AppSpacing.xs),
            Text('$ungradedCount not graded yet',
                style: AppTextStyles.caption(context, color: AppColors.textMuted)),
          ],
          const Divider(height: 20),
          _RubricGrid(subject: subject),
        ]),
      ),
    );
  }

  Widget _kv(String k, String v) {
    return Builder(builder: (context) {
      return Row(children: [
        Text('$k: ', style: AppTextStyles.caption(context, color: AppColors.textMuted)),
        Text(v, style: AppTextStyles.bodyStrong(context)),
      ]);
    });
  }
}

/// Phase 22 — the sparkline now plots real cached-percent history from
/// `myGradeHistoryProvider`. Falls back to the Phase 18 per-category
/// snapshot while history is loading or when this course has <2 points.
class _CategorySparkline extends ConsumerWidget {
  final ReportCardSubject subject;
  const _CategorySparkline({required this.subject});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final histAsync = ref.watch(myGradeHistoryProvider);
    final history = histAsync.maybeWhen(
      data: (h) => h.series.firstWhere(
        (s) => s.courseId == subject.courseId,
        orElse: () =>
            const GradeHistoryCourse(courseId: '', courseTitle: '', points: []),
      ),
      orElse: () => null,
    );
    if (history != null && history.points.length >= 2) {
      final points = history.points
          .map((p) => (p.percent / 100.0).clamp(0.0, 1.0))
          .toList();
      final passing = (subject.percent ?? 0) >= 60;
      return Row(mainAxisSize: MainAxisSize.min, children: [
        MiniSparkline(
          values: points,
          color: passing ? AppColors.success : AppColors.warning,
          width: 88,
          height: 26,
        ),
        const SizedBox(width: AppSpacing.sm),
        _TrendArrow(direction: history.trendDirection),
      ]);
    }
    // Fallback: per-rubric-category shape while history has no series.
    final points = <double>[];
    for (final item in subject.rubric) {
      final earned = subject.entries[item.gradeCategoryId];
      if (item.maxScore > 0 && earned != null) {
        points.add((earned / item.maxScore).clamp(0.0, 1.0));
      }
    }
    if (points.length < 2) return const SizedBox.shrink();
    final passing = (subject.percent ?? 0) >= 60;
    return MiniSparkline(
      values: points,
      color: passing ? AppColors.success : AppColors.warning,
      width: 88,
      height: 26,
    );
  }
}

class _TrendArrow extends StatelessWidget {
  final int direction; // +1, 0, -1
  const _TrendArrow({required this.direction});
  @override
  Widget build(BuildContext context) {
    late IconData icon;
    late Color color;
    switch (direction) {
      case 1:
        icon = Icons.trending_up_rounded;
        color = AppColors.success;
        break;
      case -1:
        icon = Icons.trending_down_rounded;
        color = AppColors.danger;
        break;
      default:
        icon = Icons.trending_flat_rounded;
        color = AppColors.textMuted;
    }
    return Icon(icon, size: 16, color: color);
  }
}

class _RubricGrid extends StatelessWidget {
  final ReportCardSubject subject;
  const _RubricGrid({required this.subject});

  @override
  Widget build(BuildContext context) {
    // Small table: category name / earned / max
    return Column(
      children: [
        for (final item in subject.rubric)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(children: [
              Expanded(
                child: Text(
                  item.gradeCategoryName ?? item.gradeCategorySlug ?? '—',
                  style: AppTextStyles.body(context),
                ),
              ),
              _scoreText(context, subject.entries[item.gradeCategoryId], item.maxScore),
            ]),
          ),
      ],
    );
  }

  Widget _scoreText(BuildContext context, double? earned, int maxScore) {
    if (earned == null) {
      return Text('— / $maxScore',
          style: AppTextStyles.caption(context, color: AppColors.textMuted));
    }
    return Text(
      '${earned.toStringAsFixed(earned == earned.roundToDouble() ? 0 : 1)} / $maxScore',
      style: AppTextStyles.bodyStrong(context),
    );
  }
}

class _LetterBadge extends StatelessWidget {
  final String letter;
  final double? gpa;
  const _LetterBadge({required this.letter, this.gpa});

  Color _colorFor(String l) {
    if (l.startsWith('A')) return AppColors.success;
    if (l.startsWith('B')) return AppColors.info;
    if (l.startsWith('C')) return AppColors.accent;
    if (l.startsWith('D')) return AppColors.warning;
    return AppColors.danger;
  }

  @override
  Widget build(BuildContext context) {
    final color = _colorFor(letter);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Text(letter, style: TextStyle(fontWeight: FontWeight.w800, color: color)),
        if (gpa != null) ...[
          const SizedBox(width: 6),
          Text('· ${gpa!.toStringAsFixed(2)}',
              style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 12)),
        ],
      ]),
    );
  }
}
