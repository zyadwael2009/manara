import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/certificate.dart';
import '../../services/api_service.dart';

/// Public certificate verify page. No auth needed. Lets anyone with a
/// certificate number confirm whether it's real (and current).
class VerifyScreen extends StatefulWidget {
  const VerifyScreen({super.key});

  @override
  State<VerifyScreen> createState() => _VerifyScreenState();
}

class _VerifyScreenState extends State<VerifyScreen> {
  final _ctrl = TextEditingController();
  VerifyResult? _result;
  bool _notFound = false;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final v = _ctrl.text.trim();
    if (v.isEmpty) return;
    setState(() {
      _loading = true;
      _result = null;
      _notFound = false;
      _error = null;
    });
    try {
      final r = await ApiService.instance.verifyCertificate(v);
      setState(() {
        _loading = false;
        _result = r;
        _notFound = r == null;
      });
    } on ApiException catch (e) {
      setState(() {
        _loading = false;
        _error = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Verify certificate', style: AppTextStyles.h3(context))),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Enter a certificate number',
                    style: AppTextStyles.h2(context), textAlign: TextAlign.center),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Anyone can verify an LMS certificate here. The number is printed on the certificate footer.',
                  style: AppTextStyles.body(context, color: AppColors.textSecondary),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: AppSpacing.xl),
                TextField(
                  controller: _ctrl,
                  autofocus: true,
                  onSubmitted: (_) => _submit(),
                  decoration: const InputDecoration(
                    labelText: 'Certificate number',
                    hintText: 'LMS-2026-XXXXXXXX',
                    prefixIcon: Icon(Icons.workspace_premium_outlined),
                  ),
                  style: const TextStyle(fontFamily: 'monospace'),
                ),
                const SizedBox(height: AppSpacing.md),
                ElevatedButton(
                  onPressed: _loading ? null : _submit,
                  child: Text(_loading ? 'Checking…' : 'Verify'),
                ),
                const SizedBox(height: AppSpacing.xl),
                if (_error != null) _ErrorCard(message: _error!),
                if (_notFound) const _NotFoundCard(),
                if (_result != null) _ResultCard(result: _result!),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  final String message;
  const _ErrorCard({required this.message});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.warningSoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      ),
      child: Text(message,
          style: AppTextStyles.body(context, color: AppColors.warning),
          textAlign: TextAlign.center),
    );
  }
}

class _NotFoundCard extends StatelessWidget {
  const _NotFoundCard();
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.xl),
      decoration: BoxDecoration(
        color: AppColors.dangerSoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.danger.withValues(alpha: 0.4)),
      ),
      child: Column(children: [
        const Icon(Icons.gpp_bad_rounded, color: AppColors.danger, size: 48),
        const SizedBox(height: AppSpacing.md),
        Text('No certificate with that number.',
            style: AppTextStyles.h3(context, color: AppColors.danger),
            textAlign: TextAlign.center),
      ]),
    );
  }
}

class _ResultCard extends StatelessWidget {
  final VerifyResult result;
  const _ResultCard({required this.result});

  String get _issued =>
      result.issuedAt == null ? '—' : DateFormat.yMMMMd().format(result.issuedAt!);

  @override
  Widget build(BuildContext context) {
    final ok = !result.revoked;
    final bg = ok ? AppColors.successSoft : AppColors.dangerSoft;
    final border = ok ? AppColors.success : AppColors.danger;
    final icon = ok ? Icons.verified_rounded : Icons.gpp_bad_rounded;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.xl),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: border.withValues(alpha: 0.4)),
      ),
      child: Column(children: [
        Icon(icon, color: border, size: 56),
        const SizedBox(height: AppSpacing.md),
        Text(ok ? 'Valid certificate' : 'Revoked certificate',
            style: AppTextStyles.h2(context, color: border), textAlign: TextAlign.center),
        const SizedBox(height: AppSpacing.lg),
        _row(context, 'Student', result.studentName ?? '—'),
        _row(context, 'Course', result.courseTitle ?? '—'),
        _row(context, 'Issued', _issued),
        _row(context, 'Number', result.certificateNumber),
        if (result.revoked) ...[
          const SizedBox(height: AppSpacing.md),
          _row(context, 'Revoked reason', result.revokedReason ?? '(no reason)'),
        ],
      ]),
    );
  }

  Widget _row(BuildContext context, String k, String v) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        SizedBox(
          width: 100,
          child: Text(k, style: AppTextStyles.caption(context, color: AppColors.textMuted)),
        ),
        Expanded(child: Text(v, style: AppTextStyles.bodyStrong(context))),
      ]),
    );
  }
}
