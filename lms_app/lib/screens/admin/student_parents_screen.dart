import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/widgets/app_button.dart';
import '../../core/widgets/app_text_field.dart';
import '../../models/parent_link.dart';
import '../../models/user.dart';
import '../../providers/parent_provider.dart';
import '../../services/api_service.dart';
import '../../core/utils/friendly_error.dart';

/// Admin-facing screen for managing a single student's parent links.
///
/// Shows currently-linked parents on top; below, an "Add parent" flow that
/// searches existing parent accounts, or lets the admin quickly create a new
/// one on the same screen (POST /api/users then link).
class StudentParentsScreen extends ConsumerStatefulWidget {
  final String studentId;
  final String studentName;
  const StudentParentsScreen({
    super.key,
    required this.studentId,
    required this.studentName,
  });

  @override
  ConsumerState<StudentParentsScreen> createState() =>
      _StudentParentsScreenState();
}

class _StudentParentsScreenState extends ConsumerState<StudentParentsScreen> {
  bool _showCreateForm = false;

  Future<void> _link(String parentId, {String relationship = 'guardian'}) async {
    try {
      await ApiService.instance.linkParentToStudent(
        studentId: widget.studentId,
        parentId: parentId,
        relationship: relationship,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Parent linked ✓')));
      }
      ref.invalidate(studentParentsProvider(widget.studentId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _unlink(String parentId) async {
    try {
      await ApiService.instance.unlinkParentFromStudent(
        studentId: widget.studentId, parentId: parentId,
      );
      ref.invalidate(studentParentsProvider(widget.studentId));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(studentParentsProvider(widget.studentId));
    return Scaffold(
      appBar: AppBar(
        title: Text('${widget.studentName} · parents',
            style: AppTextStyles.h3(context)),
      ),
      body: RefreshIndicator(
        onRefresh: () async =>
            ref.invalidate(studentParentsProvider(widget.studentId)),
        child: ListView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          children: [
            Text('LINKED PARENTS',
                style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
            const SizedBox(height: AppSpacing.sm),
            async.when(
              loading: () => const Padding(
                padding: EdgeInsets.all(AppSpacing.md),
                child: LinearProgressIndicator(minHeight: 2),
              ),
              error: (e, _) => Card(
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  child: Text(friendlyError(e),
                      style: AppTextStyles.body(context, color: AppColors.danger)),
                ),
              ),
              data: (links) => links.isEmpty
                  ? Card(
                      child: Padding(
                        padding: const EdgeInsets.all(AppSpacing.lg),
                        child: Text('No parents linked yet.',
                            style: AppTextStyles.caption(context,
                                color: AppColors.textMuted)),
                      ),
                    )
                  : Column(children: [
                      for (final l in links)
                        _LinkedParentTile(link: l, onUnlink: () => _unlink(l.parentId)),
                    ]),
            ),
            const SizedBox(height: AppSpacing.xxl),
            Text('ADD A PARENT',
                style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
            const SizedBox(height: AppSpacing.sm),
            _ParentPicker(onPick: (u) => _link(u.id)),
            const SizedBox(height: AppSpacing.md),
            if (!_showCreateForm)
              TextButton.icon(
                onPressed: () => setState(() => _showCreateForm = true),
                icon: const Icon(Icons.person_add_alt_1_outlined),
                label: const Text('Not on the list? Create a new parent account'),
              )
            else
              _CreateParentForm(
                onCreated: (u) async {
                  setState(() => _showCreateForm = false);
                  await _link(u.id);
                },
              ),
          ],
        ),
      ),
    );
  }
}

// ============================================================================
// Linked parent row
// ============================================================================
class _LinkedParentTile extends StatelessWidget {
  final StudentParent link;
  final VoidCallback onUnlink;
  const _LinkedParentTile({required this.link, required this.onUnlink});
  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(children: [
          CircleAvatar(
            backgroundColor: AppColors.primarySoft,
            child: Text(
              link.name.isNotEmpty ? link.name[0].toUpperCase() : '?',
              style: TextStyle(
                color: AppColors.primaryDark,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(link.name, style: AppTextStyles.bodyStrong(context)),
                Text(
                  '${link.email ?? "—"} · ${link.relationship}',
                  style: AppTextStyles.micro(context, color: AppColors.textMuted),
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: 'Unlink',
            icon: const Icon(Icons.link_off_rounded, color: AppColors.danger),
            onPressed: onUnlink,
          ),
        ]),
      ),
    );
  }
}

// ============================================================================
// Existing-parent picker
// ============================================================================
class _ParentPicker extends StatefulWidget {
  final void Function(AppUser) onPick;
  const _ParentPicker({required this.onPick});
  @override
  State<_ParentPicker> createState() => _ParentPickerState();
}

class _ParentPickerState extends State<_ParentPicker> {
  final _ctrl = TextEditingController();
  Future<List<AppUser>>? _results;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _search() {
    setState(() {
      _results = ApiService.instance.listParents(search: _ctrl.text.trim());
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Row(children: [
        Expanded(
          child: AppTextField(
            controller: _ctrl,
            label: 'Find an existing parent',
            hint: 'name or email',
            icon: Icons.search_rounded,
            onSubmitted: (_) => _search(),
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        OutlinedButton(onPressed: _search, child: const Text('Search')),
      ]),
      const SizedBox(height: AppSpacing.sm),
      if (_results != null)
        FutureBuilder<List<AppUser>>(
          future: _results,
          builder: (context, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const LinearProgressIndicator(minHeight: 2);
            }
            if (snap.hasError) {
              return Text(snap.error.toString(),
                  style: AppTextStyles.caption(context, color: AppColors.danger));
            }
            final rows = snap.data ?? const [];
            if (rows.isEmpty) {
              return Card(
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.md),
                  child: Text('No parent accounts match.',
                      style: AppTextStyles.caption(context,
                          color: AppColors.textMuted)),
                ),
              );
            }
            return Column(children: [
              for (final u in rows)
                Card(
                  margin: const EdgeInsets.only(bottom: AppSpacing.xs),
                  child: ListTile(
                    dense: true,
                    title: Text(u.name, style: AppTextStyles.bodyStrong(context)),
                    subtitle: Text(u.email,
                        style: AppTextStyles.micro(context,
                            color: AppColors.textMuted)),
                    trailing: OutlinedButton(
                      onPressed: () => widget.onPick(u),
                      child: const Text('Link'),
                    ),
                  ),
                ),
            ]);
          },
        ),
    ]);
  }
}

// ============================================================================
// Inline "create new parent account" form
// ============================================================================
class _CreateParentForm extends StatefulWidget {
  final void Function(AppUser) onCreated;
  const _CreateParentForm({required this.onCreated});
  @override
  State<_CreateParentForm> createState() => _CreateParentFormState();
}

class _CreateParentFormState extends State<_CreateParentForm> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController(text: 'parent12');
  bool _busy = false;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _busy = true);
    try {
      final u = await ApiService.instance.adminCreateUser(
        name: _name.text.trim(),
        email: _email.text.trim(),
        password: _password.text,
        role: 'parent',
      );
      widget.onCreated(u);
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Form(
          key: _formKey,
          child: Column(children: [
            AppTextField(
              controller: _name,
              label: 'Parent name',
              icon: Icons.person_outline_rounded,
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? 'Name required.' : null,
            ),
            const SizedBox(height: AppSpacing.sm),
            AppTextField(
              controller: _email,
              label: 'Email',
              icon: Icons.mail_outline_rounded,
              validator: (v) => (v == null || !v.contains('@'))
                  ? 'Valid email required.'
                  : null,
            ),
            const SizedBox(height: AppSpacing.sm),
            AppTextField(
              controller: _password,
              label: 'Temporary password',
              icon: Icons.lock_outline_rounded,
              obscure: true,
              validator: (v) => (v == null || v.length < 8)
                  ? 'Password must be 8+ characters.'
                  : null,
            ),
            const SizedBox(height: AppSpacing.md),
            SizedBox(
              width: double.infinity,
              child: AppButton(
                label: 'Create account + link',
                loading: _busy,
                onPressed: _submit,
              ),
            ),
          ]),
        ),
      ),
    );
  }
}
