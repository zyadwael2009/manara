import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../models/bulk_import.dart';
import '../../services/api_service.dart';

/// Phase 20 — admin's CSV bulk-import screen.
///
/// Two-panel flow:
///   1. Pick a CSV. We parse it locally, show a preview + row-count.
///   2. Tap "Import" → server processes → per-row envelope replaces
///      the preview with a Created / Updated / Skipped / Errors table.
///
/// The endpoint is idempotent; running the same file twice is safe.
class BulkImportScreen extends ConsumerStatefulWidget {
  const BulkImportScreen({super.key});

  @override
  ConsumerState<BulkImportScreen> createState() => _BulkImportScreenState();
}

class _BulkImportScreenState extends ConsumerState<BulkImportScreen> {
  PlatformFile? _file;
  List<List<String>>? _previewRows; // includes header row
  bool _sending = false;
  BulkImportResult? _result;
  String? _error;

  static const _template =
      'email,name,role,gradeName,className\n'
      'amira@school.local,Amira Al-Farsi,student,Grade 9,9-A\n'
      'rivera@school.local,Ms. Rivera,instructor,,\n';

  Future<void> _pick() async {
    setState(() {
      _error = null;
      _result = null;
    });
    final pick = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['csv'],
      withData: true,
    );
    if (pick == null || pick.files.isEmpty) return;
    final file = pick.files.first;
    List<List<String>> preview = const [];
    if (file.bytes != null) {
      final text = utf8.decode(file.bytes!, allowMalformed: true);
      preview = _parseCsv(text, maxRows: 12);
    }
    setState(() {
      _file = file;
      _previewRows = preview;
    });
  }

  Future<void> _submit() async {
    if (_file == null) return;
    setState(() {
      _sending = true;
      _error = null;
      _result = null;
    });
    try {
      final res = await ApiService.instance.uploadBulkUsers(_file!);
      if (!mounted) return;
      setState(() {
        _result = res;
        _sending = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = friendlyError(e);
        _sending = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('Bulk import users', style: AppTextStyles.h2(context)),
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.xl),
        children: [
          _HeaderCard(template: _template),
          const SizedBox(height: AppSpacing.lg),
          Row(children: [
            OutlinedButton.icon(
              onPressed: _sending ? null : _pick,
              icon: const Icon(Icons.upload_file_outlined),
              label: Text(_file == null ? 'Choose CSV…' : 'Choose different CSV…'),
            ),
            if (_file != null) ...[
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(_file!.name,
                    style: AppTextStyles.body(context,
                        color: AppColors.textSecondary),
                    overflow: TextOverflow.ellipsis),
              ),
            ],
          ]),
          const SizedBox(height: AppSpacing.md),
          if (_file != null && _result == null) ...[
            _PreviewTable(rows: _previewRows ?? const []),
            const SizedBox(height: AppSpacing.md),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: ElevatedButton.icon(
                onPressed: _sending ? null : _submit,
                icon: _sending
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          valueColor: AlwaysStoppedAnimation(Colors.white),
                        ),
                      )
                    : const Icon(Icons.cloud_upload_outlined),
                label:
                    Text(_sending ? 'Uploading…' : 'Import into the school'),
              ),
            ),
          ],
          if (_error != null) ...[
            const SizedBox(height: AppSpacing.md),
            _ErrorBanner(message: _error!),
          ],
          if (_result != null) ...[
            const SizedBox(height: AppSpacing.md),
            _ResultSummary(result: _result!),
          ],
        ],
      ),
    );
  }

  /// Deliberately small CSV parser — the file is admin-created, so we
  /// don't need full RFC 4180 (quoted commas, escaped quotes) support.
  /// Cap to `maxRows` for preview.
  List<List<String>> _parseCsv(String text, {int maxRows = 12}) {
    final out = <List<String>>[];
    final lines = const LineSplitter().convert(text);
    for (final line in lines) {
      if (line.trim().isEmpty) continue;
      out.add(line.split(',').map((c) => c.trim()).toList());
      if (out.length >= maxRows) break;
    }
    return out;
  }
}

class _HeaderCard extends StatelessWidget {
  final String template;
  const _HeaderCard({required this.template});
  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: AppColors.primarySoft,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('CSV format',
                style: AppTextStyles.micro(context, color: AppColors.primaryDark)
                    .copyWith(fontWeight: FontWeight.w800, letterSpacing: 0.8)),
            const SizedBox(height: AppSpacing.sm),
            Text('Header row required. Only email, name, and role are required — '
                'gradeName + className apply to students, and the class must '
                'already exist. Re-running the same file is safe (existing users '
                'get updated in-place).',
                style: AppTextStyles.caption(context,
                    color: AppColors.textSecondary)),
            const SizedBox(height: AppSpacing.md),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
                border: Border.all(color: AppColors.border),
              ),
              child: SelectableText(
                template,
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 12,
                  color: AppColors.textPrimary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PreviewTable extends StatelessWidget {
  final List<List<String>> rows;
  const _PreviewTable({required this.rows});
  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) {
      return Text('(Preview unavailable.)',
          style: AppTextStyles.caption(context, color: AppColors.textMuted));
    }
    final header = rows.first;
    final body = rows.skip(1).toList();
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        side: const BorderSide(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          headingRowColor:
              WidgetStateProperty.all(AppColors.surfaceMuted),
          columns: [
            for (final h in header)
              DataColumn(
                label: Text(h.isEmpty ? '(empty)' : h,
                    style: AppTextStyles.caption(context)
                        .copyWith(fontWeight: FontWeight.w800)),
              ),
          ],
          rows: [
            for (final row in body)
              DataRow(cells: [
                for (int i = 0; i < header.length; i++)
                  DataCell(Text(
                    i < row.length ? row[i] : '',
                    style: AppTextStyles.caption(context),
                  )),
              ]),
          ],
        ),
      ),
    );
  }
}

