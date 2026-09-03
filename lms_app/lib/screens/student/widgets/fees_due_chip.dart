import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/utils/transitions.dart';
import '../../../services/api_service.dart';
import '../../shared/student_fees_screen.dart';

/// Phase 30 · T2 — small "$X due" chip. Silent when there's no
/// outstanding balance. Turns amber for outstanding, red when any of
/// those fees are overdue past their due-date.
///
/// Phase 31 · T2 — now accepts an optional [studentId]. When null, hits
/// `/fees/summary` for the caller (student home). When non-null, hits
/// `/students/<id>/fees/summary` and taps navigate into the shared
/// `StudentFeesScreen` scoped to that child (parent portal).
class FeesDueChip extends ConsumerStatefulWidget {
  final String? studentId;
  final String? studentName;
  const FeesDueChip({super.key, this.studentId, this.studentName});
  @override
  ConsumerState<FeesDueChip> createState() => _FeesDueChipState();
}

class _FeesDueChipState extends ConsumerState<FeesDueChip> {
  Future<({double outstanding, int overdueCount, String currency})>? _future;

  @override
  void initState() {
    super.initState();
    final sid = widget.studentId;
    _future = (sid == null || sid.isEmpty)
        ? ApiService.instance.getMyFeeSummary()
        : ApiService.instance.getStudentFeeSummary(sid);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: _future,
      builder: (context, snap) {
        if (!snap.hasData) return const SizedBox.shrink();
        final s = snap.data!;
        if (s.outstanding <= 0.001) return const SizedBox.shrink();
        final overdue = s.overdueCount > 0;
        final bg = overdue ? AppColors.dangerSoft : AppColors.accentSoft;
        final fg = overdue ? AppColors.danger : AppColors.accentText;
        return Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.md),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              onTap: () {
                Navigator.of(context).push(
                  fadeThroughRoute(StudentFeesScreen(
                    studentId: widget.studentId,
                    studentName: widget.studentName,
                  )),
                );
              },
              child: Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                decoration: BoxDecoration(
                  color: bg,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                  border:
                      Border.all(color: fg.withValues(alpha: 0.35)),
                ),
                child: Row(children: [
                  Icon(
                      overdue
                          ? Icons.priority_high_rounded
                          : Icons.receipt_long_outlined,
                      color: fg, size: 18),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      overdue
                          ? '${s.currency} ${s.outstanding.toStringAsFixed(2)} due '
                              '(${s.overdueCount} overdue)'
                          : '${s.currency} ${s.outstanding.toStringAsFixed(2)} in fees due',
                      style: AppTextStyles.body(context, color: fg)
                          .copyWith(fontWeight: FontWeight.w700),
                    ),
                  ),
                  Icon(Icons.chevron_right_rounded, color: fg, size: 18),
                ]),
              ),
            ),
          ),
        );
      },
    );
  }
}
