import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/paged_list_view.dart';
import '../../models/comm.dart';
import '../../providers/comm_providers.dart';
import '../../services/api_service.dart';

/// Phase 21 — bell IconButton with an unread-count red-dot badge. Tap
/// opens the notifications list (marks read on visit).
class NotificationsBell extends ConsumerWidget {
  const NotificationsBell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(myNotificationsProvider);
    final unread = async.maybeWhen(
      data: (p) => p.unreadCount,
      orElse: () => 0,
    );
    return Stack(clipBehavior: Clip.none, children: [
      IconButton(
        tooltip: 'Notifications',
        icon: const Icon(Icons.notifications_none_rounded),
        onPressed: () async {
          await Navigator.of(context).push(fadeThroughRoute(
            const NotificationsScreen(),
          ));
          ref.invalidate(myNotificationsProvider);
        },
      ),
      if (unread > 0)
        Positioned(
          right: 6,
          top: 6,
          child: IgnorePointer(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
              constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
              decoration: BoxDecoration(
                color: AppColors.danger,
                borderRadius: BorderRadius.circular(999),
                border: Border.all(color: Colors.white, width: 1.5),
              ),
              alignment: Alignment.center,
              child: Text(
                unread > 9 ? '9+' : '$unread',
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 10,
                    fontWeight: FontWeight.w800,
                    height: 1.1),
              ),
            ),
          ),
        ),
    ]);
  }
}

class NotificationsScreen extends ConsumerStatefulWidget {
  const NotificationsScreen({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() =>
      _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  // Phase 30 · T4 — key on the paged list so pull-to-refresh can
  // reset it from page 1 without rebuilding the whole screen tree.
  final _pagedKey = GlobalKey<PagedListViewState<AppNotification>>();

  Future<void> _markAllRead() async {
    await ApiService.instance.markNotificationsRead(all: true);
    ref.invalidate(myNotificationsProvider);
    _pagedKey.currentState?.refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('Notifications', style: AppTextStyles.h2(context)),
        actions: [
          TextButton(
            onPressed: _markAllRead,
            child: const Text('Mark all read'),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(myNotificationsProvider);
          await _pagedKey.currentState?.refresh();
        },
        child: PagedListView<AppNotification>(
          key: _pagedKey,
          padding: const EdgeInsets.symmetric(vertical: AppSpacing.md),
          separator:
              const Divider(height: 1, color: AppColors.divider),
          emptyPlaceholder: ListView(children: const [
            EmptyState(
              icon: Icons.notifications_none_rounded,
              title: 'No notifications yet',
              message: "You'll see grades, replies, and reminders here.",
            ),
          ]),
          fetchPage: (page) async {
            final resp = await ApiService.instance
                .myNotifications(page: page, pageSize: 20);
            return PagedResult<AppNotification>(
              items: resp.notifications,
              hasMore: resp.hasMore ?? (resp.notifications.length >= 20),
            );
          },
          itemBuilder: (context, item, _) => _NotificationTile(item: item),
        ),
      ),
    );
  }
}

class _NotificationTile extends StatelessWidget {
  final AppNotification item;
  const _NotificationTile({required this.item});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: _iconBgFor(item.kind),
        child: Icon(_iconFor(item.kind), color: _iconFgFor(item.kind), size: 18),
      ),
      title: Row(children: [
        Expanded(
          child: Text(item.title,
              style: AppTextStyles.body(context).copyWith(
                fontWeight: item.isUnread ? FontWeight.w800 : FontWeight.w500,
              )),
        ),
        if (item.isUnread)
          Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.primary,
            ),
          ),
      ]),
      subtitle: item.body.isNotEmpty
          ? Text(item.body,
              style: AppTextStyles.caption(context,
                  color: AppColors.textSecondary),
              maxLines: 2,
              overflow: TextOverflow.ellipsis)
          : null,
      trailing: Text(_ago(item.createdAt),
          style: AppTextStyles.caption(context, color: AppColors.textMuted)),
    );
  }

  static IconData _iconFor(String kind) => switch (kind) {
        'grade_updated' => Icons.grade_outlined,
        'assignment_graded' => Icons.assignment_turned_in_outlined,
        'certificate_issued' => Icons.workspace_premium_outlined,
        'announcement' => Icons.campaign_outlined,
        'attendance_marked' => Icons.event_available_outlined,
        'message' => Icons.chat_bubble_outline_rounded,
        'comment_reply' => Icons.forum_outlined,
        _ => Icons.notifications_none_rounded,
      };

  static Color _iconBgFor(String kind) => switch (kind) {
        'certificate_issued' => AppColors.warningSoft,
        'announcement' => AppColors.dangerSoft,
        'attendance_marked' => AppColors.warningSoft,
        'message' || 'comment_reply' => AppColors.infoSoft,
        _ => AppColors.primarySoft,
      };

  static Color _iconFgFor(String kind) => switch (kind) {
        'certificate_issued' => AppColors.warning,
        'announcement' => AppColors.danger,
        'attendance_marked' => AppColors.warning,
        'message' || 'comment_reply' => AppColors.info,
        _ => AppColors.primaryDark,
      };

  static String _ago(DateTime? t) {
    if (t == null) return '';
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'now';
    if (d.inHours < 1) return '${d.inMinutes}m';
    if (d.inDays < 1) return '${d.inHours}h';
    if (d.inDays < 7) return '${d.inDays}d';
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return '${t.day} ${months[t.month - 1]}';
  }
}
