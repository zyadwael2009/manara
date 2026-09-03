import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/fees.dart';
import '../../services/api_service.dart';

/// Phase 28 — read-only fee list for a student.
///
/// Same widget powers three surfaces:
///   * Student "My fees"        (studentId = null → uses /fees/mine)
///   * Parent's per-child view  (studentId = child.id, isParentView = true)
///   * Admin's student drilldown (see AdminStudentFeesScreen for the
///     write side)
///
/// Trust-core: this screen never writes fee state.
class StudentFeesScreen extends ConsumerStatefulWidget {
  final String? studentId;
  final String? studentName;
  const StudentFeesScreen({super.key, this.studentId, this.studentName});
  @override
  ConsumerState<StudentFeesScreen> createState() => _StudentFeesScreenState();
}

class _StudentFeesScreenState extends ConsumerState<StudentFeesScreen> {
  Future<FeeStatement>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<FeeStatement> _load() {
    final sid = widget.studentId;
    if (sid == null || sid.isEmpty) {
      return ApiService.instance.listMyFees();
    }
    return ApiService.instance.listStudentFees(sid);
  }

  void _reload() => setState(() => _future = _load());

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.studentName == null ? 'My fees' : 'Fees',
            style: AppTextStyles.h3(context)),
        actions: [
          if (widget.studentId != null)
            IconButton(
              tooltip: 'Statement PDF',
              icon: const Icon(Icons.picture_as_pdf_outlined),
              onPressed: () => launchUrl(
                Uri.parse(
                    ApiService.instance.feesPdfUrl(widget.studentId!)),
                mode: LaunchMode.platformDefault,
              ),
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => _reload(),
        child: FutureBuilder<FeeStatement>(
          future: _future,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return ListView(children: [
                const SizedBox(height: 80),
                Center(child: Text(friendlyError(snap.error!))),
              ]);
            }
            final s = snap.data!;
            if (s.items.isEmpty) {
              return ListView(children: const [
                EmptyState(
                  icon: Icons.receipt_long_outlined,
                  title: 'No fees on file',
                  message:
                      'When the school office adds a fee for you, it will '
                      'appear here with any payments already logged.',
                ),
              ]);
            }
            return ListView(
              padding: const EdgeInsets.all(AppSpacing.xl),
              children: [
                _TotalsCard(statement: s),
                const SizedBox(height: AppSpacing.md),
                for (final f in s.items) _FeeCard(fee: f),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _TotalsCard extends StatelessWidget {
  final FeeStatement statement;
  const _TotalsCard({required this.statement});
  @override
  Widget build(BuildContext context) {
    final owed = statement.totalBalance;
    final fmt = NumberFormat.currency(symbol: '', decimalDigits: 2);
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
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('OUTSTANDING BALANCE',
            style: TextStyle(
                color: Colors.white70,
                fontSize: 10,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.2)),
        const SizedBox(height: AppSpacing.sm),
        Text(fmt.format(owed),
            style: TextStyle(
                color: Colors.white,
                fontSize: 28,
                fontWeight: FontWeight.w800)),
        const SizedBox(height: AppSpacing.md),
        Row(children: [
          Expanded(
            child: _kv(context, 'Total billed', fmt.format(statement.totalAmount)),
          ),
          Expanded(
            child: _kv(context, 'Total paid', fmt.format(statement.totalPaid)),
          ),
        ]),
      ]),
    );
  }

  Widget _kv(BuildContext context, String label, String value) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(color: Colors.white70, fontSize: 10,
                  fontWeight: FontWeight.w700, letterSpacing: 0.8)),
          Text(value,
              style: const TextStyle(color: Colors.white,
                  fontSize: 14, fontWeight: FontWeight.w700)),
        ],
      );
}

class _FeeCard extends StatelessWidget {
  final FeeItem fee;
  const _FeeCard({required this.fee});
  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat.currency(symbol: '', decimalDigits: 2);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Expanded(
                child: Text(fee.label,
                    style: AppTextStyles.bodyStrong(context)),
              ),
              _StatusChip(fee: fee),
            ]),
            const SizedBox(height: 4),
            Row(children: [
              Text(fmt.format(fee.amount),
                  style: AppTextStyles.h3(context)
                      .copyWith(fontWeight: FontWeight.w700)),
              const SizedBox(width: AppSpacing.sm),
              if (fee.dueDate != null)
                Text('Due ${DateFormat.yMMMd().format(fee.dueDate!)}',
                    style: AppTextStyles.caption(context,
                        color: AppColors.textMuted)),
            ]),
            if ((fee.notes ?? '').isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(fee.notes!,
                  style: AppTextStyles.caption(context,
                      color: AppColors.textSecondary)),
            ],
            if (fee.payments.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.md),
              Text('PAYMENTS',
                  style: AppTextStyles.micro(context,
                      color: AppColors.textSecondary)),
              const SizedBox(height: 4),
              for (final p in fee.payments)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(children: [
                    const Icon(Icons.check_circle_outline,
                        size: 14, color: AppColors.success),
                    const SizedBox(width: AppSpacing.snug),
                    Expanded(
                      child: Text(
                        p.paidAt == null
                            ? 'Payment'
                            : DateFormat.yMMMd().format(p.paidAt!),
                        style: AppTextStyles.caption(context,
                            color: AppColors.textSecondary),
                      ),
                    ),
                    if (p.method != null)
                      Padding(
                        padding: const EdgeInsetsDirectional.only(
                            end: AppSpacing.sm),
                        child: Text(p.method!,
                            style: AppTextStyles.caption(context,
                                color: AppColors.textMuted)),
                      ),
                    Text(fmt.format(p.amount),
                        style: AppTextStyles.caption(context)),
                  ]),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final FeeItem fee;
  const _StatusChip({required this.fee});
  @override
  Widget build(BuildContext context) {
    final (label, bg, fg) = fee.isFullyPaid
        ? ('PAID', AppColors.successSoft, AppColors.success)
        : (fee.paidAmount > 0
            ? ('PARTIAL', AppColors.accentSoft, AppColors.accentText)
            : ('OWED', AppColors.dangerSoft, AppColors.danger));
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(label,
          style: TextStyle(
              color: fg,
              fontSize: 10,
              fontWeight: FontWeight.w800,
              letterSpacing: 0.6)),
    );
  }
}
