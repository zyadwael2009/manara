import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/utils/transitions.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/quiz.dart';
import '../../providers/quiz_providers.dart';
import 'quiz_history_screen.dart';

/// Phase 16 — the student "Quizzes" hub. Every published quiz across
/// every course the student is enrolled in, with best/last/attempt count
/// and the full attempt timeline for each quiz.
///
/// Reachable from the "My classes" AppBar via the quiz icon.
class MyQuizzesScreen extends ConsumerWidget {
  const MyQuizzesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(myQuizzesAllProvider);
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: Text('Quizzes', style: AppTextStyles.h2(context))),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(myQuizzesAllProvider);
          await ref.read(myQuizzesAllProvider.future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(friendlyError(e))),
          ]),
          data: (rows) {
            if (rows.isEmpty) {
              return ListView(children: const [
                SizedBox(height: 80),
                EmptyState(
                  icon: Icons.quiz_outlined,
                  title: 'No quizzes yet',
                  message:
                      "Your courses haven't opened any quizzes yet. When a teacher publishes one it will show up here.",
                ),
              ]);
            }
            return _QuizzesBody(rows: rows);
          },
        ),
      ),
    );
  }
}

/// Phase 18 filter buckets. Applied client-side over the flat list —
/// the summary card at the top always reflects the pre-filter totals.
enum _QuizFilter { all, untaken, attemptsLeft, passed, failed }

extension _QuizFilterLabel on _QuizFilter {
  String get label => switch (this) {
        _QuizFilter.all => 'All',
        _QuizFilter.untaken => 'Untaken',
        _QuizFilter.attemptsLeft => 'Attempts left',
        _QuizFilter.passed => 'Passed',
        _QuizFilter.failed => 'Failed',
      };

  bool matches(MyQuizRow r) => switch (this) {
        _QuizFilter.all => true,
        _QuizFilter.untaken => r.attemptsCount == 0,
        _QuizFilter.attemptsLeft =>
          r.canRetake && (r.quiz.maxAttempts == null || r.attemptsCount < r.quiz.maxAttempts!),
        _QuizFilter.passed => r.passed,
        _QuizFilter.failed => r.hasHistory && !r.passed,
      };
}

/// Groups the flat list by course, then renders each group as a header +
/// a card per quiz. The backend already sorts by course → module → quiz.
class _QuizzesBody extends StatefulWidget {
  final List<MyQuizRow> rows;
  const _QuizzesBody({required this.rows});

  @override
  State<_QuizzesBody> createState() => _QuizzesBodyState();
}

class _QuizzesBodyState extends State<_QuizzesBody> {
  _QuizFilter _filter = _QuizFilter.all;

  @override
  Widget build(BuildContext context) {
    final filtered = widget.rows.where(_filter.matches).toList();
    final groups = <String, List<MyQuizRow>>{};
    for (final r in filtered) {
      groups.putIfAbsent(r.course.id, () => []).add(r);
    }

    // Roll-up bar reflects the full list, not the filter — that's the
    // "how am I doing overall" number.
    final taken = widget.rows.where((r) => r.hasHistory).length;
    final bestSamples = widget.rows
        .where((r) => r.bestPercent != null)
        .map((r) => r.bestPercent!)
        .toList();
    final avgBest = bestSamples.isEmpty
        ? null
        : bestSamples.reduce((a, b) => a + b) / bestSamples.length;

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      children: [
        _SummaryCard(total: widget.rows.length, taken: taken, avgBest: avgBest),
        const SizedBox(height: AppSpacing.md),
        _FilterChips(
          selected: _filter,
          onChanged: (f) => setState(() => _filter = f),
          countFor: (f) => widget.rows.where(f.matches).length,
        ),
        const SizedBox(height: AppSpacing.md),
        if (filtered.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: AppSpacing.xxl),
            child: Center(
              child: Text(
                _filter == _QuizFilter.all
                    ? 'No quizzes to show.'
                    : 'Nothing matches the "${_filter.label}" filter.',
                style: AppTextStyles.body(context, color: AppColors.textMuted),
              ),
            ),
          )
        else
          for (final entry in groups.entries) ...[
            _CourseHeader(course: entry.value.first.course),
            const SizedBox(height: AppSpacing.sm),
            for (final row in entry.value) ...[
              _QuizCard(row: row),
              const SizedBox(height: AppSpacing.md),
            ],
            const SizedBox(height: AppSpacing.lg),
          ],
      ],
    );
  }
}

