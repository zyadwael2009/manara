import 'package:file_picker/file_picker.dart';
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
import '../../providers/auth_provider.dart';
import '../../services/api_service.dart';

/// Student view of one assignment + submit / re-submit flow.
class AssignmentSubmitScreen extends ConsumerStatefulWidget {
  final String assignmentId;
  const AssignmentSubmitScreen({super.key, required this.assignmentId});

  @override
  ConsumerState<AssignmentSubmitScreen> createState() =>
      _AssignmentSubmitScreenState();
}

class _AssignmentSubmitScreenState extends ConsumerState<AssignmentSubmitScreen> {
  final _textCtrl = TextEditingController();
  String? _uploadedUrl;
  String? _uploadedKind;
  String? _uploadedName;
  bool _busy = false;
  bool _seeded = false;

  @override
  void dispose() {
    _textCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickAndUpload() async {
    setState(() => _busy = true);
    try {
      final res = await FilePicker.platform.pickFiles(withData: true);
      if (res == null || res.files.isEmpty) return;
      final f = res.files.first;
      // Guess kind from extension for the /uploads API.
      String kind = 'pdf';
      final ext = (f.extension ?? '').toLowerCase();
      if (['jpg', 'jpeg', 'png', 'webp'].contains(ext)) {
        kind = 'image';
      } else if (['mp4', 'webm'].contains(ext)) {
        kind = 'video';
      } else if (ext == 'pdf') {
        kind = 'pdf';
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('Unsupported file type: .$ext'),
          ));
        }
        return;
      }
      final result = await ApiService.instance.uploadFile(kind: kind, file: f);
      setState(() {
        _uploadedUrl = result.url;
        _uploadedKind = kind;
        _uploadedName = f.name;
      });
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(friendlyError(e))),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submit(Assignment a) async {
    final text = _textCtrl.text.trim();
    if (text.isEmpty && _uploadedUrl == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Add text or upload a file first.')),
      );
      return;
    }
    // Re-submit warning if a graded submission exists.
    if (a.mySubmission?.isGraded ?? false) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (d) => AlertDialog(
          title: const Text('Replace your submission?'),
          content: const Text(
            'You already have a graded submission for this assignment. '
            'Re-submitting will clear the grade — your teacher will need to grade the new work.',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(d, false),
                child: const Text('Cancel')),
            ElevatedButton(onPressed: () => Navigator.pop(d, true),
                child: const Text('Re-submit')),
          ],
        ),
      );
      if (ok != true) return;
    }

    setState(() => _busy = true);
    try {
      await ApiService.instance.submitAssignment(
        a.id,
        responseText: text.isEmpty ? null : text,
        fileUrl: _uploadedUrl,
        fileKind: _uploadedKind,
      );
      ref.invalidate(assignmentDetailProvider(a.id));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Submitted ✓')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(friendlyError(e))),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _seedIfNeeded(Assignment a) {
    if (_seeded) return;
    _seeded = true;
    if (a.mySubmission?.responseText != null) {
      _textCtrl.text = a.mySubmission!.responseText!;
    }
    _uploadedUrl = a.mySubmission?.fileUrl;
    _uploadedKind = a.mySubmission?.fileKind;
    _uploadedName = a.mySubmission?.fileUrl?.split('/').last;
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(assignmentDetailProvider(widget.assignmentId));
    return Scaffold(
      appBar: AppBar(title: Text('Assignment', style: AppTextStyles.h3(context))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (a) {
          _seedIfNeeded(a);
          return ListView(
            padding: const EdgeInsets.all(AppSpacing.xl),
            children: [
              _Header(assignment: a),
              const SizedBox(height: AppSpacing.lg),
              if (a.description.isNotEmpty)
                Text(a.description, style: AppTextStyles.body(context)),
              const SizedBox(height: AppSpacing.xl),
              // Phase 27 — group picker for is_group assignments. Blocks
              // submit if the caller hasn't joined a group yet; server
              // returns 409 in that case too, so this is UX-only.
              if (a.isGroup) ...[
                _GroupPickerSection(assignment: a),
                const SizedBox(height: AppSpacing.xl),
              ],
              if (a.mySubmission != null) _CurrentSubmissionCard(sub: a.mySubmission!),
              const SizedBox(height: AppSpacing.md),
              if (a.allowText) ...[
                Text('YOUR ANSWER',
                    style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
                const SizedBox(height: AppSpacing.sm),
                TextField(
                  controller: _textCtrl,
                  maxLines: 8,
                  minLines: 4,
                  maxLength: 20000,
                  decoration: const InputDecoration(
                    hintText: 'Type your answer here…',
                    alignLabelWithHint: true,
                    border: OutlineInputBorder(),
                  ),
                ),
              ],
              if (a.allowFile) ...[
                const SizedBox(height: AppSpacing.md),
                Text('OR UPLOAD A FILE',
                    style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
                const SizedBox(height: AppSpacing.sm),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(AppSpacing.md),
                    child: Row(children: [
                      const Icon(Icons.attach_file_rounded, color: AppColors.primary),
                      const SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: Text(
                          _uploadedName ?? 'No file selected',
                          overflow: TextOverflow.ellipsis,
                          style: AppTextStyles.body(context,
                              color: _uploadedName == null
                                  ? AppColors.textMuted
                                  : AppColors.textPrimary),
                        ),
                      ),
                      OutlinedButton(
                        onPressed: _busy ? null : _pickAndUpload,
                        child: Text(_uploadedName == null ? 'Choose' : 'Replace'),
                      ),
                    ]),
                  ),
                ),
              ],
              const SizedBox(height: AppSpacing.xl),
              AppButton(
                label: (a.mySubmission?.isGraded ?? false)
                    ? 'Re-submit'
                    : 'Submit',
                loading: _busy,
                onPressed: () => _submit(a),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final Assignment assignment;
  const _Header({required this.assignment});
  @override
  Widget build(BuildContext context) {
    final sub = assignment.mySubmission;
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(spacing: 6, runSpacing: 6, children: [
            _pill(_statusText(sub), bg: _statusBg(sub), fg: Colors.white),
            _pill('${assignment.maxPoints} pts',
                bg: Colors.white.withValues(alpha: 0.16), fg: Colors.white),
          ]),
          const SizedBox(height: AppSpacing.md),
          Text(assignment.title,
              style: TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.w800,
              )),
          if (assignment.dueAt != null) ...[
            const SizedBox(height: 6),
            Text(
              'Due ${DateFormat.yMMMMd().add_jm().format(assignment.dueAt!.toLocal())}',
              style: TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }

  static String _statusText(AssignmentSubmission? s) {
    if (s == null) return 'NOT SUBMITTED';
    if (s.isGraded) return 'GRADED · ${s.gradedScore!.toStringAsFixed(0)}/${(s.gradedMax ?? 100).toStringAsFixed(0)}';
    if (s.isLate) return 'SUBMITTED · LATE';
    return 'SUBMITTED';
  }

  static Color _statusBg(AssignmentSubmission? s) {
    if (s == null) return AppColors.danger.withValues(alpha: 0.7);
    if (s.isGraded) return AppColors.success.withValues(alpha: 0.7);
    if (s.isLate) return AppColors.warning.withValues(alpha: 0.7);
    return Colors.white.withValues(alpha: 0.24);
  }

  Widget _pill(String label, {required Color bg, required Color fg}) => Container(
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

// ============================================================================
// Phase 27 — Group picker (only rendered when assignment.isGroup == true)
// ============================================================================
class _GroupPickerSection extends ConsumerStatefulWidget {
  final Assignment assignment;
  const _GroupPickerSection({required this.assignment});
  @override
  ConsumerState<_GroupPickerSection> createState() =>
      _GroupPickerSectionState();
}

class _GroupPickerSectionState extends ConsumerState<_GroupPickerSection> {
  Future<
      ({List<AssignmentGroup> groups, bool isGroup, int? maxSize})>?
      _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<({List<AssignmentGroup> groups, bool isGroup, int? maxSize})>
      _load() {
    return ApiService.instance.listAssignmentGroups(widget.assignment.id);
  }

  void _reload() {
    setState(() => _future = _load());
    // Also refresh the parent detail so submit button re-enables.
    ref.invalidate(assignmentDetailProvider(widget.assignment.id));
  }

  Future<void> _create() async {
    final nameCtrl = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('New group'),
        content: TextField(
          controller: nameCtrl,
          autofocus: true,
          maxLength: 80,
          decoration: const InputDecoration(
            labelText: 'Group name',
            hintText: 'e.g. Team Nebula',
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
          ElevatedButton(
              onPressed: () => Navigator.pop(d, nameCtrl.text.trim()),
              child: const Text('Create')),
        ],
      ),
    );
    nameCtrl.dispose();
    if (name == null || name.isEmpty) return;
    try {
      await ApiService.instance.createAssignmentGroup(
        widget.assignment.id,
        name: name,
      );
      _reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  Future<void> _join(AssignmentGroup g) async {
    try {
      await ApiService.instance.joinAssignmentGroup(g.id);
      _reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  Future<void> _leave(AssignmentGroup g) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('Leave group?'),
        content: Text('You will leave ${g.name} and can join another.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(d, false),
              child: const Text('Cancel')),
          ElevatedButton(
              onPressed: () => Navigator.pop(d, true),
              child: const Text('Leave')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ApiService.instance.leaveAssignmentGroup(g.id);
      _reload();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final me = ref.watch(authProvider).user;
    final meId = me?.id ?? '';
    return FutureBuilder(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState == ConnectionState.waiting) {
          return const Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: Center(child: CircularProgressIndicator()),
          );
        }
        if (snap.hasError) {
          return Text(friendlyError(snap.error!),
              style: AppTextStyles.caption(context, color: AppColors.danger));
        }
        final data = snap.data!;
        final myGroup = data.groups.firstWhere(
          (g) => g.members.any((m) => m.studentId == meId),
          orElse: () => const AssignmentGroup(
              id: '',
              assignmentId: '',
              name: '',
              memberCount: 0,
              members: []),
        );
        final inGroup = myGroup.id.isNotEmpty;
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  const Icon(Icons.groups_outlined,
                      color: AppColors.primary),
                  const SizedBox(width: AppSpacing.sm),
                  Text('GROUP ASSIGNMENT',
                      style: AppTextStyles.micro(context,
                              color: AppColors.primaryDark)
                          .copyWith(
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.8)),
                  const Spacer(),
                  if (data.maxSize != null)
                    Text('Max ${data.maxSize} per group',
                        style: AppTextStyles.caption(context,
                            color: AppColors.textMuted)),
                ]),
                const SizedBox(height: AppSpacing.md),
                if (inGroup) ...[
                  Text(myGroup.name,
                      style: AppTextStyles.h3(context)
                          .copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: AppSpacing.sm),
                  Text('Members',
                      style: AppTextStyles.micro(context,
                          color: AppColors.textSecondary)),
                  const SizedBox(height: 4),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      for (final m in myGroup.members)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 2),
                          child: Row(children: [
                            const Icon(Icons.person_outline,
                                size: 14, color: AppColors.textMuted),
                            const SizedBox(width: 6),
                            Text(m.studentName ?? '—',
                                style: AppTextStyles.body(context)),
                            if (m.studentId == meId) ...[
                              const SizedBox(width: 6),
                              Text('(you)',
                                  style: AppTextStyles.caption(context,
                                      color: AppColors.textMuted)),
                            ],
                          ]),
                        ),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.md),
                  Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: TextButton.icon(
                      onPressed: () => _leave(myGroup),
                      icon: const Icon(Icons.logout_rounded, size: 16),
                      label: const Text('Leave group'),
                    ),
                  ),
                ] else ...[
                  Text(
                    "Pick a group before submitting. Every group-mate's "
                    'submission is shared — one grade covers the team.',
                    style: AppTextStyles.body(context,
                        color: AppColors.textSecondary),
                  ),
                  const SizedBox(height: AppSpacing.md),
                  if (data.groups.isEmpty)
                    Text('No groups yet — create the first one.',
                        style: AppTextStyles.caption(context,
                            color: AppColors.textMuted))
                  else
                    Column(
                      children: [
                        for (final g in data.groups) _GroupRow(
                          group: g,
                          maxSize: data.maxSize,
                          onJoin: () => _join(g),
                        ),
                      ],
                    ),
                  const SizedBox(height: AppSpacing.md),
                  Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: OutlinedButton.icon(
                      onPressed: _create,
                      icon: const Icon(Icons.group_add_outlined, size: 16),
                      label: const Text('Create group'),
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }
}

class _GroupRow extends StatelessWidget {
  final AssignmentGroup group;
  final int? maxSize;
  final VoidCallback onJoin;
  const _GroupRow({
    required this.group,
    required this.maxSize,
    required this.onJoin,
  });
  @override
  Widget build(BuildContext context) {
    final full = maxSize != null && group.memberCount >= maxSize!;
    final capLabel = maxSize == null
        ? '${group.memberCount}'
        : '${group.memberCount} / $maxSize';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(group.name, style: AppTextStyles.bodyStrong(context)),
                Text('$capLabel member${group.memberCount == 1 ? "" : "s"}',
                    style: AppTextStyles.caption(context,
                        color: AppColors.textMuted)),
              ],
            ),
          ),
          if (full)
            Text('Full',
                style: AppTextStyles.caption(context,
                    color: AppColors.textMuted))
          else
            OutlinedButton(
              onPressed: onJoin,
              child: const Text('Join'),
            ),
        ],
      ),
    );
  }
}

