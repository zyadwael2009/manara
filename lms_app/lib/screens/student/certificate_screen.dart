import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/certificate.dart';
import '../../providers/certificates_provider.dart';
import '../../services/api_service.dart';
import '../../core/utils/friendly_error.dart';

/// Certificate detail — styled preview + Download PDF + Copy verify link.
class CertificateScreen extends ConsumerWidget {
  final String certificateId;
  const CertificateScreen({super.key, required this.certificateId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(certificateProvider(certificateId));
    return Scaffold(
      appBar: AppBar(title: Text('Certificate', style: AppTextStyles.h3(context))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (cert) => _Body(cert: cert),
      ),
    );
  }
}

class _Body extends StatelessWidget {
  final Certificate cert;
  const _Body({required this.cert});

  String get _issuedStr {
    if (cert.issuedAt == null) return '—';
    return DateFormat.yMMMMd().format(cert.issuedAt!);
  }

  @override
  Widget build(BuildContext context) {
    final verifyUrl = '${ApiService.instance.baseUrl}/verify/${cert.certificateNumber}';
    return ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
      _PreviewCard(cert: cert, issuedStr: _issuedStr),
      const SizedBox(height: AppSpacing.lg),
      if (cert.revoked) _RevokedBanner(reason: cert.revokedReason),
      const SizedBox(height: AppSpacing.md),
      Row(children: [
        Expanded(
          child: ElevatedButton.icon(
            onPressed: () async {
              final url = ApiService.instance.certificatePdfUrl(cert.id);
              // Session token is sent via query for browser opens; we don't
              // ship it via URL though (server accepts cookie or header).
              // On web, the browser will present the cookie; on native, the
              // browser opens without our session — that's a limitation.
              await launchUrl(Uri.parse(url), mode: LaunchMode.platformDefault);
            },
            icon: const Icon(Icons.picture_as_pdf_outlined),
            label: const Text('Download PDF'),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        OutlinedButton.icon(
          onPressed: () async {
            await Clipboard.setData(ClipboardData(text: verifyUrl));
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Verify link copied.')),
              );
            }
          },
          icon: const Icon(Icons.link_rounded),
          label: const Text('Copy verify link'),
        ),
      ]),
      const SizedBox(height: AppSpacing.md),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Certificate number',
                  style: AppTextStyles.micro(context, color: AppColors.textMuted)),
              const SizedBox(height: 4),
              SelectableText(cert.certificateNumber, style: AppTextStyles.bodyStrong(context)),
              const SizedBox(height: AppSpacing.md),
              Text('Verify URL',
                  style: AppTextStyles.micro(context, color: AppColors.textMuted)),
              const SizedBox(height: 4),
              SelectableText(verifyUrl, style: AppTextStyles.caption(context)),
            ],
          ),
        ),
      ),
    ]);
  }
}

class _PreviewCard extends StatelessWidget {
  final Certificate cert;
  final String issuedStr;
  const _PreviewCard({required this.cert, required this.issuedStr});

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 297 / 210, // landscape A4
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          border: Border.all(color: AppColors.primary, width: 2),
          boxShadow: const [
            BoxShadow(color: Color(0x22000000), blurRadius: 20, offset: Offset(0, 8)),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Container(
            decoration: BoxDecoration(
              border: Border.all(color: AppColors.accent, width: 1),
              borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
            ),
            padding: const EdgeInsets.all(20),
            child: Column(
              children: [
                Text('LMS · SCHOOL OF LEARNING',
                    style: TextStyle(
                      color: AppColors.primaryDark,
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                      letterSpacing: 1.2,
                    )),
                const Spacer(flex: 1),
                Text(
                  'Certificate of Completion',
                  style: TextStyle(
                    fontSize: 34,
                    fontWeight: FontWeight.w800,
                    color: AppColors.textPrimary,
                    letterSpacing: -0.5,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                Text('This certificate is proudly presented to',
                    style: TextStyle(color: AppColors.textSecondary, fontSize: 12),
                    textAlign: TextAlign.center),
                const SizedBox(height: 12),
                FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(
                    cert.studentName ?? '—',
                    style: TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.w800,
                      color: AppColors.primary,
                    ),
                  ),
                ),
                const SizedBox(height: 4),
                Container(
                  height: 1,
                  margin: const EdgeInsets.symmetric(horizontal: 60),
                  color: AppColors.border,
                ),
                const SizedBox(height: 12),
                Text('for successfully completing the course',
                    style: TextStyle(color: AppColors.textSecondary, fontSize: 12),
                    textAlign: TextAlign.center),
                const SizedBox(height: 8),
                Text(cert.courseTitle ?? '—',
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                    textAlign: TextAlign.center),
                const SizedBox(height: 12),
                Text('Issued on $issuedStr',
                    style: TextStyle(
                      fontStyle: FontStyle.italic,
                      color: AppColors.textSecondary,
                      fontSize: 11,
                    )),
                const Spacer(flex: 2),
                Row(children: [
                  Text('Certificate No. ${cert.certificateNumber}',
                      style: TextStyle(color: AppColors.textMuted, fontSize: 9)),
                  const Spacer(),
                ]),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RevokedBanner extends StatelessWidget {
  final String? reason;
  const _RevokedBanner({this.reason});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.dangerSoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.danger.withValues(alpha: 0.4)),
      ),
      child: Row(children: [
        const Icon(Icons.block_rounded, color: AppColors.danger),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            reason == null
                ? 'This certificate has been revoked.'
                : 'This certificate has been revoked. Reason: $reason',
            style: AppTextStyles.body(context, color: AppColors.danger),
          ),
        ),
      ]),
    );
  }
}
