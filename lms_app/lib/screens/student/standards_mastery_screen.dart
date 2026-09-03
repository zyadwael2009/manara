import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/standard.dart';
import '../../providers/auth_provider.dart';
import '../../services/api_service.dart';

/// Phase 32 · T3 — per-standard mastery view.
///
/// Groups the standards by subject, colors each row by its mastery
/// band, and shows the sample size so the student knows how many
/// tagged quizzes/assignments back the number.
class StandardsMasteryScreen extends ConsumerStatefulWidget {
  final String? studentId;
  const StandardsMasteryScreen({super.key, this.studentId});
  @override
  ConsumerState<StandardsMasteryScreen> createState() =>
      _StandardsMasteryScreenState();
}

class _StandardsMasteryScreenState
    extends ConsumerState<StandardsMasteryScreen> {
  Future<List<StandardMastery>>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<StandardMastery>> _load() async {
    final sid = widget.studentId ?? ref.read(authProvider).user?.id ?? '';
    if (sid.isEmpty) return const [];
    return ApiService.instance.studentStandardsMastery(sid);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Standards mastery', style: AppTextStyles.h3(context)),
      ),
      body: FutureBuilder<List<StandardMastery>>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text(friendlyError(snap.error!)));
          }
          final rows = snap.data ?? const <StandardMastery>[];
          if (rows.isEmpty) {
            return const EmptyState(
              icon: Icons.rule_outlined,
              title: 'No standards yet',
              message: 'When your school defines curriculum standards '
                  'and tags them onto lessons or quizzes, your mastery '
                  'per standard will show here.',
            );
          }
          // Group by subject for a scannable layout.
          final bySubject = <String, List<StandardMastery>>{};
          for (final r in rows) {
            bySubject.putIfAbsent(r.subject ?? 'general', () => []).add(r);
          }
          return ListView(
            padding: const EdgeInsets.all(AppSpacing.md),
            children: [
              for (final subj in bySubject.keys)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.xl),
                  child: Card(
                    child: Padding(
                      padding: const EdgeInsets.all(AppSpacing.md),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(subj.toUpperCase(),
                              style: AppTextStyles.micro(context,
                                      color: AppColors.textMuted)
                                  .copyWith(
                                      letterSpacing: 1.2,
                                      fontWeight: FontWeight.w800)),
                          const SizedBox(height: AppSpacing.sm),
                          for (final r in bySubject[subj]!) _MasteryRow(row: r),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _MasteryRow extends StatelessWidget {
  final StandardMastery row;
  const _MasteryRow({required this.row});

  static const _bandColors = {
    'mastered': AppColors.success,
    'meeting': AppColors.primary,
    'progressing': AppColors.warning,
    'beginning': AppColors.danger,
    'not-assessed': AppColors.textMuted,
  };

  @override
  Widget build(BuildContext context) {
    final color = _bandColors[row.band] ?? AppColors.textMuted;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(children: [
        Container(
          width: 4, height: 42,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(2),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(row.code,
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
              Text(row.name,
                  style: AppTextStyles.body(context)
                      .copyWith(fontWeight: FontWeight.w600)),
            ],
          ),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              row.masteryPercent == null
                  ? '—'
                  : '${row.masteryPercent!.toStringAsFixed(0)}%',
              style: AppTextStyles.bodyStrong(context, color: color),
            ),
            Text(
              '${row.band.replaceAll('-', ' ')} · n=${row.sampleSize}',
              style: AppTextStyles.micro(context,
                  color: AppColors.textMuted),
            ),
          ],
        ),
      ]),
    );
  }
}
