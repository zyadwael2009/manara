import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/widgets/upload_field.dart';
import '../../models/lesson.dart';

/// Modal-sheet form for creating or editing a Lesson.
/// Returns a `_LessonDraft` on save, null on cancel.
class LessonEditorSheet extends StatefulWidget {
  final Lesson? existing;
  const LessonEditorSheet({super.key, this.existing});

  @override
  State<LessonEditorSheet> createState() => _LessonEditorSheetState();
}

class LessonDraft {
  final String title;
  final String type; // video | text | pdf
  final String? contentUrl;
  final String? contentText;
  final int? durationMinutes;
  const LessonDraft({
    required this.title,
    required this.type,
    this.contentUrl,
    this.contentText,
    this.durationMinutes,
  });
}

class _LessonEditorSheetState extends State<LessonEditorSheet> {
  late final TextEditingController _title;
  late final TextEditingController _text;
  late final TextEditingController _duration;
  String _type = 'text';
  String? _uploadUrl;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    _title = TextEditingController(text: e?.title ?? '');
    _text = TextEditingController(text: e?.contentText ?? '');
    _duration = TextEditingController(
      text: e?.durationMinutes != null ? '${e!.durationMinutes}' : '',
    );
    _type = e?.type ?? 'text';
    _uploadUrl = e?.contentUrl;
  }

  @override
  void dispose() {
    _title.dispose();
    _text.dispose();
    _duration.dispose();
    super.dispose();
  }

  bool _validate() {
    if (_title.text.trim().isEmpty) return false;
    if (_type == 'text' && _text.text.trim().isEmpty) return false;
    if (_type != 'text' && (_uploadUrl == null || _uploadUrl!.isEmpty)) return false;
    return true;
  }

  void _save() {
    if (!_validate()) return;
    final int? minutes =
        _duration.text.trim().isEmpty ? null : int.tryParse(_duration.text.trim());
    Navigator.of(context).pop(
      LessonDraft(
        title: _title.text.trim(),
        type: _type,
        contentUrl: _type == 'text' ? null : _uploadUrl,
        contentText: _type == 'text' ? _text.text.trim() : null,
        durationMinutes: minutes,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.existing != null;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: AppSpacing.xl,
          right: AppSpacing.xl,
          top: AppSpacing.xl,
          bottom: MediaQuery.of(context).viewInsets.bottom + AppSpacing.xl,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(isEdit ? 'Edit lesson' : 'New lesson', style: AppTextStyles.h2(context)),
              const SizedBox(height: AppSpacing.lg),
              TextField(
                controller: _title,
                autofocus: !isEdit,
                decoration: const InputDecoration(labelText: 'Title'),
              ),
              const SizedBox(height: AppSpacing.md),
              DropdownButtonFormField<String>(
                initialValue: _type,
                decoration: const InputDecoration(labelText: 'Type'),
                items: const [
                  DropdownMenuItem(value: 'text', child: Text('Text')),
                  DropdownMenuItem(value: 'video', child: Text('Video')),
                  DropdownMenuItem(value: 'pdf', child: Text('PDF')),
                ],
                onChanged: (v) => setState(() => _type = v ?? 'text'),
              ),
              const SizedBox(height: AppSpacing.md),
              TextField(
                controller: _duration,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Duration (minutes, optional)'),
              ),
              const SizedBox(height: AppSpacing.md),
              Text('Content', style: AppTextStyles.bodyStrong(context)),
              const SizedBox(height: AppSpacing.sm),
              if (_type == 'text')
                TextField(
                  controller: _text,
                  maxLines: 8,
                  decoration: const InputDecoration(
                    hintText: 'Lesson body — Markdown is supported.',
                    alignLabelWithHint: true,
                  ),
                )
              else
                UploadField(
                  kind: _type, // video or pdf
                  initialUrl: _uploadUrl,
                  onChanged: (u) => setState(() => _uploadUrl = u),
                ),
              const SizedBox(height: AppSpacing.xl),
              Row(mainAxisAlignment: MainAxisAlignment.end, children: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Cancel'),
                ),
                const SizedBox(width: AppSpacing.sm),
                ElevatedButton(
                  onPressed: _validate() ? _save : null,
                  child: Text(isEdit ? 'Save changes' : 'Create lesson'),
                ),
              ]),
              if (!_validate())
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.sm),
                  child: Text(
                    'Title and content are required.',
                    style: AppTextStyles.caption(context, color: AppColors.textMuted),
                    textAlign: TextAlign.right,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
