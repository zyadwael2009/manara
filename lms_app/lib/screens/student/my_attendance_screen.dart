import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../providers/attendance_provider.dart';
import '../shared/attendance_calendar.dart';

/// Student's own attendance history — read-only calendar view.
class MyAttendanceScreen extends ConsumerWidget {
  const MyAttendanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(myAttendanceProvider);
    return Scaffold(
      appBar: AppBar(title: Text('My attendance', style: AppTextStyles.h3(context))),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(myAttendanceProvider);
          await ref.read(myAttendanceProvider.future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(friendlyError(e))),
          ]),
          data: (marks) => marks.isEmpty
              ? ListView(children: const [
                  SizedBox(height: 80),
                  EmptyState(
                    icon: Icons.fact_check_outlined,
                    title: 'No attendance records yet',
                    message: 'Your homeroom teacher will start marking soon.',
                  ),
                ])
              : ListView(
                  padding: const EdgeInsets.all(AppSpacing.xl),
                  children: [
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(AppSpacing.lg),
                        child: AttendanceCalendar(marks: marks),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}
