import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/cohort.dart';
import '../../core/constants/app_constants.dart';
import '../../models/term.dart';
import '../../services/api_service.dart';
import 'package:url_launcher/url_launcher.dart';

/// Phase 28 — admin's side-by-side term comparison.
///
/// Two term pickers at the top; on both being set, calls
/// `/api/dashboards/cohort-comparison` and renders four metric bars
/// (attendance, avg %, pass rate, cert count) with an "overall" row
/// and a per-class breakdown below.
class CohortComparisonScreen extends ConsumerStatefulWidget {
  const CohortComparisonScreen({super.key});
  @override
  ConsumerState<CohortComparisonScreen> createState() =>
      _CohortComparisonScreenState();
}

class _CohortComparisonScreenState
    extends ConsumerState<CohortComparisonScreen> {
  String? _termAId;
  String? _termBId;
  Future<CohortComparison>? _future;
  Future<List<Term>>? _termsFuture;

  @override
  void initState() {
    super.initState();
    _termsFuture = _loadAllTerms();
  }

  /// Flatten every term across every school year — the endpoint takes
  /// two termIds and doesn't care about the year hierarchy, so the
  /// picker shows them all together with the year suffix for context.
  Future<List<Term>> _loadAllTerms() async {
    final years = await ApiService.instance.listSchoolYears();
    final all = <Term>[];
    for (final y in years) {
      try {
        final rows = await ApiService.instance.listTerms(y.id);
        all.addAll(rows);
      } catch (_) {}
    }
    return all;
  }

  void _run() {
    final a = _termAId, b = _termBId;
    if (a == null || b == null || a == b) {
      setState(() => _future = null);
      return;
    }
    setState(() {
      _future = ApiService.instance
          .getCohortComparison(termAId: a, termBId: b);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Cohort comparison', style: AppTextStyles.h3(context)),
        actions: [
          // Phase 30 · T3 — CSV export of the current side-by-side
          // snapshot. Silent no-op until both terms are picked (the
          // server would 400 without both ids anyway).
          IconButton(
            tooltip: 'Export CSV',
            icon: const Icon(Icons.file_download_outlined),
            onPressed: (_termAId != null && _termBId != null)
                ? () => launchUrl(
                      Uri.parse(
                        '${AppConstants.apiBaseUrl}'
                        '/dashboards/cohort-comparison.csv'
                        '?termAId=$_termAId&termBId=$_termBId',
                      ),
                      mode: LaunchMode.platformDefault,
                    )
                : null,
          ),
          // Phase 31 · T3 — PDF export (sibling of CSV).
          IconButton(
            tooltip: 'Export PDF',
            icon: const Icon(Icons.picture_as_pdf_outlined),
            onPressed: (_termAId != null && _termBId != null)
                ? () => launchUrl(
                      Uri.parse(
                        ApiService.instance.cohortComparisonPdfUrl(
                          termAId: _termAId!,
                          termBId: _termBId!,
                        ),
                      ),
                      mode: LaunchMode.platformDefault,
                    )
                : null,
          ),
        ],
      ),
      body: FutureBuilder<List<Term>>(
        future: _termsFuture,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text(friendlyError(snap.error!)));
          }
          final terms = snap.data ?? const <Term>[];
          return _body(context, terms);
        },
      ),
    );
  }

  Widget _body(BuildContext context, List<Term> terms) {
    return Builder(builder: (context) {
          if (terms.isEmpty) {
            return const EmptyState(
              icon: Icons.calendar_view_month_outlined,
              title: 'No terms defined',
              message: 'Create at least two terms in Grading admin '
                  'before you can compare cohorts.',
            );
          }
          return ListView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            children: [
              Row(children: [
                Expanded(
                  child: _TermPicker(
                    label: 'Term A',
                    terms: terms,
                    value: _termAId,
                    onChanged: (v) {
                      _termAId = v;
                      _run();
                    },
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: _TermPicker(
                    label: 'Term B',
                    terms: terms,
                    value: _termBId,
                    onChanged: (v) {
                      _termBId = v;
                      _run();
                    },
                  ),
                ),
              ]),
              const SizedBox(height: AppSpacing.xl),
              if (_future == null)
                const EmptyState(
                  icon: Icons.compare_arrows_rounded,
                  title: 'Pick two different terms',
                  message: 'Choose two distinct terms above to compare '
                      'attendance, grades, pass rate, and certificates.',
                )
              else
                FutureBuilder<CohortComparison>(
                  future: _future,
                  builder: (context, snap) {
                    if (snap.connectionState == ConnectionState.waiting) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    if (snap.hasError) {
                      return Center(child: Text(friendlyError(snap.error!)));
                    }
                    return _ComparisonBody(cmp: snap.data!);
                  },
                ),
            ],
          );
        });
  }
}

