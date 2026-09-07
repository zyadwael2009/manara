import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/widgets/silent_error.dart';
import '../../../models/announcement.dart';
import '../../../providers/announcements_provider.dart';

/// Phase 19 — top-of-home banner listing recent announcements for the
/// caller. Silent when the feed is empty.
///
/// Shows the top 3 items collapsed by default; a "See all" hooks into a
/// simple inline expander (avoids adding another route for a small list).
class AnnouncementsBanner extends ConsumerStatefulWidget {
  const AnnouncementsBanner({super.key});

  @override
  ConsumerState<AnnouncementsBanner> createState() =>
      _AnnouncementsBannerState();
}

class _AnnouncementsBannerState extends ConsumerState<AnnouncementsBanner> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(myAnnouncementsProvider);
    return async.when(
      loading: () => const SizedBox.shrink(),
      // Phase 26 · T9 — instead of dropping the banner silently, show
      // a tiny "couldn't load — tap to retry" chip so a real server
      // outage isn't indistinguishable from an empty feed.
      error: (_, _) => SilentError(
        onRetry: () => ref.invalidate(myAnnouncementsProvider),
      ),
      data: (rows) {
        if (rows.isEmpty) return const SizedBox.shrink();
        final visible = _expanded ? rows : rows.take(3).toList();
        return Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.lg),
          child: Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              side: const BorderSide(color: AppColors.border),
            ),
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    const Icon(Icons.campaign_outlined,
                        size: 16, color: AppColors.accent),
                    const SizedBox(width: AppSpacing.sm),
                    Text('ANNOUNCEMENTS',
                        style: AppTextStyles.micro(context,
                                color: AppColors.textMuted)
                            .copyWith(
                                fontWeight: FontWeight.w800,
                                letterSpacing: 0.8)),
                    const Spacer(),
                    if (rows.length > 3)
                      TextButton(
                        onPressed: () =>
                            setState(() => _expanded = !_expanded),
                        style: TextButton.styleFrom(
                          minimumSize: Size.zero,
                          padding: const EdgeInsets.symmetric(
                              horizontal: AppSpacing.sm, vertical: 2),
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ),
                        child: Text(_expanded
                            ? 'Show less'
                            : 'See all ${rows.length}'),
                      ),
                  ]),
                  const SizedBox(height: AppSpacing.sm),
                  for (final a in visible) _Row(announcement: a),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class _Row extends StatelessWidget {
  final Announcement announcement;
  const _Row({required this.announcement});

  @override
  Widget build(BuildContext context) {
    final a = announcement;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _AudienceChip(announcement: a),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(a.title,
                    style: AppTextStyles.body(context)
                        .copyWith(fontWeight: FontWeight.w700)),
                if (a.body.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(a.body,
                      style: AppTextStyles.caption(context,
                          color: AppColors.textSecondary)),
                ],
                const SizedBox(height: 2),
                Text(
                    '${a.authorName ?? "Staff"} · ${_ago(a.createdAt)}',
                    style: AppTextStyles.micro(context,
                        color: AppColors.textMuted)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String _ago(DateTime? t) {
    if (t == null) return '';
    final d = DateTime.now().difference(t);
    if (d.inMinutes < 1) return 'just now';
    if (d.inHours < 1) return '${d.inMinutes}m ago';
    if (d.inDays < 1) return '${d.inHours}h ago';
    if (d.inDays < 7) return '${d.inDays}d ago';
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return '${t.day} ${months[t.month - 1]}';
  }
}

class _AudienceChip extends StatelessWidget {
  final Announcement announcement;
  const _AudienceChip({required this.announcement});
  @override
  Widget build(BuildContext context) {
    late Color bg;
    late Color fg;
    late IconData icon;
    switch (announcement.audience) {
      case 'school':
        bg = AppColors.dangerSoft;
        fg = AppColors.danger;
        icon = Icons.school_outlined;
        break;
      case 'class':
        bg = AppColors.primarySoft;
        fg = AppColors.primaryDark;
        icon = Icons.groups_outlined;
        break;
      case 'course':
      default:
        bg = AppColors.successSoft;
        fg = AppColors.success;
        icon = Icons.book_outlined;
        break;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 11, color: fg),
        const SizedBox(width: 3),
        Text(announcement.audienceLabel,
            style: TextStyle(
                color: fg, fontWeight: FontWeight.w700, fontSize: 10)),
      ]),
    );
  }
}
