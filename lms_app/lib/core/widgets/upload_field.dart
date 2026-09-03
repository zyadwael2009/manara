import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../services/api_service.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import '../theme/app_text_styles.dart';

/// Uploads a file via `POST /api/uploads` and returns the resulting URL.
///
/// Two-tab UX: "Upload" (file_picker → multipart) vs "Paste URL" (plain text).
/// Whichever tab is active on save wins. Reports the resulting URL through
/// [onChanged] whenever it changes.
class UploadField extends StatefulWidget {
  final String kind; // video | pdf | image
  final String? initialUrl;
  final ValueChanged<String?> onChanged;

  const UploadField({
    super.key,
    required this.kind,
    required this.onChanged,
    this.initialUrl,
  });

  @override
  State<UploadField> createState() => _UploadFieldState();
}

class _UploadFieldState extends State<UploadField> {
  late TextEditingController _urlCtrl;
  int _tab = 0; // 0 = upload, 1 = paste URL
  bool _uploading = false;
  String? _uploadedFilename;
  int? _uploadedSize;
  String? _error;

  @override
  void initState() {
    super.initState();
    _urlCtrl = TextEditingController(text: widget.initialUrl ?? '');
    if ((widget.initialUrl ?? '').isNotEmpty) _tab = 1;
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickAndUpload() async {
    final allowed = switch (widget.kind) {
      'video' => ['mp4', 'webm'],
      'pdf' => ['pdf'],
      'image' => ['jpg', 'jpeg', 'png', 'webp'],
      _ => null,
    };
    final res = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: allowed,
      withData: true, // needed for web
    );
    if (res == null || res.files.isEmpty) return;
    final file = res.files.first;
    if ((file.size) > 200 * 1024 * 1024) {
      setState(() => _error = 'File too large. Max 200 MB.');
      return;
    }
    setState(() {
      _uploading = true;
      _error = null;
    });
    try {
      final result = await ApiService.instance.uploadFile(kind: widget.kind, file: file);
      setState(() {
        _uploading = false;
        _uploadedFilename = result.filename;
        _uploadedSize = result.sizeBytes;
        _urlCtrl.text = result.url;
      });
      widget.onChanged(result.url);
    } on ApiException catch (e) {
      setState(() {
        _uploading = false;
        _error = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Container(
        decoration: BoxDecoration(
          border: Border.all(color: AppColors.border),
          borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
        ),
        child: Row(children: [
          _tabBtn(0, 'Upload'),
          _tabBtn(1, 'Paste URL'),
        ]),
      ),
      const SizedBox(height: AppSpacing.md),
      if (_tab == 0) _uploadTab() else _urlTab(),
      if (_error != null) ...[
        const SizedBox(height: AppSpacing.sm),
        Text(_error!, style: AppTextStyles.caption(context, color: AppColors.danger)),
      ],
    ]);
  }

  Widget _tabBtn(int i, String label) {
    final selected = _tab == i;
    return Expanded(
      child: InkWell(
        onTap: () => setState(() => _tab = i),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
          color: selected ? AppColors.primarySoft : Colors.transparent,
          alignment: Alignment.center,
          child: Text(
            label,
            style: TextStyle(
              fontWeight: FontWeight.w600,
              color: selected ? AppColors.primary : AppColors.textSecondary,
            ),
          ),
        ),
      ),
    );
  }

  Widget _uploadTab() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.surfaceMuted,
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        border: Border.all(color: AppColors.border, style: BorderStyle.solid),
      ),
      child: Column(children: [
        const Icon(Icons.cloud_upload_outlined, size: 32, color: AppColors.primary),
        const SizedBox(height: AppSpacing.sm),
        if (_uploading)
          const CircularProgressIndicator()
        else ...[
          Text(
            _uploadedFilename ?? 'Choose a ${widget.kind} file',
            style: AppTextStyles.bodyStrong(context),
          ),
          if (_uploadedSize != null)
            Text(
              _prettySize(_uploadedSize!),
              style: AppTextStyles.caption(context),
            ),
          const SizedBox(height: AppSpacing.md),
          OutlinedButton.icon(
            onPressed: _pickAndUpload,
            icon: const Icon(Icons.folder_open_rounded),
            label: Text(_uploadedFilename == null ? 'Choose file' : 'Replace file'),
          ),
        ],
      ]),
    );
  }

  Widget _urlTab() {
    return TextField(
      controller: _urlCtrl,
      onChanged: widget.onChanged,
      decoration: const InputDecoration(
        hintText: 'https://…',
        prefixIcon: Icon(Icons.link_rounded),
      ),
    );
  }

  String _prettySize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / 1024 / 1024).toStringAsFixed(1)} MB';
  }
}