class _CurrentSubmissionCard extends StatelessWidget {
  final AssignmentSubmission sub;
  const _CurrentSubmissionCard({required this.sub});
  @override
  Widget build(BuildContext context) {
    return Card(
      color: sub.isGraded ? AppColors.successSoft : AppColors.primarySoft,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              sub.isGraded
                  ? 'GRADED · ${sub.gradedScore!.toStringAsFixed(0)}/${(sub.gradedMax ?? 100).toStringAsFixed(0)}'
                  : 'CURRENT SUBMISSION',
              style: AppTextStyles.micro(context,
                  color: sub.isGraded ? AppColors.success : AppColors.primaryDark),
            ),
            const SizedBox(height: 4),
            if (sub.submittedAt != null)
              Text(
                'Submitted ${DateFormat.yMMMd().add_jm().format(sub.submittedAt!.toLocal())}',
                style: AppTextStyles.caption(context, color: AppColors.textSecondary),
              ),
            if (sub.gradedFeedback != null && sub.gradedFeedback!.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.md),
              Text('TEACHER FEEDBACK',
                  style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
              const SizedBox(height: 4),
              Text(sub.gradedFeedback!,
                  style: AppTextStyles.body(context, color: AppColors.textPrimary)),
            ],
          ],
        ),
      ),
    );
  }
}