class _ResultSummary extends StatelessWidget {
  final BulkImportResult result;
  const _ResultSummary({required this.result});
  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(children: [
          Expanded(
            child: _tile(context, 'Created', result.created.length,
                AppColors.success, Icons.person_add_alt_1_rounded),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: _tile(context, 'Updated', result.updated.length,
                AppColors.info, Icons.sync_rounded),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: _tile(context, 'Skipped', result.skipped.length,
                AppColors.warning, Icons.skip_next_rounded),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: _tile(context, 'Errors', result.errors.length,
                AppColors.danger, Icons.error_outline_rounded),
          ),
        ]),
        const SizedBox(height: AppSpacing.md),
        if (result.created.isNotEmpty) ...[
          _NoticeCard(
            title: 'Temporary passwords',
            body: 'Each new user has their own password, listed below. This is '
                'the only time they are shown — copy them now. Everyone here '
                'must choose a new password when they first sign in.',
            color: AppColors.warning,
            bg: AppColors.warningSoft,
            icon: Icons.key_outlined,
          ),
          const SizedBox(height: AppSpacing.md),
          _CredentialsCard(rows: result.created),
        ],
        if (result.skipped.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          _RowsCard(
            title: 'Skipped rows',
            color: AppColors.warning,
            bg: AppColors.warningSoft,
            rows: [
              for (final s in result.skipped)
                '#${s.row} · ${s.email} — ${s.reason}',
            ],
          ),
        ],
        if (result.errors.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          _RowsCard(
            title: 'Errors',
            color: AppColors.danger,
            bg: AppColors.dangerSoft,
            rows: [
              for (final e in result.errors) '#${e.row} — ${e.error}',
            ],
          ),
        ],
      ],
    );
  }

  Widget _tile(BuildContext ctx, String label, int n, Color color, IconData icon) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(children: [
        Icon(icon, color: color),
        const SizedBox(height: 4),
        Text('$n',
            style: TextStyle(
                color: color, fontWeight: FontWeight.w800, fontSize: 22)),
        Text(label.toUpperCase(),
            style: AppTextStyles.micro(ctx, color: color)
                .copyWith(letterSpacing: 0.7, fontWeight: FontWeight.w800)),
      ]),
    );
  }
}

class _RowsCard extends StatelessWidget {
  final String title;
  final Color color;
  final Color bg;
  final List<String> rows;
  const _RowsCard({
    required this.title,
    required this.color,
    required this.bg,
    required this.rows,
  });
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title.toUpperCase(),
              style: AppTextStyles.micro(context, color: color)
                  .copyWith(letterSpacing: 0.7, fontWeight: FontWeight.w800)),
          const SizedBox(height: AppSpacing.xs),
          for (final r in rows)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Text(r,
                  style: AppTextStyles.caption(context, color: color)),
            ),
        ],
      ),
    );
  }
}

class _NoticeCard extends StatelessWidget {
  final String title;
  final String body;
  final Color color;
  final Color bg;
  final IconData icon;
  const _NoticeCard({
    required this.title,
    required this.body,
    required this.color,
    required this.bg,
    required this.icon,
  });
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, color: color),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title,
                  style: AppTextStyles.bodyStrong(context, color: color)),
              const SizedBox(height: 2),
              Text(body,
                  style: AppTextStyles.caption(context,
                      color: AppColors.textSecondary)),
            ],
          ),
        ),
      ]),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  final String message;
  const _ErrorBanner({required this.message});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.dangerSoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.danger.withValues(alpha: 0.35)),
      ),
      child: Row(children: [
        const Icon(Icons.error_outline, color: AppColors.danger),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(message,
              style: AppTextStyles.body(context, color: AppColors.danger)),
        ),
      ]),
    );
  }
}


/// The one-and-only listing of the temporary passwords a bulk import just
/// minted. Rendered as selectable text plus a copy-all button, because the
/// office has to get these to real people and the server keeps only hashes.
class _CredentialsCard extends StatelessWidget {
  final List<BulkImportRow> rows;

  const _CredentialsCard({required this.rows});

  String get _asText => [
        for (final r in rows) '${r.email}\t${r.temporaryPassword ?? ""}',
      ].join('\n');

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.warningSoft,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.warning.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'NEW ACCOUNTS',
                  style: AppTextStyles.micro(context, color: AppColors.warning)
                      .copyWith(letterSpacing: 0.7, fontWeight: FontWeight.w800),
                ),
              ),
              TextButton.icon(
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: _asText));
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Copied to clipboard.')),
                  );
                },
                icon: const Icon(Icons.copy_all_rounded, size: 16),
                label: const Text('Copy all'),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.xs),
          SelectionArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final r in rows)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          flex: 3,
                          child: Text(
                            r.email,
                            style: AppTextStyles.caption(context),
                          ),
                        ),
                        Expanded(
                          flex: 2,
                          child: Text(
                            r.temporaryPassword ?? '',
                            style: AppTextStyles.caption(context).copyWith(
                              fontFamily: 'monospace',
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
