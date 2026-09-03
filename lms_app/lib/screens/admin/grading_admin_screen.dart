import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/school_year.dart';
import '../../providers/grading_providers.dart';
import '../../services/api_service.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/failed_load.dart';

/// Admin grading admin — tabs for School years / Terms / Categories / Scale.
/// Full CRUD is available via API; this screen exposes the actions that
/// come up during normal operations (create year, add term, lock/unlock term,
/// rename category, tweak scale band).
class GradingAdminScreen extends ConsumerStatefulWidget {
  const GradingAdminScreen({super.key});

  @override
  ConsumerState<GradingAdminScreen> createState() => _GradingAdminScreenState();
}

class _GradingAdminScreenState extends ConsumerState<GradingAdminScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tab;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Rendered inside AdminHomeScreen's TabBarView — no outer AppBar to avoid
    // a double header. Just tabs + content.
    return Column(children: [
      Container(
        color: Theme.of(context).colorScheme.surface,
        child: TabBar(
          controller: _tab,
          isScrollable: true,
          labelColor: AppColors.primary,
          unselectedLabelColor: AppColors.textSecondary,
          tabs: const [
            Tab(text: 'School years'),
            Tab(text: 'Terms'),
            Tab(text: 'Categories'),
            Tab(text: 'Scale'),
          ],
        ),
      ),
      Expanded(
        child: TabBarView(controller: _tab, children: const [
          _SchoolYearsTab(),
          _TermsTab(),
          _CategoriesTab(),
          _ScaleTab(),
        ]),
      ),
    ]);
  }
}

// ============================================================================
// School years
// ============================================================================
class _SchoolYearsTab extends ConsumerWidget {
  const _SchoolYearsTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(schoolYearsProvider);
    return Scaffold(
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (years) => ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
          for (final y in years)
            Card(
              child: ListTile(
                title: Text(y.name, style: AppTextStyles.bodyStrong(context)),
                subtitle: Text(
                  '${y.startDate ?? "—"} → ${y.endDate ?? "—"}',
                  style: AppTextStyles.caption(context),
                ),
                trailing: y.isCurrent
                    ? Chip(
                        label: const Text('Current'),
                        backgroundColor: AppColors.primarySoft,
                        labelStyle: const TextStyle(color: AppColors.primary),
                      )
                    : TextButton(
                        child: const Text('Make current'),
                        onPressed: () async {
                          try {
                            await ApiService.instance.updateSchoolYear(y.id, isCurrent: true);
                            ref.invalidate(schoolYearsProvider);
                          } on ApiException catch (e) {
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                            }
                          }
                        },
                      ),
              ),
            ),
        ]),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          final name = await _promptText(context, title: 'New school year', hint: 'e.g. 2026-2027');
          if (name == null || name.trim().isEmpty) return;
          try {
            await ApiService.instance.createSchoolYear(name: name.trim(), isCurrent: false);
            ref.invalidate(schoolYearsProvider);
          } on ApiException catch (e) {
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
            }
          }
        },
        icon: const Icon(Icons.add),
        label: const Text('Add year'),
      ),
    );
  }
}

// ============================================================================
// Terms — pick a year, then manage terms in it
// ============================================================================
class _TermsTab extends ConsumerStatefulWidget {
  const _TermsTab();
  @override
  ConsumerState<_TermsTab> createState() => _TermsTabState();
}

class _TermsTabState extends ConsumerState<_TermsTab> {
  SchoolYear? _year;