class _FilterChips extends StatelessWidget {
  final _QuizFilter selected;
  final ValueChanged<_QuizFilter> onChanged;
  final int Function(_QuizFilter) countFor;
  const _FilterChips({
    required this.selected,
    required this.onChanged,
    required this.countFor,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(children: [
        for (final f in _QuizFilter.values) ...[
          _Chip(
            label: f.label,
            count: countFor(f),
            active: f == selected,
            onTap: () => onChanged(f),
          ),
          const SizedBox(width: AppSpacing.sm),
        ],
      ]),
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final int count;
  final bool active;
  final VoidCallback onTap;
  const _Chip({
    required this.label,
    required this.count,
    required this.active,
    required this.onTap,
  });
  @override
  Widget build(BuildContext context) {
    final bg = active ? AppColors.primary : AppColors.surface;
    final fg = active ? Colors.white : AppColors.textSecondary;
    final border = active ? AppColors.primary : AppColors.border;
    return InkWell(
      borderRadius: BorderRadius.circular(999),
      onTap: onTap,
      child: Container(
        padding:
            const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: 6),
        decoration: BoxDecoration(
          color: bg,
          border: Border.all(color: border),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Text(label,
              style: TextStyle(
                  color: fg, fontWeight: FontWeight.w700, fontSize: 12)),
          const SizedBox(width: 6),
          Text('$count',
              style: TextStyle(
                  color: fg.withValues(alpha: active ? 0.85 : 0.65),
                  fontWeight: FontWeight.w600,
                  fontSize: 11)),
        ]),
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final int total;
  final int taken;
  final double? avgBest;
  const _SummaryCard({required this.total, required this.taken, this.avgBest});

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: AppColors.primarySoft,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg, vertical: AppSpacing.md),
        child: Row(children: [
          Expanded(
            child: _Stat(label: 'Quizzes', value: '$total'),
          ),
          Container(
              width: 1, height: 32, color: AppColors.border),
          Expanded(
            child: _Stat(label: 'Taken', value: '$taken'),
          ),
          Container(
              width: 1, height: 32, color: AppColors.border),
          Expanded(
            child: _Stat(
              label: 'Avg best',
              value: avgBest == null ? '—' : '${avgBest!.round()}%',
            ),
          ),
        ]),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  final String label;
  final String value;
  const _Stat({required this.label, required this.value});
  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Text(value,
          style: AppTextStyles.h3(context)
              .copyWith(color: AppColors.primaryDark, fontWeight: FontWeight.w700)),
      const SizedBox(height: 2),
      Text(label.toUpperCase(),
          style: AppTextStyles.caption(context, color: AppColors.textMuted)
              .copyWith(letterSpacing: 0.8)),
    ]);
  }
}

class _CourseHeader extends StatelessWidget {
  final MyQuizCourse course;
  const _CourseHeader({required this.course});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.only(start: 4, bottom: 2),
      child: Row(children: [
        Container(
          width: 6, height: 6,
          decoration: const BoxDecoration(
              shape: BoxShape.circle, color: AppColors.accent),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(course.title,
              style: AppTextStyles.h3(context)
                  .copyWith(fontWeight: FontWeight.w700)),
        ),
        if (course.gradeName != null)
          Text(course.gradeName!,
              style: AppTextStyles.caption(context, color: AppColors.textMuted)),
      ]),
    );
  }
}

class _QuizCard extends ConsumerWidget {
  final MyQuizRow row;
  const _QuizCard({required this.row});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Phase 29 · T2 — one semantic node instead of enumerating title +
    // module + best-badge + meta-chips.
    final srLabel = [
      'Quiz ${row.quiz.title}',
      'module ${row.quiz.moduleTitle}',
      if (row.lastPercent != null)
        'last score ${row.lastPercent!.round()}%',
      'double-tap to open',
    ].join(', ');
    return Semantics(
      button: true,
      container: true,
      label: srLabel,
      excludeSemantics: true,
      child: Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        side: const BorderSide(color: AppColors.border),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        onTap: () async {
          // Phase 17 — the hub no longer opens the take flow directly.
          // History screen shows prior attempts + guarded Retry. On return,
          // refresh so any new attempt shows up on the hub card too.
          await Navigator.of(context).push(fadeThroughRoute(
            QuizHistoryScreen(initialRow: row),
          ));
          ref.invalidate(myQuizzesAllProvider);
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
                      Text(row.quiz.title,
                          style: AppTextStyles.body(context)
                              .copyWith(fontWeight: FontWeight.w600)),
                      const SizedBox(height: 2),
                      Text(row.quiz.moduleTitle,
                          style: AppTextStyles.caption(context,
                              color: AppColors.textMuted)),
                    ],
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                _BestBadge(row: row),
              ]),
              const SizedBox(height: AppSpacing.md),
              Row(children: [
                _MetaChip(
                  icon: Icons.emoji_events_outlined,
                  label: row.lastPercent == null
                      ? 'Not attempted'
                      : 'Last ${row.lastPercent!.round()}%',
                  color: _colorForPercent(row.lastPercent, row.quiz.passingScore),
                ),
                const SizedBox(width: AppSpacing.sm),
                _MetaChip(
                  icon: Icons.replay_rounded,
                  label: _attemptsLabel(row),
                  color: AppColors.textMuted,
                ),
                const Spacer(),
                Text('${row.quiz.totalPoints} pts',
                    style: AppTextStyles.caption(context,
                        color: AppColors.textMuted)),
              ]),
              if (row.attempts.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.md),
                const Divider(height: 1, color: AppColors.divider),
                const SizedBox(height: AppSpacing.sm),
                _AttemptsTimeline(row: row),
              ],
            ],
          ),
        ),
      ),
      ),
    );
  }

  static Color _colorForPercent(double? pct, int passing) {
    if (pct == null) return AppColors.textMuted;
    return pct >= passing ? AppColors.success : AppColors.danger;
  }

  static String _attemptsLabel(MyQuizRow row) {
    if (row.attemptsCount == 0) {
      return row.quiz.maxAttempts == null
          ? 'Unlimited attempts'
          : '${row.quiz.maxAttempts} attempts allowed';
    }
    if (row.quiz.maxAttempts == null) {
      return '${row.attemptsCount} attempt${row.attemptsCount == 1 ? "" : "s"}';
    }
    return '${row.attemptsCount} / ${row.quiz.maxAttempts} attempts';
  }
}

