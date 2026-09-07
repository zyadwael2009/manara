import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/utils/transitions.dart';
import '../../providers/auth_provider.dart';
import '../../providers/comm_providers.dart';
import '../../providers/courses_provider.dart';
import '../../providers/school_providers.dart';
import '../../services/api_service.dart';
import '../admin/class_detail_screen.dart';
import '../catalog/course_detail_screen.dart';
import '../shared/announcement_composer_sheet.dart';
import '../shared/inbox_screen.dart';
import '../shared/notifications_bell.dart';
import '../shared/now_next_card.dart';
import '../shared/search_screen.dart';
import 'attendance_take_screen.dart';
import 'instructor_dashboard_screen.dart';
import 'my_teaching_screen.dart';
import '../../core/widgets/account_menu.dart';
import '../../core/widgets/trailing_chevron.dart';

class TeacherHomeScreen extends ConsumerStatefulWidget {
  const TeacherHomeScreen({super.key});
  @override
  ConsumerState<TeacherHomeScreen> createState() => _TeacherHomeScreenState();
}

class _TeacherHomeScreenState extends ConsumerState<TeacherHomeScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(myCoursesProvider.notifier).refresh();
    });
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider).user;
    final myCoursesState = ref.watch(myCoursesProvider);
    final classesAsync = ref.watch(classesProvider(null));

    // Which class does the current user homeroom (if any)?
    final myHomeroom = classesAsync.value?.where((c) => c.homeroomTeacherId == user?.id).firstOrNull;

    return Scaffold(
      appBar: AppBar(
        title: Text('Teacher home', style: AppTextStyles.h2(context)),
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
      // Phase 19 — quick way to broadcast to your class / a course you
      // teach. The sheet auto-limits what audiences are available based
      // on the caller's role.
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => AnnouncementComposerSheet.open(context),
        icon: const Icon(Icons.campaign_outlined),
        label: const Text('Announce'),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(classesProvider);
          await ref.read(myCoursesProvider.notifier).refresh();
        },
        child: ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: [
          // Phase 13: live Now/Next indicator at the very top — the first
          // thing a teacher wants to see on opening the app.
          const NowNextCard(),
          // Phase 7: dashboard entry — primary-tinted card at the very top
          // so it reads as the first thing an instructor sees each session.
          Card(
            color: AppColors.primary,
            child: InkWell(
              borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              onTap: () {
                Navigator.of(context).push(
                  fadeThroughRoute(const InstructorDashboardScreen()),
                );
              },
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Row(children: [
                  const Icon(Icons.insights_rounded, color: Colors.white, size: 28),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Dashboard',
                            style: AppTextStyles.h3(context,
                                color: Colors.white)),
                        const SizedBox(height: 2),
                        Text('Enrollments, completion, quiz pass rate',
                            style: TextStyle(
                                color: Colors.white70, fontSize: 12)),
                      ],
                    ),
                  ),
                  const TrailingChevron(color: Colors.white70),
                ]),
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
          Text('MY HOMEROOM',
              style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
          const SizedBox(height: AppSpacing.sm),
          if (myHomeroom == null)
            _EmptyPanel(text: 'You are not the homeroom teacher for any class.')
          else ...[
            // Phase 12: primary attendance CTA — the fast morning flow.
            Card(
              color: AppColors.accent,
              child: InkWell(
                borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                onTap: () {
                  Navigator.of(context).push(
                    fadeThroughRoute(AttendanceTakeScreen(
                      classId: myHomeroom.id,
                      className: myHomeroom.name,
                    )),
                  );
                },
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  child: Row(children: [
                    const Icon(Icons.fact_check_rounded,
                        color: Colors.white, size: 28),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text("Take today's attendance",
                              style: AppTextStyles.h3(context,
                                  color: Colors.white)),
                          const SizedBox(height: 2),
                          Text('Mark ${myHomeroom.name} present, absent, late, or excused',
                              style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.85),
                                  fontSize: 12)),
                        ],
                      ),
                    ),
                    const TrailingChevron(color: Colors.white),
                  ]),
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            Card(
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: AppColors.primary,
                  child: Text(
                    myHomeroom.name.isNotEmpty ? myHomeroom.name[0] : '?',
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
                  ),
                ),
                title: Text(myHomeroom.name, style: AppTextStyles.bodyStrong(context)),
                subtitle: Text(
                  '${myHomeroom.gradeName ?? "no grade"} · ${myHomeroom.studentCount} students',
                  style: AppTextStyles.caption(context),
                ),
                trailing: const TrailingChevron(),
                onTap: () {
                  Navigator.of(context).push(
                    fadeThroughRoute(ClassDetailScreen(classId: myHomeroom.id)),
                  );
                },
              ),
            ),
          ],
          if (myHomeroom != null) ...[
            const SizedBox(height: AppSpacing.md),
            // Phase 21 — inline homework composer for the homeroom.
            _HomeworkComposerCard(
              classId: myHomeroom.id, className: myHomeroom.name,
            ),
          ],
          const SizedBox(height: AppSpacing.xl),
          Text('MY SUBJECTS',
              style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
          const SizedBox(height: AppSpacing.sm),
          if (myCoursesState.loading && myCoursesState.courses.isEmpty)
            const Center(child: Padding(
              padding: EdgeInsets.all(AppSpacing.xl),
              child: CircularProgressIndicator(),
            ))
          else if (myCoursesState.courses.isEmpty)
            _EmptyPanel(text: 'No subject assigned to you yet.')
          else
            for (final c in myCoursesState.courses)
              Card(
                child: ListTile(
                  title: Text(c.title, style: AppTextStyles.bodyStrong(context)),
                  subtitle: Text(
                    '${c.gradeName ?? ""} · ${c.category}',
                    style: AppTextStyles.caption(context),
                  ),
                  trailing: const TrailingChevron(),
                  onTap: () {
                    Navigator.of(context).push(
                      fadeThroughRoute(CourseDetailScreen(courseId: c.id)),
                    );
                  },
                ),
              ),
          const SizedBox(height: AppSpacing.xl),
          Text('MY TEACHING SCHEDULE',
              style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
          const SizedBox(height: AppSpacing.sm),
          Card(
            child: ListTile(
              leading: const Icon(Icons.event_note_rounded, color: AppColors.primary),
              title: Text('Weekly timetable',
                  style: AppTextStyles.bodyStrong(context)),
              subtitle: Text('Every class you teach, on one grid.',
                  style: AppTextStyles.caption(context)),
              trailing: const TrailingChevron(),
              onTap: () {
                Navigator.of(context).push(
                  fadeThroughRoute(const MyTeachingScreen()),
                );
              },
            ),
          ),
          const SizedBox(height: AppSpacing.xl),
          Text('MY LEADERSHIP',
              style: AppTextStyles.micro(context, color: AppColors.textSecondary)),
          const SizedBox(height: AppSpacing.sm),
          _EmptyPanel(
              text:
                  'Department-leader assignments live on the admin console. Ask your school office if you should be listed there.'),
        ]),
      ),
    );
  }
}

