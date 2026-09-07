import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/utils/transitions.dart';
import '../../models/comm.dart';
import '../../providers/auth_provider.dart';
import '../../providers/comm_providers.dart';
import '../../services/api_service.dart';

/// Phase 21 — one-to-one messaging inbox reachable from the AppBar on
/// parent + teacher home screens. Left column = thread list; tap a row
/// to push the `ThreadChatScreen`.
class InboxScreen extends ConsumerWidget {
  const InboxScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(myThreadsProvider);
    final me = ref.watch(authProvider).user;
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(title: Text('Messages', style: AppTextStyles.h2(context))),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(myThreadsProvider);
          await ref.read(myThreadsProvider.future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(friendlyError(e))),
          ]),
          data: (threads) {
            if (threads.isEmpty) {
              return ListView(children: [
                const SizedBox(height: 80),
                Center(
                  child: Text(
                      'No conversations yet.\nStart one from a student or teacher profile.',
                      textAlign: TextAlign.center,
                      style: AppTextStyles.body(context,
                          color: AppColors.textMuted)),
                ),
              ]);
            }
            return ListView.separated(
              itemCount: threads.length,
              separatorBuilder: (_, _) =>
                  const Divider(height: 1, color: AppColors.divider),
              itemBuilder: (context, i) => _ThreadRow(
                thread: threads[i],
                viewerId: me?.id ?? '',
              ),
            );
          },
        ),
      ),
    );
  }
}

class _ThreadRow extends ConsumerWidget {
  final MessageThreadSummary thread;
  final String viewerId;
  const _ThreadRow({required this.thread, required this.viewerId});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final other = thread.otherName(viewerId: viewerId);
    // Phase 29 · T2 — collapse the ListTile's leading + title + subtitle
    // + unread-dot enumeration into one screen-reader-friendly label.
    final srLabel = [
      'Conversation with $other',
      if (thread.hasUnreadForViewer) 'unread',
      if (thread.subject.isNotEmpty) 'about ${thread.subject}',
      'double-tap to open',
    ].join(', ');
    return Semantics(
      button: true,
      container: true,
      label: srLabel,
      excludeSemantics: true,
      child: ListTile(
      leading: CircleAvatar(
        backgroundColor: AppColors.primarySoft,
        child: Text(
          other.isEmpty ? '?' : other.trim().substring(0, 1).toUpperCase(),
          style: const TextStyle(
              color: AppColors.primaryDark, fontWeight: FontWeight.w800),
        ),
      ),
      title: Row(children: [
        Expanded(
          child: Text(other,
              style: AppTextStyles.body(context).copyWith(
                fontWeight: thread.hasUnreadForViewer
                    ? FontWeight.w800
                    : FontWeight.w600,
              )),
        ),
        if (thread.hasUnreadForViewer)
          Container(
            width: 8, height: 8,
            decoration: const BoxDecoration(
                shape: BoxShape.circle, color: AppColors.primary),
          ),
      ]),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(thread.subject,
              style: AppTextStyles.caption(context,
                      color: AppColors.textSecondary)
                  .copyWith(fontWeight: FontWeight.w600),
              maxLines: 1, overflow: TextOverflow.ellipsis),
          if (thread.lastMessagePreview.isNotEmpty)
            Text(thread.lastMessagePreview,
                style: AppTextStyles.caption(context,
                    color: AppColors.textMuted),
                maxLines: 1, overflow: TextOverflow.ellipsis),
        ],
      ),
      onTap: () async {
        await Navigator.of(context).push(fadeThroughRoute(
          ThreadChatScreen(threadId: thread.id),
        ));
        ref.invalidate(myThreadsProvider);
        ref.invalidate(myNotificationsProvider);
      },
      ),
    );
  }
}

class ThreadChatScreen extends ConsumerStatefulWidget {
  final String threadId;
  const ThreadChatScreen({super.key, required this.threadId});
  @override
  ConsumerState<ThreadChatScreen> createState() => _ThreadChatScreenState();
}

class _ThreadChatScreenState extends ConsumerState<ThreadChatScreen> {
  final _ctrl = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final body = _ctrl.text.trim();
    if (body.isEmpty || _sending) return;
    setState(() => _sending = true);
    try {
      await ApiService.instance.replyMessageThread(widget.threadId, body);
      _ctrl.clear();
      ref.invalidate(messageThreadProvider(widget.threadId));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(friendlyError(e))));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(messageThreadProvider(widget.threadId));
    final me = ref.watch(authProvider).user;
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: async.maybeWhen(
          data: (p) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(p.thread.otherName(viewerId: me?.id ?? ''),
                  style: AppTextStyles.h3(context)),
              Text(p.thread.subject,
                  style: AppTextStyles.caption(context,
                      color: AppColors.textMuted)),
            ],
          ),
          orElse: () => Text('Conversation', style: AppTextStyles.h2(context)),
        ),
      ),
      body: Column(children: [
        Expanded(
          child: async.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text(friendlyError(e))),
            data: (page) {
              if (page.messages.isEmpty) {
                return Center(
                  child: Text('No messages yet.',
                      style: AppTextStyles.body(context,
                          color: AppColors.textMuted)),
                );
              }
              return ListView.builder(
                padding: const EdgeInsets.all(AppSpacing.md),
                itemCount: page.messages.length,
                itemBuilder: (context, i) =>
                    _Bubble(m: page.messages[i], meId: me?.id ?? ''),
              );
            },
          ),
        ),
        SafeArea(
          child: Container(
            decoration: BoxDecoration(
              color: AppColors.surface,
              border: Border(top: BorderSide(color: AppColors.border)),
            ),
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md, vertical: AppSpacing.sm),
            child: Row(children: [
              Expanded(
                child: TextField(
                  controller: _ctrl,
                  minLines: 1,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    hintText: 'Type a message…',
                    isDense: true,
                    border: OutlineInputBorder(),
                  ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              IconButton.filled(
                onPressed: _sending ? null : _send,
                icon: _sending
                    ? const SizedBox(
                        height: 18, width: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          valueColor: AlwaysStoppedAnimation(Colors.white),
                        ),
                      )
                    : const Icon(Icons.send_rounded),
              ),
            ]),
          ),
        ),
      ]),
    );
  }
}

class _Bubble extends StatelessWidget {
  final DmMessage m;
  final String meId;
  const _Bubble({required this.m, required this.meId});
  @override
  Widget build(BuildContext context) {
    final mine = m.authorId == meId;
    final bg = mine ? AppColors.primary : AppColors.surface;
    final fg = mine ? Colors.white : AppColors.textPrimary;
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md, vertical: AppSpacing.sm),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        decoration: BoxDecoration(
          color: bg,
          border: mine ? null : Border.all(color: AppColors.border),
          borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (!mine && m.authorName != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Text(m.authorName!,
                    style: AppTextStyles.micro(context,
                            color: AppColors.textMuted)
                        .copyWith(fontWeight: FontWeight.w700)),
              ),
            Text(m.body, style: TextStyle(color: fg)),
            const SizedBox(height: 2),
            Text(_timeLabel(m.createdAt),
                style: TextStyle(
                    color: fg.withValues(alpha: 0.6),
                    fontSize: 10)),
          ],
        ),
      ),
    );
  }

  static String _timeLabel(DateTime? t) {
    if (t == null) return '';
    final hh = t.hour.toString().padLeft(2, '0');
    final mm = t.minute.toString().padLeft(2, '0');
    return '$hh:$mm';
  }
}