class _TermPicker extends StatelessWidget {
  final String label;
  final List<Term> terms;
  final String? value;
  final ValueChanged<String?> onChanged;
  const _TermPicker({
    required this.label,
    required this.terms,
    required this.value,
    required this.onChanged,
  });
  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<String>(
      initialValue: value,
      isExpanded: true,
      decoration: InputDecoration(labelText: label),
      items: [
        for (final t in terms)
          DropdownMenuItem(
              value: t.id, child: Text('${t.name} · ${t.schoolYearName ?? ""}')),
      ],
      onChanged: onChanged,
    );
  }
}

class _ComparisonBody extends StatelessWidget {
  final CohortComparison cmp;
  const _ComparisonBody({required this.cmp});
  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(children: [
            _headerRow(context, cmp.termA.termName, cmp.termB.termName),
            const Divider(),
            _metricRow(context, 'Attendance',
                cmp.termA.overall.attendanceRate * 100,
                cmp.termB.overall.attendanceRate * 100,
                suffix: '%'),
            _metricRow(context, 'Avg %',
                cmp.termA.overall.avgPercent,
                cmp.termB.overall.avgPercent,
                suffix: '%'),
            _metricRow(context, 'Pass rate',
                cmp.termA.overall.passRate * 100,
                cmp.termB.overall.passRate * 100,
                suffix: '%'),
            _metricRow(context, 'Certificates',
                cmp.termA.overall.certCount.toDouble(),
                cmp.termB.overall.certCount.toDouble()),
          ]),
        ),
      ),
      const SizedBox(height: AppSpacing.xl),
      Text('Per class', style: AppTextStyles.h3(context)),
      const SizedBox(height: AppSpacing.sm),
      _PerClassGrid(cmp: cmp),
    ]);
  }

  Widget _headerRow(BuildContext context, String a, String b) => Row(
        children: [
          const SizedBox(width: 100),
          Expanded(
              child: Text(a,
                  textAlign: TextAlign.center,
                  style: AppTextStyles.bodyStrong(context,
                      color: AppColors.primary))),
          Expanded(
              child: Text(b,
                  textAlign: TextAlign.center,
                  style: AppTextStyles.bodyStrong(context,
                      color: AppColors.accent))),
        ],
      );

  Widget _metricRow(BuildContext context, String label, double a, double b,
      {String suffix = ''}) {
    final delta = b - a;
    final deltaColor = delta.abs() < 0.05
        ? AppColors.textMuted
        : (delta > 0 ? AppColors.success : AppColors.danger);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(children: [
        SizedBox(width: 100, child: Text(label)),
        Expanded(
            child: Text(
                suffix.isEmpty
                    ? a.toStringAsFixed(0)
                    : '${a.toStringAsFixed(1)}$suffix',
                textAlign: TextAlign.center,
                style: AppTextStyles.bodyStrong(context))),
        Expanded(
            child: Text(
                suffix.isEmpty
                    ? b.toStringAsFixed(0)
                    : '${b.toStringAsFixed(1)}$suffix',
                textAlign: TextAlign.center,
                style: AppTextStyles.bodyStrong(context, color: deltaColor))),
      ]),
    );
  }
}

class _PerClassGrid extends StatelessWidget {
  final CohortComparison cmp;
  const _PerClassGrid({required this.cmp});
  @override
  Widget build(BuildContext context) {
    // Merge on classId — a class present in only one term still shows,
    // with the missing side blanked out.
    final byId = <String, ({CohortClassRow? a, CohortClassRow? b, String name})>{};
    for (final r in cmp.termA.perClass) {
      byId[r.classId] = (a: r, b: null, name: r.className);
    }
    for (final r in cmp.termB.perClass) {
      final prev = byId[r.classId];
      byId[r.classId] = (
        a: prev?.a,
        b: r,
        name: prev?.name ?? r.className,
      );
    }
    if (byId.isEmpty) {
      return const EmptyState(
        icon: Icons.groups_outlined,
        title: 'No active classes',
        message: 'Neither term has active classes with grade data.',
      );
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(children: [
          for (final entry in byId.entries) ...[
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(children: [
                SizedBox(
                    width: 100,
                    child: Text(entry.value.name,
                        style: AppTextStyles.bodyStrong(context))),
                Expanded(
                    child: Text(
                        entry.value.a == null
                            ? '—'
                            : '${entry.value.a!.avgPercent.toStringAsFixed(1)}%',
                        textAlign: TextAlign.center,
                        style: AppTextStyles.body(context,
                            color: AppColors.primary))),
                Expanded(
                    child: Text(
                        entry.value.b == null
                            ? '—'
                            : '${entry.value.b!.avgPercent.toStringAsFixed(1)}%',
                        textAlign: TextAlign.center,
                        style: AppTextStyles.body(context,
                            color: AppColors.accent))),
              ]),
            ),
            const Divider(height: 1),
          ],
        ]),
      ),
    );
  }
}
