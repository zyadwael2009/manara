import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../services/api_service.dart';

/// Phase 25 — "Subscribe to calendar" bottom-sheet. Shown from the
/// student's My timetable + the teacher's My teaching screens.
///
/// Copy button copies the raw URL; the ICS launcher opens the URL
/// (some OSes handle `webcal://` specifically, but plain https also
/// works — Google Calendar / Apple Calendar / Outlook all accept it).
class CalendarSubscribeSheet extends ConsumerStatefulWidget {
  const CalendarSubscribeSheet({super.key});

  static Future<void> open(BuildContext context) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: const CalendarSubscribeSheet(),
      ),
    );
  }

  @override
  ConsumerState<CalendarSubscribeSheet> createState() =>
      _CalendarSubscribeSheetState();
}

class _CalendarSubscribeSheetState
    extends ConsumerState<CalendarSubscribeSheet> {
  String? _url;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _fetch();
  }

  Future<void> _fetch() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await ApiService.instance.getCalendarToken();
      if (!mounted) return;
      setState(() {
        _url = data['url'] as String?;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = friendlyError(e);
        _loading = false;
      });
    }
  }

  Future<void> _rotate() async {
    setState(() => _loading = true);
    try {
      final data = await ApiService.instance.rotateCalendarToken();
      if (!mounted) return;
      setState(() {
        _url = data['url'] as String?;
        _loading = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('New link generated; old subscribers stop syncing.')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = friendlyError(e);
        _loading = false;
      });
    }
  }

  Future<void> _revoke() async {
    setState(() => _loading = true);
    try {
      await ApiService.instance.revokeCalendarToken();
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Calendar link revoked.')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = friendlyError(e);
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
            AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xl),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Row(children: [
            const Icon(Icons.calendar_month_outlined, color: AppColors.accent),
            const SizedBox(width: AppSpacing.sm),
            Text('Subscribe to calendar',
                style: AppTextStyles.h3(context)
                    .copyWith(fontWeight: FontWeight.w800)),
            const Spacer(),
            IconButton(
              tooltip: 'Close',
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.close_rounded),
            ),
          ]),
          const SizedBox(height: AppSpacing.md),
          Text(
            'Copy the link and paste it into Google Calendar → Other calendars → '
            'From URL (or Apple Calendar → File → New Calendar Subscription). '
            'It stays in sync as your schedule changes.',
            style: AppTextStyles.caption(context, color: AppColors.textSecondary),
          ),
          const SizedBox(height: AppSpacing.md),
          if (_loading) const Center(child: CircularProgressIndicator())
          else if (_error != null)
            Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: AppColors.dangerSoft,
                borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              ),
              child: Text(_error!,
                  style: AppTextStyles.body(context, color: AppColors.danger)),
            )
          else ...[
            Container(
              padding: const EdgeInsets.all(AppSpacing.md),
              decoration: BoxDecoration(
                color: AppColors.surfaceMuted,
                borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                border: Border.all(color: AppColors.border),
              ),
              child: Row(children: [
                Expanded(
                  child: SelectableText(_url ?? '',
                      style: const TextStyle(
                          fontFamily: 'monospace', fontSize: 12)),
                ),
                IconButton(
                  tooltip: 'Copy link',
                  icon: const Icon(Icons.copy_all_rounded),
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: _url ?? ''));
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Link copied.')),
                    );
                  },
                ),
                IconButton(
                  tooltip: 'Open in browser',
                  icon: const Icon(Icons.open_in_new_rounded),
                  onPressed: () async {
                    if (_url != null) {
                      await launchUrl(Uri.parse(_url!),
                          mode: LaunchMode.platformDefault);
                    }
                  },
                ),
              ]),
            ),
            const SizedBox(height: AppSpacing.md),
            Row(children: [
              OutlinedButton.icon(
                onPressed: _rotate,
                icon: const Icon(Icons.refresh_rounded),
                label: const Text('Rotate link'),
              ),
              const SizedBox(width: AppSpacing.sm),
              TextButton.icon(
                onPressed: _revoke,
                icon: const Icon(Icons.link_off_rounded,
                    color: AppColors.danger),
                label: const Text('Revoke',
                    style: TextStyle(color: AppColors.danger)),
              ),
            ]),
          ],
        ]),
      ),
    );
  }
}
