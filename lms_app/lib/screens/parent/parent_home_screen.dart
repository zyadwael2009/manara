import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/utils/transitions.dart';
import '../../core/widgets/account_menu.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/parent_link.dart';
import '../../providers/auth_provider.dart';
import '../../providers/parent_provider.dart';
import '../shared/inbox_screen.dart';
import '../shared/notifications_bell.dart';
import '../shared/search_screen.dart';
import 'child_dashboard_screen.dart';
import '../../core/widgets/trailing_chevron.dart';

/// Parent portal home — list of linked children. Read-only landing view.
class ParentHomeScreen extends ConsumerWidget {
  const ParentHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(linkedChildrenProvider);
    final user = ref.watch(authProvider).user;
    final firstName = (user?.name ?? '').split(' ').first;

    return Scaffold(
      appBar: AppBar(
        // Phase 26 · T6 — bump to h2 so the parent home reads with
        // the same weight as the student/teacher/admin home titles.
        title: Text('Parent portal', style: AppTextStyles.h2(context)),
        actions: [
          IconButton(
            tooltip: 'Search',
            icon: const Icon(Icons.search_rounded),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const SearchScreen()),
              );
            },
          ),
          const NotificationsBell(),
          IconButton(
            tooltip: 'Messages',
            icon: const Icon(Icons.chat_bubble_outline_rounded),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const InboxScreen()),
              );
            },
          ),
          const AccountMenu(),
        ],
      ),
      body: RefreshIndicator(
        // Phase 10 audit fix M6: wait on the refetch so the spinner stays
        // visible until the new data lands — was flashing off immediately
        // because `invalidate` is synchronous.
        onRefresh: () async {
          ref.invalidate(linkedChildrenProvider);
          await ref.read(linkedChildrenProvider.future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(friendlyError(e), style: AppTextStyles.body(context))),
          ]),
          data: (kids) => kids.isEmpty
              ? ListView(children: const [
                  SizedBox(height: 80),
                  EmptyState(
                    icon: Icons.family_restroom_outlined,
                    title: 'No children linked yet',
                    message:
                        'Ask your school office to link a student to your account.',
                  ),
                ])
              : ListView(
                  padding: const EdgeInsets.all(AppSpacing.xl),
                  children: [
                    if (firstName.isNotEmpty)
                      Text('Hello, $firstName',
                          style: AppTextStyles.display(context)),
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      firstName.isEmpty
                          ? 'Your linked children'
                          : 'Here\'s what your children are working on.',
                      style: AppTextStyles.body(context,
                          color: AppColors.textSecondary),
                    ),
                    const SizedBox(height: AppSpacing.xxl),
                    for (final k in kids) _ChildCard(kid: k),
                  ],
                ),
        ),
      ),
    );
  }
}

class _ChildCard extends StatelessWidget {
  final LinkedChild kid;
  const _ChildCard({required this.kid});

  @override
  Widget build(BuildContext context) {
    final initial = kid.name.isNotEmpty ? kid.name[0].toUpperCase() : '?';
    return Card(
      margin: const EdgeInsets.only(bottom: AppSpacing.md),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        onTap: () {
          Navigator.of(context).push(fadeThroughRoute(
              ChildDashboardScreen(childId: kid.studentId, childName: kid.name)));
        },
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Row(
            children: [
              // Phase 12: red badge dot when today's attendance = absent.
              Stack(clipBehavior: Clip.none, children: [
                Container(
                  width: 52, height: 52,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [AppColors.primary, AppColors.primaryDark],
                    ),
                    shape: BoxShape.circle,
                  ),
                  child: Text(initial,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                      )),
                ),
                if (kid.todayAttendanceStatus == 'absent')
                  Positioned(
                    right: -2, top: -2,
                    child: Container(
                      width: 16, height: 16,
                      decoration: BoxDecoration(
                        color: AppColors.danger,
                        shape: BoxShape.circle,
                        border: Border.all(color: AppColors.surface, width: 2),
                      ),
                    ),
                  ),
              ]),
              const SizedBox(width: AppSpacing.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(kid.name, style: AppTextStyles.h3(context)),
                    const SizedBox(height: 2),
                    Text(
                      _subtitle(),
                      style: AppTextStyles.caption(context,
                          color: AppColors.textMuted),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.primarySoft,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                ),
                child: Text(kid.relationship,
                    style: AppTextStyles.micro(context,
                        color: AppColors.primaryDark)),
              ),
              const SizedBox(width: AppSpacing.sm),
              const TrailingChevron(color: AppColors.textMuted),
            ],
          ),
        ),
      ),
    );
  }

  String _subtitle() {
    final parts = <String>[];
    if (kid.gradeName != null) parts.add(kid.gradeName!);
    if (kid.className != null) parts.add(kid.className!);
    return parts.isEmpty ? 'No class assigned' : parts.join(' · ');
  }
}
