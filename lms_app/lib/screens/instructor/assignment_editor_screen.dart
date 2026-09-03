import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/app_button.dart';
import '../../models/assignment.dart';
import '../../providers/assignments_provider.dart';
import '../../services/api_service.dart';

/// Create OR edit an assignment. Pass `moduleId` for create, `existing`
/// for edit. Publish/unpublish + delete controls appear after save.
class AssignmentEditorScreen extends ConsumerStatefulWidget {
  final String moduleId;
  final String courseId;
  final Assignment? existing;
  const AssignmentEditorScreen({
    super.key,
    required this.moduleId,
    required this.courseId,
    this.existing,
  });

  @override
  ConsumerState<AssignmentEditorScreen> createState() =>
      _AssignmentEditorScreenState();
}

class _AssignmentEditorScreenState extends ConsumerState<AssignmentEditorScreen> {
  final _title = TextEditingController();
  final _description = TextEditingController();
  final _maxPoints = TextEditingController(text: '100');
  DateTime? _dueAt;
  bool _allowText = true;
  bool _allowFile = true;
  bool _busy = false;
  Assignment? _current;

  @override
  void initState() {
    super.initState();
    if (widget.existing != null) {
      _current = widget.existing;
      _title.text = widget.existing!.title;
      _description.text = widget.existing!.description;
      _maxPoints.text = widget.existing!.maxPoints.toString();
      _dueAt = widget.existing!.dueAt;
      _allowText = widget.existing!.allowText;
      _allowFile = widget.existing!.allowFile;
    }
  }

  @override
  void dispose() {
    _title.dispose();
    _description.dispose();
    _maxPoints.dispose();
    super.dispose();
  }

  Future<void> _pickDue() async {
    final base = _dueAt ?? DateTime.now().add(const Duration(days: 3));
    final d = await showDatePicker(
      context: context,
      initialDate: base,
      firstDate: DateTime.now().subtract(const Duration(days: 30)),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (d == null || !mounted) return;
    final t = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(base),
    );
    if (t == null) return;
    setState(() => _dueAt =
        DateTime(d.year, d.month, d.day, t.hour, t.minute));
  }

  Future<void> _save() async {
    final title = _title.text.trim();
    if (title.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Title is required.')),
      );
      return;
    }
    final maxPoints = int.tryParse(_maxPoints.text) ?? 100;
    if (!_allowText && !_allowFile) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enable at least one of text / file.')),
      );
      return;
    }
    setState(() => _busy = true);
    try {
      Assignment saved;
      if (_current == null) {
        saved = await ApiService.instance.createAssignment(
          widget.moduleId,
          title: title,
          description: _description.text.trim(),
          maxPoints: maxPoints,
          allowText: _allowText,
          allowFile: _allowFile,
          dueAt: _dueAt,
        );
      } else {
        saved = await ApiService.instance.updateAssignment(
          _current!.id,
          title: title,
          description: _description.text.trim(),
          maxPoints: maxPoints,
          allowText: _allowText,
          allowFile: _allowFile,
          dueAt: _dueAt,
        );
      }
      setState(() => _current = saved);
      ref.invalidate(courseAssignmentsProvider(widget.courseId));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Saved ✓')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _togglePublish() async {
    if (_current == null) return;
    setState(() => _busy = true);
    try {
      final saved = _current!.isPublished
          ? await ApiService.instance.unpublishAssignment(_current!.id)
          : await ApiService.instance.publishAssignment(_current!.id);
      setState(() => _current = saved);
      ref.invalidate(courseAssignmentsProvider(widget.courseId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete() async {
    if (_current == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('Delete assignment?'),
        content: const Text(
          'This is irreversible. Assignments with student submissions can\'t be deleted.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(d, true),
              style: ElevatedButton.styleFrom(backgroundColor: AppColors.danger),
              child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.instance.deleteAssignment(_current!.id);
      ref.invalidate(courseAssignmentsProvider(widget.courseId));
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_current == null ? 'New assignment' : 'Edit assignment',
            style: AppTextStyles.h3(context)),
        actions: [
          if (_current != null)
            IconButton(
              tooltip: 'Delete',
              icon: const Icon(Icons.delete_outline_rounded, color: AppColors.danger),
              onPressed: _delete,
            ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.xl),
        children: [
          TextField(
            controller: _title,
            decoration: const InputDecoration(
              labelText: 'Title',
              border: OutlineInputBorder(),
            ),
            autofocus: true,
          ),
          const SizedBox(height: AppSpacing.md),
          TextField(
            controller: _description,
            maxLines: 6,
            minLines: 3,
            decoration: const InputDecoration(
              labelText: 'Instructions',
              alignLabelWithHint: true,
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          Row(children: [
            SizedBox(
              width: 120,
              child: TextField(
                controller: _maxPoints,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Max points',
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: _pickDue,
                icon: const Icon(Icons.event_rounded, size: 18),
                label: Text(_dueAt == null
                    ? 'Due date (optional)'
                    : DateFormat.yMMMd().add_jm().format(_dueAt!)),
              ),
            ),
          ]),
          const SizedBox(height: AppSpacing.md),
          Card(
            child: Column(children: [
              SwitchListTile(
                title: const Text('Allow text answer'),
                subtitle: const Text('Students can type an inline response'),
                value: _allowText,
                onChanged: (v) => setState(() => _allowText = v),
              ),
              SwitchListTile(
                title: const Text('Allow file upload'),
                subtitle: const Text('Students can upload a PDF / image'),
                value: _allowFile,
                onChanged: (v) => setState(() => _allowFile = v),
              ),
            ]),
          ),
          const SizedBox(height: AppSpacing.xl),
          AppButton(label: 'Save', loading: _busy, onPressed: _save),
          if (_current != null) ...[
            const SizedBox(height: AppSpacing.md),
            OutlinedButton.icon(
              onPressed: _togglePublish,
              icon: Icon(_current!.isPublished
                  ? Icons.visibility_off_rounded
                  : Icons.visibility_rounded),
              label: Text(_current!.isPublished ? 'Un-publish' : 'Publish'),
            ),
          ],
        ],
      ),
    );
  }
}
