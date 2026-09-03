import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/failed_load.dart';
import '../../models/insight.dart';
import '../../providers/insight_providers.dart';

/// Phase 22 — admin-only attendance patterns block. Three ranked lists:
///   * Chronic absentees (< 80% present).
///   * Tardy leaders (most late marks).
///   * Class averages (best-to-worst).
class AttendancePatternsScreen extends ConsumerWidget {
  const AttendancePatternsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(attendancePatternsProvider);
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title:
            Text('Attendance patterns', style: AppTextStyles.h2(context)),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(attendancePatternsProvider);
          await ref.read(attendancePatternsProvider.future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          // Phase 29 · T1 — required-data view. If the patterns fetch
          // fails, an admin needs to know AND retry, not just see a
          // muted centered string.
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
              child: FailedLoad(
                label: "Couldn't load attendance patterns",
                detail: friendlyError(e),
                onRetry: () => ref.invalidate(attendancePatternsProvider),
              ),
            ),
          ]),
          data: (p) {
            final anyData = p.chronicAbsentees.isNotEmpty ||
                p.tardyLeaders.isNotEmpty ||
                p.classes.isNotEmpty;
            if (!anyData) {
              return ListView(children: const [
                SizedBox(height: 80),
                EmptyState(
                  icon: Icons.insights_outlined,
                  title: 'No attendance data yet',
                  message:
                      'Once homeroom teachers mark attendance, patterns will surface here.',
                ),
              ]);
            }
            return ListView(
              padding: const EdgeInsets.all(AppSpacing.lg),
              children: [
                _ClassesBlock(rows: p.classes),
                const SizedBox(height: AppSpacing.xl),
                _ChronicBlock(rows: p.chronicAbsentees),
                const SizedBox(height: AppSpacing.xl),
                _TardyBlock(rows: p.tardyLeaders),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _ClassesBlock extends StatelessWidget {
  final List<ClassAttendanceRank> rows;
  const _ClassesBlock({required this.rows});
  @override
  Widget build(BuildContext context) {
    return _Block(
      title: 'CLASSES · ATTENDANCE RATE',
      empty: 'No class-level attendance yet.',
      rows: rows.isEmpty ? const [] : rows.map((r) => _RankedRow(
        leadingLabel: r.name,
        rightMetric: '${r.pctPresent.toStringAsFixed(1)}%',
        subtitle: '${r.marksCount} marks',
        color: _paletteFor(r.pctPresent),
      )).toList(),
    );
  }

  static Color _paletteFor(double pct) {
    if (pct >= 95) return AppColors.success;
    if (pct >= 85) return AppColors.primary;
    if (pct >= 70) return AppColors.warning;
    return AppColors.danger;
  }
}

class _ChronicBlock extends StatelessWidget {
  final List<ChronicAbsentee> rows;
  const _ChronicBlock({required this.rows});
  @override
  Widget build(BuildContext context) {
    return _Block(
      title: 'CHRONIC ABSENTEES',
      empty: 'No students below the 80% threshold.',
      rows: rows.isEmpty
          ? const []
          : rows.map((r) => _RankedRow(
                leadingLabel: r.name,
                rightMetric: r.pctPresent == null
                    ? '—'
                    : '${r.pctPresent!.toStringAsFixed(1)}%',
                subtitle: '${r.absentCount} absent',
                color: AppColors.danger,
              )).toList(),
    );
  }
}

class _TardyBlock extends StatelessWidget {
  final List<TardyLeader> rows;
  const _TardyBlock({required this.rows});
  @override
  Widget build(BuildContext context) {
    return _Block(
      title: 'MOST TARDIES',
      empty: 'No tardy marks logged.',
      rows: rows.isEmpty
          ? const []
          : rows.map((r) => _RankedRow(
                leadingLabel: r.name,
                rightMetric: '${r.lateCount}',
                subtitle: 'late arrivals',
                color: AppColors.warning,
              )).toList(),
    );
  }
}

class _RankedRow {
  final String leadingLabel;
  final String rightMetric;
  final String subtitle;
  final Color color;
  const _RankedRow({
    required this.leadingLabel,
    required this.rightMetric,
    required this.subtitle,
    required this.color,
  });
}

class _Block extends StatelessWidget {
  final String title;
  final String empty;
  final List<_RankedRow> rows;
  const _Block({required this.title, required this.empty, required this.rows});
  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.lg, vertical: AppSpacing.md),
            child: Text(title,
                style: AppTextStyles.micro(context, color: AppColors.textMuted)
                    .copyWith(fontWeight: FontWeight.w800, letterSpacing: 0.8)),
          ),
          const Divider(height: 1, color: AppColors.divider),
          if (rows.isEmpty)
            Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Text(empty,
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
            )
          else
            for (int i = 0; i < rows.length; i++) ...[
              _RowTile(rank: i + 1, row: rows[i]),
              if (i < rows.length - 1)
                const Divider(height: 1, color: AppColors.divider),
            ],
        ],
      ),
    );
  }
}

class _RowTile extends StatelessWidget {
  final int rank;
  final _RankedRow row;
  const _RowTile({required this.rank, required this.row});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
      child: Row(children: [
        SizedBox(
          width: 24,
          child: Text('$rank.',
              style: AppTextStyles.caption(context, color: AppColors.textMuted)
                  .copyWith(fontWeight: FontWeight.w800)),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(row.leadingLabel,
                  style: AppTextStyles.body(context)
                      .copyWith(fontWeight: FontWeight.w600)),
              Text(row.subtitle,
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
            ],
          ),
        ),
        Text(row.rightMetric,
            style: TextStyle(
                color: row.color,
                fontWeight: FontWeight.w800,
                fontSize: 16)),
      ]),
    );
  }
}
