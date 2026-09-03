import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/diploma.dart';
import '../../services/api_service.dart';

/// Phase 32 · T2 — hero card for a student's digital diploma.
///
/// Also usable in the parent / admin drilldown by passing a
/// non-null [studentId] (mirrors the FeesDueChip pattern).
class DiplomaScreen extends ConsumerStatefulWidget {
  final String? studentId;
  const DiplomaScreen({super.key, this.studentId});
  @override
  ConsumerState<DiplomaScreen> createState() => _DiplomaScreenState();
}

class _DiplomaScreenState extends ConsumerState<DiplomaScreen> {
  Future<Diploma?>? _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Diploma?> _load() {
    final sid = widget.studentId;
    return (sid == null || sid.isEmpty)
        ? ApiService.instance.myDiploma()
        : ApiService.instance.studentDiploma(sid);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Diploma', style: AppTextStyles.h3(context)),
      ),
      body: FutureBuilder<Diploma?>(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text(friendlyError(snap.error!)));
          }
          final dip = snap.data;
          if (dip == null) {
            return const EmptyState(
              icon: Icons.school_outlined,
              title: 'No diploma on file',
              message: 'Diplomas are issued when a student graduates '
                  'Grade 12. Once that lands, this page shows the '
                  'verified credential.',
            );
          }
          return ListView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            children: [_DiplomaHero(diploma: dip)],
          );
        },
      ),
    );
  }
}

class _DiplomaHero extends StatelessWidget {
  final Diploma diploma;
  const _DiplomaHero({required this.diploma});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.xl),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: diploma.revoked
              ? [AppColors.danger, AppColors.dangerSoft]
              : [AppColors.primary, AppColors.accent],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            diploma.revoked ? 'REVOKED DIPLOMA' : 'CLASS OF ${diploma.classOfYear}',
            style: TextStyle(
                color: Colors.white70,
                fontSize: 10,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.4),
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            diploma.studentName ?? '—',
            style: const TextStyle(
                color: Colors.white,
                fontSize: 26,
                fontWeight: FontWeight.w800),
          ),
          if (diploma.honors != null) ...[
            const SizedBox(height: 4),
            Text(
              diploma.honors!.replaceAll('_', ' ').toUpperCase(),
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontStyle: FontStyle.italic,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.8),
            ),
          ],
          const SizedBox(height: AppSpacing.lg),
          _kv(context, 'Diploma number', diploma.diplomaNumber),
          _kv(context, 'Issued',
              diploma.issuedAt == null
                  ? '—'
                  : DateFormat.yMMMMd().format(diploma.issuedAt!)),
          _kv(context, 'Course certificates',
              '${diploma.totalCertificates}'),
          if (diploma.averagePercent != null)
            _kv(context, 'Average grade',
                '${diploma.averagePercent!.toStringAsFixed(1)}%'),
          if (diploma.revoked && (diploma.revokedReason ?? '').isNotEmpty) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              'Reason: ${diploma.revokedReason}',
              style: const TextStyle(color: Colors.white, fontSize: 12),
            ),
          ],
          const SizedBox(height: AppSpacing.xl),
          Row(children: [
            OutlinedButton.icon(
              onPressed: () => launchUrl(
                Uri.parse(ApiService.instance
                    .studentDiplomaPdfUrl(diploma.studentId)),
                mode: LaunchMode.platformDefault,
              ),
              icon: const Icon(Icons.picture_as_pdf_outlined, size: 16),
              label: const Text('Download PDF'),
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.white,
                side: const BorderSide(color: Colors.white70),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            OutlinedButton.icon(
              onPressed: () => launchUrl(
                Uri.parse(ApiService.instance
                    .verifyDiplomaUrl(diploma.diplomaNumber)),
                mode: LaunchMode.platformDefault,
              ),
              icon: const Icon(Icons.verified_outlined, size: 16),
              label: const Text('Verify'),
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.white,
                side: const BorderSide(color: Colors.white70),
              ),
            ),
          ]),
        ],
      ),
    );
  }

  Widget _kv(BuildContext context, String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(children: [
          SizedBox(
            width: 130,
            child: Text(label,
                style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.85),
                    fontSize: 12)),
          ),
          Expanded(
            child: Text(value,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w600)),
          ),
        ]),
      );
}
