import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../services/api_service.dart';

/// Phase 25 — admin data export panel.
///
/// Each row is one downloadable CSV. Attendance + grades support
/// optional filters (date window / term id) surfaced as small inline
/// text fields.
class DataExportScreen extends ConsumerStatefulWidget {
  const DataExportScreen({super.key});
  @override
  ConsumerState<DataExportScreen> createState() => _DataExportScreenState();
}

class _DataExportScreenState extends ConsumerState<DataExportScreen> {
  late Future<List<Map<String, dynamic>>> _kinds;
  final _attFrom = TextEditingController();
  final _attTo = TextEditingController();
  final _gradesTerm = TextEditingController();

  @override
  void initState() {
    super.initState();
    _kinds = ApiService.instance.listExportKinds();
  }

  @override
  void dispose() {
    _attFrom.dispose();
    _attTo.dispose();
    _gradesTerm.dispose();
    super.dispose();
  }

  void _download(String kind, {Map<String, String>? params}) {
    final url = ApiService.instance.csvExportUrl(kind, params: params);
    launchUrl(Uri.parse(url), mode: LaunchMode.platformDefault);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: Text('Data export', style: AppTextStyles.h2(context))),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _kinds,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text(friendlyError(snap.error)));
          }
          final kinds = snap.data ?? const [];
          return ListView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            children: [
              _Header(),
              const SizedBox(height: AppSpacing.lg),
              for (final k in kinds) _KindCard(
                kind: k,
                extraChild: _extrasFor(k['id'] as String? ?? ''),
                onDownload: () {
                  final id = k['id'] as String? ?? '';
                  if (id == 'attendance') {
                    _download(id, params: {
                      if (_attFrom.text.trim().isNotEmpty) 'from': _attFrom.text.trim(),
                      if (_attTo.text.trim().isNotEmpty) 'to': _attTo.text.trim(),
                    });
                  } else if (id == 'grades') {
                    _download(id, params: {
                      if (_gradesTerm.text.trim().isNotEmpty) 'termId': _gradesTerm.text.trim(),
                    });
                  } else {
                    _download(id);
                  }
                },
              ),
            ],
          );
        },
      ),
    );
  }

  Widget? _extrasFor(String id) {
    if (id == 'attendance') {
      return Row(children: [
        Expanded(
          child: TextField(
            controller: _attFrom,
            decoration: const InputDecoration(
              labelText: 'From (YYYY-MM-DD)',
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: TextField(
            controller: _attTo,
            decoration: const InputDecoration(
              labelText: 'To (YYYY-MM-DD)',
              border: OutlineInputBorder(),
              isDense: true,
            ),
          ),
        ),
      ]);
    }
    if (id == 'grades') {
      return TextField(
        controller: _gradesTerm,
        decoration: const InputDecoration(
          labelText: 'Term id (optional)',
          border: OutlineInputBorder(),
          isDense: true,
        ),
      );
    }
    return null;
  }
}

class _Header extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.primarySoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      ),
      child: Row(children: [
        const Icon(Icons.download_rounded, color: AppColors.primaryDark),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Download school data',
                  style: AppTextStyles.bodyStrong(context,
                      color: AppColors.primaryDark)),
              const SizedBox(height: 2),
              Text(
                'CSV files open in Excel, Google Sheets, or any text editor. '
                'Each file includes a header row.',
                style: AppTextStyles.caption(context,
                    color: AppColors.textSecondary),
              ),
            ],
          ),
        ),
      ]),
    );
  }
}

class _KindCard extends StatelessWidget {
  final Map<String, dynamic> kind;
  final Widget? extraChild;
  final VoidCallback onDownload;
  const _KindCard({
    required this.kind,
    required this.onDownload,
    this.extraChild,
  });
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Card(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          side: const BorderSide(color: AppColors.border),
        ),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text((kind['label'] as String?) ?? '',
                  style: AppTextStyles.h3(context)
                      .copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 4),
              Text((kind['description'] as String?) ?? '',
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
              if (extraChild != null) ...[
                const SizedBox(height: AppSpacing.md),
                extraChild!,
              ],
              const SizedBox(height: AppSpacing.md),
              Align(
                alignment: Alignment.centerRight,
                child: ElevatedButton.icon(
                  onPressed: onDownload,
                  icon: const Icon(Icons.file_download_outlined),
                  label: const Text('Download CSV'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