class _EmptyPanel extends StatelessWidget {
  final String text;
  const _EmptyPanel({required this.text});
  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Center(
            child: Text(text, style: AppTextStyles.caption(context), textAlign: TextAlign.center)),
      ),
    );
  }
}

// ============================================================================
// Phase 21 — inline homework composer for the teacher's homeroom.
//
// One-post-per-day model (server unique on class_id + date). If today's
// post exists we prefill the fields, PUT re-writes it. First post pings
// the whole class's bell + linked parents; edits do not (see server).
// ============================================================================
class _HomeworkComposerCard extends ConsumerStatefulWidget {
  final String classId;
  final String className;
  const _HomeworkComposerCard({required this.classId, required this.className});
  @override
  ConsumerState<_HomeworkComposerCard> createState() =>
      _HomeworkComposerCardState();
}

class _HomeworkComposerCardState
    extends ConsumerState<_HomeworkComposerCard> {
  final _title = TextEditingController();
  final _body = TextEditingController();
  bool _saving = false;
  bool _seededFromExisting = false;

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_title.text.trim().isEmpty || _saving) return;
    setState(() => _saving = true);
    try {
      await ApiService.instance.upsertHomework(
        classId: widget.classId,
        date: DateTime.now(),
        title: _title.text.trim(),
        body: _body.text.trim(),
      );
      ref.invalidate(classHomeworkProvider(widget.classId));
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Homework posted.')));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(friendlyError(e))));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(classHomeworkProvider(widget.classId));
    // Prefill with today's existing post (once, so the teacher can keep typing).
    async.whenData((rows) {
      final today = DateTime.now();
      final match = rows.where((r) =>
          r.date.year == today.year &&
          r.date.month == today.month &&
          r.date.day == today.day).toList();
      if (match.isNotEmpty && !_seededFromExisting) {
        _title.text = match.first.title;
        _body.text = match.first.body;
        _seededFromExisting = true;
      }
    });
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
        side: const BorderSide(color: AppColors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(children: [
              const Icon(Icons.edit_note_rounded, color: AppColors.accent),
              const SizedBox(width: AppSpacing.sm),
              Text('Today’s homework for ${widget.className}',
                  style: AppTextStyles.bodyStrong(context)),
            ]),
            const SizedBox(height: AppSpacing.md),
            TextField(
              controller: _title,
              maxLength: 200,
              decoration: const InputDecoration(
                labelText: 'Title',
                border: OutlineInputBorder(),
                isDense: true,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            TextField(
              controller: _body,
              minLines: 2, maxLines: 5, maxLength: 5000,
              decoration: const InputDecoration(
                labelText: 'Details (optional)',
                border: OutlineInputBorder(),
                alignLabelWithHint: true,
                isDense: true,
              ),
            ),
            const SizedBox(height: AppSpacing.sm),
            SizedBox(
              height: 44,
              child: ElevatedButton.icon(
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox(
                        height: 18, width: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          valueColor: AlwaysStoppedAnimation(Colors.white),
                        ),
                      )
                    : const Icon(Icons.send_rounded),
                label: Text(_saving ? 'Posting…' : 'Post to class'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