  @override
  Widget build(BuildContext context) {
    final yearsAsync = ref.watch(schoolYearsProvider);
    return Scaffold(
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl, vertical: AppSpacing.md),
          child: yearsAsync.when(
            loading: () => const LinearProgressIndicator(),
            error: (e, _) => Text(friendlyError(e)),
            data: (years) {
              _year ??= years.firstWhere((y) => y.isCurrent, orElse: () => years.isEmpty ? null as dynamic : years.first);
              return DropdownButtonFormField<SchoolYear>(
                initialValue: _year,
                decoration: const InputDecoration(labelText: 'School year'),
                items: [for (final y in years) DropdownMenuItem(value: y, child: Text(y.name))],
                onChanged: (v) => setState(() => _year = v),
              );
            },
          ),
        ),
        Expanded(
          child: _year == null
              ? const Center(child: Text('Pick a school year.'))
              : Consumer(builder: (context, ref, _) {
                  final termsAsync = ref.watch(termsProvider(_year!.id));
                  return termsAsync.when(
                    loading: () => const Center(child: CircularProgressIndicator()),
                    error: (e, _) => Center(child: Text(friendlyError(e))),
                    data: (terms) => ListView(
                      padding: const EdgeInsets.all(AppSpacing.xl),
                      children: [
                        for (final t in terms)
                          Card(
                            child: ListTile(
                              title: Text(t.name, style: AppTextStyles.bodyStrong(context)),
                              subtitle: t.isLocked
                                  ? Text('Locked', style: AppTextStyles.caption(context, color: AppColors.warning))
                                  : Text('Open', style: AppTextStyles.caption(context, color: AppColors.success)),
                              trailing: TextButton(
                                onPressed: () async {
                                  try {
                                    if (t.isLocked) {
                                      await ApiService.instance.unlockTerm(t.id);
                                    } else {
                                      await ApiService.instance.lockTerm(t.id);
                                    }
                                    ref.invalidate(termsProvider(_year!.id));
                                  } on ApiException catch (e) {
                                    if (context.mounted) {
                                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                                    }
                                  }
                                },
                                child: Text(t.isLocked ? 'Unlock' : 'Lock'),
                              ),
                            ),
                          ),
                      ],
                    ),
                  );
                }),
        ),
      ]),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _year == null
            ? null
            : () async {
                final name = await _promptText(context, title: 'New term', hint: 'e.g. Q3');
                if (name == null || name.trim().isEmpty) return;
                try {
                  await ApiService.instance.createTerm(_year!.id, name: name.trim());
                  ref.invalidate(termsProvider(_year!.id));
                } on ApiException catch (e) {
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                  }
                }
              },
        icon: const Icon(Icons.add),
        label: const Text('Add term'),
      ),
    );
  }
}

// ============================================================================
// Grade categories
// ============================================================================
class _CategoriesTab extends ConsumerWidget {
  const _CategoriesTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(gradeCategoriesProvider);
    return Scaffold(
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        // Phase 29 · T1 — grade categories are required data (the whole
        // gradebook rubric depends on them). Surface the failure loudly
        // with a retry instead of a bare centered error string.
        error: (e, _) => Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: FailedLoad(
            label: "Couldn't load grade categories",
            detail: friendlyError(e),
            onRetry: () => ref.invalidate(gradeCategoriesProvider),
          ),
        ),
        data: (cats) => ListView(
          padding: const EdgeInsets.all(AppSpacing.xl),
          children: [
            for (final c in cats)
              Card(
                child: ListTile(
                  title: Text(c.name),
                  subtitle: Text(c.slug, style: AppTextStyles.caption(context)),
                  trailing: c.isSystem
                      ? const Chip(
                          label: Text('System', style: TextStyle(fontSize: 10)),
                          backgroundColor: AppColors.primarySoft,
                        )
                      : IconButton(
                          tooltip: 'Delete category',
                          icon: const Icon(Icons.delete_outline, size: 18),
                          color: AppColors.danger,
                          onPressed: () async {
                            try {
                              await ApiService.instance.deleteGradeCategory(c.id);
                              ref.invalidate(gradeCategoriesProvider);
                            } on ApiException catch (e) {
                              if (context.mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                              }
                            }
                          },
                        ),
                ),
              ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          final name = await _promptText(context, title: 'New category', hint: 'e.g. Homework');
          if (name == null || name.trim().isEmpty) return;
          try {
            await ApiService.instance.createGradeCategory(name: name.trim());
            ref.invalidate(gradeCategoriesProvider);
          } on ApiException catch (e) {
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
            }
          }
        },
        icon: const Icon(Icons.add),
        label: const Text('Add category'),
      ),
    );
  }
}

// ============================================================================
// Grading scale
// ============================================================================
class _ScaleTab extends ConsumerWidget {
  const _ScaleTab();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(gradingScaleProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text(friendlyError(e))),
      data: (bands) => ListView(
        padding: const EdgeInsets.all(AppSpacing.xl),
        children: [
          for (final b in bands)
            Card(
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: AppColors.primarySoft,
                  child: Text(b.letter,
                      style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700)),
                ),
                title: Text('${b.minPercent}–${b.maxPercent}%'),
                subtitle: Text('GPA ${b.gpaValue.toStringAsFixed(2)}',
                    style: AppTextStyles.caption(context)),
              ),
            ),
        ],
      ),
    );
  }
}

Future<String?> _promptText(BuildContext ctx, {required String title, String? hint}) async {
  // Phase 10 audit fix M4: dispose controller on dialog close.
  final ctrl = TextEditingController();
  try {
    return await showDialog<String>(
      context: ctx,
      builder: (d) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: InputDecoration(hintText: hint),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(d, ctrl.text), child: const Text('Create')),
        ],
      ),
    );
  } finally {
    ctrl.dispose();
  }
}
