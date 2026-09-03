import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/user.dart';
import '../../providers/school_providers.dart';
import '../../services/api_service.dart';
import '../../core/utils/friendly_error.dart';

class DepartmentLeadersScreen extends ConsumerWidget {
  const DepartmentLeadersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final leadersAsync = ref.watch(departmentLeadersProvider);
    final sectionsAsync = ref.watch(sectionsProvider);

    return leadersAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text(friendlyError(e))),
      data: (leaders) => sectionsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(friendlyError(e))),
        data: (sections) => RefreshIndicator(
          onRefresh: () async {
            ref.invalidate(departmentLeadersProvider);
            ref.invalidate(sectionsProvider);
          },
          child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
            Text(
              'Assign a teacher as leader for each department × section slot. '
              'They gain content-edit rights over every course in that scope.',
              style: AppTextStyles.caption(context),
            ),
            const SizedBox(height: AppSpacing.lg),
            for (final dept in AppConstants.courseCategories)
              _DeptCard(dept: dept, sections: sections, leaders: leaders),
          ]),
        ),
      ),
    );
  }
}

class _DeptCard extends ConsumerWidget {
  final String dept;
  final List<dynamic> sections; // Section
  final List<DepartmentLeader> leaders;
  const _DeptCard({required this.dept, required this.sections, required this.leaders});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(AppConstants.prettyCategory(dept), style: AppTextStyles.bodyStrong(context)),
          const Divider(),
          for (final s in sections) _slotRow(context, ref, s),
        ]),
      ),
    );
  }

  Widget _slotRow(BuildContext context, WidgetRef ref, dynamic section) {
    final match = leaders.where((l) => l.department == dept && l.sectionId == section.id).toList();
    final leader = match.isEmpty ? null : match.first;
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      title: Text(section.name, style: AppTextStyles.caption(context)),
      subtitle: Text(
        leader?.teacherName ?? 'unassigned',
        style: AppTextStyles.body(
          context,
          color: leader == null ? AppColors.textMuted : AppColors.textPrimary,
        ),
      ),
      trailing: leader == null
          ? TextButton(
              onPressed: () async => _pick(context, ref, section.id),
              child: const Text('Assign'),
            )
          : Row(mainAxisSize: MainAxisSize.min, children: [
              TextButton(
                onPressed: () async => _pick(context, ref, section.id),
                child: const Text('Change'),
              ),
              IconButton(
                tooltip: 'Remove leader',
                icon: const Icon(Icons.close, size: 18),
                onPressed: () async {
                  try {
                    await ApiService.instance.clearDepartmentLeader(leader.id);
                    ref.invalidate(departmentLeadersProvider);
                  } on ApiException catch (e) {
                    if (context.mounted) {
                      ScaffoldMessenger.of(context)
                          .showSnackBar(SnackBar(content: Text(e.message)));
                    }
                  }
                },
              ),
            ]),
    );
  }

  Future<void> _pick(BuildContext context, WidgetRef ref, String sectionId) async {
    final teachers = await ApiService.instance.listInstructors();
    if (!context.mounted) return;
    final teacher = await showDialog<AppUser>(
      context: context,
      builder: (d) => SimpleDialog(
        title: const Text('Pick a teacher'),
        children: [
          for (final t in teachers)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(d, t),
              child: Text(t.name),
            ),
        ],
      ),
    );
    if (teacher == null) return;
    try {
      await ApiService.instance.setDepartmentLeader(
        department: dept,
        sectionId: sectionId,
        teacherId: teacher.id,
      );
      ref.invalidate(departmentLeadersProvider);
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }
}