class _BestBadge extends StatelessWidget {
  final MyQuizRow row;
  const _BestBadge({required this.row});
  @override
  Widget build(BuildContext context) {
    if (row.bestPercent == null) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: AppColors.surfaceMuted,
          borderRadius: BorderRadius.circular(999),
        ),
        child: Text('New',
            style: AppTextStyles.caption(context, color: AppColors.textSecondary)
                .copyWith(fontWeight: FontWeight.w600, letterSpacing: 0.4)),
      );
    }
    final passed = row.bestPercent! >= row.quiz.passingScore;
    final bg = passed ? AppColors.successSoft : AppColors.dangerSoft;
    final fg = passed ? AppColors.success : AppColors.danger;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(
          passed ? Icons.check_circle_rounded : Icons.error_outline_rounded,
          size: 14, color: fg,
        ),
        const SizedBox(width: 6),
        Text('Best ${row.bestPercent!.round()}%',
            style: AppTextStyles.caption(context, color: fg)
                .copyWith(fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

class _MetaChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  const _MetaChip({required this.icon, required this.label, required this.color});
  @override
  Widget build(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(icon, size: 14, color: color),
      const SizedBox(width: 4),
      Text(label,
          style: AppTextStyles.caption(context, color: color)
              .copyWith(fontWeight: FontWeight.w600)),
    ]);
  }
}

/// One line per prior attempt: "#3 · 12 Aug · 85%".
class _AttemptsTimeline extends StatelessWidget {
  final MyQuizRow row;
  const _AttemptsTimeline({required this.row});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('ATTEMPTS',
            style: AppTextStyles.caption(context, color: AppColors.textMuted)
                .copyWith(letterSpacing: 0.8, fontWeight: FontWeight.w700)),
        const SizedBox(height: AppSpacing.xs),
        for (final a in row.attempts) _AttemptLine(attempt: a, passing: row.quiz.passingScore),
      ],
    );
  }
}

class _AttemptLine extends StatelessWidget {
  final MyQuizAttemptStub attempt;
  final int passing;
  const _AttemptLine({required this.attempt, required this.passing});

  @override
  Widget build(BuildContext context) {
    final passed = attempt.percent != null && attempt.percent! >= passing;
    final pctColor = attempt.percent == null
        ? AppColors.textMuted
        : (passed ? AppColors.success : AppColors.danger);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        SizedBox(
          width: 32,
          child: Text('#${attempt.attemptNumber}',
              style: AppTextStyles.caption(context, color: AppColors.textMuted)
                  .copyWith(fontWeight: FontWeight.w600)),
        ),
        Expanded(
          child: Text(
            _dateLabel(attempt.submittedAt),
            style:
                AppTextStyles.caption(context, color: AppColors.textSecondary),
          ),
        ),
        if (attempt.needsManualReview)
          Padding(
            padding: const EdgeInsetsDirectional.only(end: AppSpacing.sm),
            child: Text('review pending',
                style: AppTextStyles.caption(context, color: AppColors.warning)
                    .copyWith(fontStyle: FontStyle.italic)),
          ),
        Text(
          attempt.percent == null ? '—' : '${attempt.percent!.round()}%',
          style: AppTextStyles.caption(context, color: pctColor)
              .copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(width: AppSpacing.sm),
        Text(
          attempt.finalScore == null || attempt.maxScore == null
              ? ''
              : '${_trim(attempt.finalScore!)}/${_trim(attempt.maxScore!)}',
          style:
              AppTextStyles.caption(context, color: AppColors.textMuted),
        ),
      ]),
    );
  }

  static String _dateLabel(String? iso) {
    if (iso == null) return 'In progress';
    final t = DateTime.tryParse(iso);
    if (t == null) return '';
    const months = [
      'Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'
    ];
    return '${t.day} ${months[t.month - 1]} ${t.year}';
  }

  static String _trim(double d) {
    if (d == d.roundToDouble()) return d.toInt().toString();
    return d.toStringAsFixed(1);
  }
}
