import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/widgets/empty_state.dart';
import '../../providers/timetable_provider.dart';
import '../shared/calendar_subscribe_sheet.dart';
import '../shared/now_next_card.dart';
import '../shared/weekly_timetable_grid.dart';

/// Teacher's aggregated weekly view — every period across every class
/// they teach. Cells show className since the teacher spans multiple
/// classes.
class MyTeachingScreen extends ConsumerWidget {
  const MyTeachingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(myTimetableProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text('My teaching', style: AppTextStyles.h3(context)),
        actions: [
          IconButton(
            tooltip: 'Subscribe to calendar',
            icon: const Icon(Icons.calendar_month_outlined),
            onPressed: () => CalendarSubscribeSheet.open(context),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(myTimetableProvider);
          ref.invalidate(nowNextProvider);
          await ref.read(myTimetableProvider.future);
        },
        child: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ListView(children: [
            const SizedBox(height: 80),
            Center(child: Text(friendlyError(e))),
          ]),
          data: (week) => week.periods.isEmpty
              ? ListView(children: const [
                  SizedBox(height: 80),
                  EmptyState(
                    icon: Icons.event_note_outlined,
                    title: 'No teaching timetable yet',
                    message: 'The school office hasn\'t scheduled your classes yet.',
                  ),
                ])
              : ListView(
                  padding: const EdgeInsets.all(AppSpacing.xl),
                  children: [
                    const NowNextCard(),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(AppSpacing.md),
                        child: WeeklyTimetableGrid(
                          week: week,
                          showClassName: true,
                        ),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}
