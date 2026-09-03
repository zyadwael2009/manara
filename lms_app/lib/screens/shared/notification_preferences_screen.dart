import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../services/api_service.dart';

/// Phase 32 · T1 — one screen per user for per-kind notification opt-outs.
///
/// Fetches the current preferences on init, renders one SwitchListTile
/// per kind, and pushes updates on toggle (optimistic — reverts on
/// server error).
class NotificationPreferencesScreen extends ConsumerStatefulWidget {
  const NotificationPreferencesScreen({super.key});
  @override
  ConsumerState<NotificationPreferencesScreen> createState() =>
      _NotificationPreferencesScreenState();
}

class _NotificationPreferencesScreenState
    extends ConsumerState<NotificationPreferencesScreen> {
  Future<({List<String> kinds, Map<String, bool> preferences})>? _future;
  Map<String, bool> _prefs = {};

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<({List<String> kinds, Map<String, bool> preferences})>
      _load() async {
    final data = await ApiService.instance.getNotificationPreferences();
    setState(() => _prefs = Map<String, bool>.from(data.preferences));
    return data;
  }

  Future<void> _toggle(String kind, bool value) async {
    final prev = _prefs[kind] ?? true;
    setState(() => _prefs[kind] = value);
    try {
      final data = await ApiService.instance
          .updateNotificationPreferences({kind: value});
      setState(() => _prefs = Map<String, bool>.from(data.preferences));
    } on ApiException catch (e) {
      // Optimistic revert.
      setState(() => _prefs[kind] = prev);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(friendlyError(e))));
      }
    }
  }

  // Human labels for the machine kind slugs — matches the server's
  // `NOTIFICATION_KINDS` set.
  static const _labels = {
    'grade_posted': 'Grades posted',
    'assignment_graded': 'Assignment feedback',
    'fee_created': 'New fee added',
    'fee_payment': 'Fee payment recorded',
    'fee_overdue': 'Fee overdue reminder',
    'announcement': 'School / class announcements',
    'message': 'Direct messages',
    'quiz_due': 'Quiz due soon',
    'attendance_absent': 'Absence marked',
    'streak_reminder': 'Streak reminder',
    'cert_issued': 'Certificate earned',
  };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title:
            Text('Notification preferences', style: AppTextStyles.h3(context)),
      ),
      body: FutureBuilder(
        future: _future,
        builder: (context, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text(friendlyError(snap.error!)));
          }
          final kinds = snap.data!.kinds;
          return ListView(
            children: [
              const Padding(
                padding: EdgeInsets.all(AppSpacing.lg),
                child: Text(
                  'Turn any category off to stop the bell + push for it. '
                  'Grade + fee history stays visible in-app either way.',
                ),
              ),
              for (final k in kinds)
                SwitchListTile(
                  title: Text(_labels[k] ?? k,
                      style: AppTextStyles.body(context)),
                  subtitle: Text(k,
                      style: AppTextStyles.caption(context,
                          color: AppColors.textMuted)),
                  value: _prefs[k] ?? true,
                  onChanged: (v) => _toggle(k, v),
                ),
            ],
          );
        },
      ),
    );
  }
}
