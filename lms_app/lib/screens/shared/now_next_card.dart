import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/timetable.dart';
import '../../providers/timetable_provider.dart';
import '../../core/widgets/silent_error.dart';

/// Live "NOW · NEXT" card. Compact card meant to sit at the very top of
/// a home screen. Two lines: current period + upcoming period. Silent
/// when there's neither (weekend / no schedule yet).
class NowNextCard extends ConsumerWidget {
  const NowNextCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(nowNextProvider);
    return async.when(
      loading: () => const SizedBox.shrink(),
      // Phase 26 · T9 — SilentError so a Now/Next fetch failure
      // shows a retry chip instead of vanishing.
      error: (_, _) => SilentError(
        onRetry: () => ref.invalidate(nowNextProvider),
      ),
      data: (nn) {
        if (nn.now == null && nn.next == null) {
          return const SizedBox.shrink();
        }
        return Card(
          margin: const EdgeInsets.only(bottom: AppSpacing.md),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (nn.now != null) _NowRow(slot: nn.now!),
                if (nn.now != null && nn.next != null)
                  const Divider(height: AppSpacing.xl, color: AppColors.divider),
                if (nn.next != null) _NextRow(slot: nn.next!),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _NowRow extends StatelessWidget {
  final NowNextSlot slot;
  const _NowRow({required this.slot});
  @override
  Widget build(BuildContext context) {
    return _SlotRow(
      label: 'NOW',
      labelColor: AppColors.success,
      period: slot.period,
      tail: slot.endsInMinutes != null
          ? 'Ends in ${slot.endsInMinutes}m · ${slot.endsAt ?? ""}'
          : slot.endsAt != null
              ? 'Ends ${slot.endsAt}'
              : null,
      // Phase 27 — Join button when the live period has a Meet URL.
      showJoin: true,
    );
  }
}

class _NextRow extends StatelessWidget {
  final NowNextSlot slot;
  const _NextRow({required this.slot});
  @override
  Widget build(BuildContext context) {
    final tail = !slot.sameDay
        ? 'Tomorrow · ${slot.startsAt ?? ""}'
        : slot.startsInMinutes != null
            ? 'Starts in ${slot.startsInMinutes}m · ${slot.startsAt ?? ""}'
            : slot.startsAt != null
                ? 'Starts ${slot.startsAt}'
                : null;
    return _SlotRow(
      label: 'NEXT',
      labelColor: AppColors.primary,
      period: slot.period,
      tail: tail,
    );
  }
}

class _SlotRow extends StatelessWidget {
  final String label;
  final Color labelColor;
  final Period period;
  final String? tail;
  // Phase 27 — only the "NOW" row exposes the Join button; a "NEXT"
  // period isn't live yet, so jumping into its Meet room is premature.
  final bool showJoin;
  const _SlotRow({
    required this.label,
    required this.labelColor,
    required this.period,
    this.tail,
    this.showJoin = false,
  });

  @override
  Widget build(BuildContext context) {
    final title = period.course?.title
        ?? (period.isOverride ? (period.note ?? 'Custom event') : 'Free period');
    final sub = <String>[
      if (period.teacherName != null && period.teacherName!.isNotEmpty)
        period.teacherName!,
      if (period.className != null && period.className!.isNotEmpty)
        period.className!,
      if (period.room != null && period.room!.isNotEmpty) 'Room ${period.room}',
    ].join(' · ');

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: labelColor,
            borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
          ),
          child: Text(label,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 10,
                fontWeight: FontWeight.w800,
                letterSpacing: 0.8,
              )),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: AppTextStyles.bodyStrong(context)),
              if (sub.isNotEmpty)
                Text(sub,
                    style: AppTextStyles.micro(context, color: AppColors.textMuted)),
            ],
          ),
        ),
        if (tail != null)
          Padding(
            padding: const EdgeInsetsDirectional.only(start: AppSpacing.sm),
            child: Text(tail!,
                style: AppTextStyles.caption(context,
                    color: labelColor)),
          ),
        // Phase 27 — Join Meet/Zoom button for live periods with a URL.
        if (showJoin &&
            period.meetingUrl != null &&
            period.meetingUrl!.isNotEmpty)
          Padding(
            padding: const EdgeInsetsDirectional.only(start: AppSpacing.sm),
            child: FilledButton.icon(
              onPressed: () => launchUrl(
                Uri.parse(period.meetingUrl!),
                mode: LaunchMode.externalApplication,
              ),
              icon: const Icon(Icons.videocam_outlined, size: 16),
              label: const Text('Join'),
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.md, vertical: 4),
                minimumSize: const Size(0, 32),
                visualDensity: VisualDensity.compact,
              ),
            ),
          ),
      ],
    );
  }
}
