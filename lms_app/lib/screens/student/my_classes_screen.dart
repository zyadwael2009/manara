import 'package:cached_network_image/cached_network_image.dart';
import 'package:confetti/confetti.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/category_palette.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/transitions.dart';
import '../../core/widgets/account_menu.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/progress_ring.dart';
import '../../core/widgets/skeleton_loader.dart';
import '../../core/widgets/warning_tile.dart';
import '../../models/enrollment.dart';
import '../../providers/attendance_provider.dart';
import '../../providers/auth_provider.dart';
import '../../providers/enrollments_provider.dart';
import '../../providers/gamify_providers.dart';
import '../../services/api_service.dart';
import '../catalog/course_detail_screen.dart';
import '../shared/notification_preferences_screen.dart';
import '../shared/notifications_bell.dart';
import '../shared/now_next_card.dart';
import '../shared/search_screen.dart';
import '../shared/student_fees_screen.dart';
import 'my_diploma_screen.dart';
import 'standards_mastery_screen.dart';
import 'widgets/announcements_banner.dart';
import 'widgets/fees_due_chip.dart';
import 'widgets/homework_strip.dart';
import 'widgets/today_card.dart';
import 'certificate_screen.dart';
import 'my_assignments_screen.dart';
import 'my_attendance_screen.dart';
import 'my_calendar_screen.dart';
import 'my_quizzes_screen.dart';
import 'my_timetable_screen.dart';
import 'widgets/streak_card.dart';
import 'report_card_screen.dart';

/// Student home — matches the mockup's Section 5 shape:
/// subtitle line with class + grade, pending-electives banner,
/// 2-column grid of course cards each with a gradient thumbnail and
/// a progress ring.
class MyClassesScreen extends ConsumerStatefulWidget {
  const MyClassesScreen({super.key});

  @override
  ConsumerState<MyClassesScreen> createState() => _MyClassesScreenState();
}

class _MyClassesScreenState extends ConsumerState<MyClassesScreen> {
  late final ConfettiController _confetti;
  final Set<String> _seenCertIds = {};
  bool _seenFirstLoad = false;

  @override
  void initState() {
    super.initState();
    _confetti = ConfettiController(duration: const Duration(seconds: 2));
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _refresh();
      // Phase 24 — tick the daily streak. Same-day repeats are a no-op
      // on the server so this is safe every time the screen builds.
      try {
        await ApiService.instance.tickStreak();
        ref.invalidate(myStreakProvider);
        ref.invalidate(myBadgesProvider);
      } catch (_) {
        // Silent — the streak card handles error/loading states.
      }
    });
  }

  @override
  void dispose() {
    _confetti.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    final userId = ref.read(authProvider).user?.id;
    await ref.read(myEnrollmentsProvider.notifier).refresh(currentUserId: userId);
  }

  void _maybeFireConfetti(List<dynamic> enrollments) {
    final currentIds = <String>{};
    for (final e in enrollments) {
      final cert = e.certificate;
      if (cert != null && !cert.revoked) currentIds.add(cert.id as String);
    }
    if (!_seenFirstLoad) {
      // Prime the "seen" set on first load — we don't want to fire confetti
      // for every already-issued cert on the very first render.
      _seenCertIds.addAll(currentIds);
      _seenFirstLoad = true;
      return;
    }
    final fresh = currentIds.difference(_seenCertIds);
    if (fresh.isNotEmpty) {
      _confetti.play();
    }
    _seenCertIds
      ..clear()
      ..addAll(currentIds);
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final state = ref.watch(myEnrollmentsProvider);
    final user = auth.user;

    // Detect newly-issued certs between renders.
    _maybeFireConfetti(state.active);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text('My classes', style: AppTextStyles.h2(context)),
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
            tooltip: 'Calendar',
            icon: const Icon(Icons.calendar_month_outlined),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MyCalendarScreen()),
              );
            },
          ),
          IconButton(
            tooltip: 'Timetable',
            icon: const Icon(Icons.event_note_outlined),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MyTimetableScreen()),
              );
            },
          ),
          IconButton(
            tooltip: 'Attendance',
            icon: const Icon(Icons.fact_check_outlined),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MyAttendanceScreen()),
              );
            },
          ),
          // Phase 28 — student sees their own fees (read-only). The
          // shared StudentFeesScreen powers this + the parent-view path.
          IconButton(
            tooltip: 'My fees',
            icon: const Icon(Icons.receipt_long_outlined),
            onPressed: () {
              Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => const StudentFeesScreen(),
              ));
            },
          ),
          // Phase 32 — overflow menu for the newer surfaces so the
          // AppBar doesn't grow past a comfortable count.
          PopupMenuButton<String>(
            tooltip: 'More',
            icon: const Icon(Icons.more_vert_rounded),
            onSelected: (value) {
              switch (value) {
                case 'diploma':
                  Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const DiplomaScreen(),
                  ));
                  break;
                case 'standards':
                  Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const StandardsMasteryScreen(),
                  ));
                  break;
                case 'notif_prefs':
                  Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const NotificationPreferencesScreen(),
                  ));
                  break;
              }
            },
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'diploma', child: Text('My diploma')),
              PopupMenuItem(
                  value: 'standards', child: Text('Standards mastery')),
              PopupMenuItem(
                  value: 'notif_prefs',
                  child: Text('Notification preferences')),
            ],
          ),
          IconButton(
            tooltip: 'Quizzes',
            icon: const Icon(Icons.quiz_outlined),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MyQuizzesScreen()),
              );
            },
          ),
          IconButton(
            tooltip: 'Assignments',
            icon: const Icon(Icons.assignment_outlined),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const MyAssignmentsScreen()),
              );
            },
          ),
          IconButton(
            tooltip: 'Report card',
            icon: const Icon(Icons.assessment_outlined),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const ReportCardScreen()),
              );
            },
          ),
          if (user != null) const AccountMenu(),
        ],
      ),
      body: Stack(children: [
        RefreshIndicator(
          onRefresh: _refresh,
          child: _Body(
            state: state,
            subtitle: user == null
                ? ''
                : '${user.name}${user.className != null ? " · ${user.gradeName ?? ""} ${user.className}" : ""}',
          ),
        ),
        // Center-top confetti overlay. Wide angle + gentle gravity.
        Align(
          alignment: Alignment.topCenter,
          child: ConfettiWidget(
            confettiController: _confetti,
            blastDirectionality: BlastDirectionality.explosive,
            shouldLoop: false,
            emissionFrequency: 0.03,
            numberOfParticles: 24,
            maxBlastForce: 15,
            minBlastForce: 6,
            gravity: 0.3,
            colors: const [
              AppColors.primary,
              AppColors.accent,
              AppColors.success,
              Colors.white,
            ],
          ),
        ),
      ]),
    );
  }
}

class _Body extends StatelessWidget {
  final MyEnrollmentsState state;
  final String subtitle;
  const _Body({required this.state, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    if (state.loading && state.enrollments.isEmpty) {
      return ListView(padding: const EdgeInsets.all(AppSpacing.xl), children: const [
        SkeletonCourseCard(),
        SizedBox(height: AppSpacing.lg),
        SkeletonCourseCard(),
      ]);
    }
    if (state.error != null && state.enrollments.isEmpty) {
      return EmptyState(
        icon: Icons.error_outline_rounded,
        title: 'Could not load your classes',
        message: state.error!,
      );
    }
    final active = state.active;
    if (active.isEmpty && state.pendingElectives.isEmpty) {
      return const EmptyState(
        icon: Icons.school_outlined,
        title: 'No classes yet',
        message:
            "You haven't been placed in a class yet. Your teachers or the school office will add you.",
      );
    }

    // Find the highest-recency active enrollment for the "Continue" band.
    Enrollment? continueEnrollment;
    if (active.isNotEmpty) {
      continueEnrollment = active.first;
      for (final e in active) {
        if ((e.enrolledAt ?? DateTime(1970))
            .isAfter(continueEnrollment!.enrolledAt ?? DateTime(1970))) {
          continueEnrollment = e;
        }
      }
    }

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.xl),
      children: [
        if (subtitle.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.md),
            child: Text(subtitle, style: AppTextStyles.caption(context)),
          ),
        // Phase 19: audience-scoped announcements (school/class/course).
        // Silent when the feed is empty.
        const AnnouncementsBanner(),
        // Phase 24: streak flame + earned-badge count. Tap → full grid.
        const StreakCard(),
        // Phase 21: today's homework post from the homeroom teacher.
        const HomeworkStrip(),
        // Phase 18: "Today" strip — periods coming up + assignments due
        // today + open quizzes. Silent when there's nothing worth showing.
        const TodayCard(),
        // Phase 13: Now/Next indicator at the top.
        const NowNextCard(),
        // Phase 30 · T2: outstanding fees chip (silent when zero).
        const FeesDueChip(),
        if (state.pendingElectives.isNotEmpty) ...[
          _PendingBanner(pending: state.pendingElectives),
          const SizedBox(height: AppSpacing.lg),
        ],
        if (continueEnrollment != null) ...[
          Text('CONTINUE WHERE YOU LEFT OFF',
              style: AppTextStyles.micro(context, color: AppColors.textMuted)),
          const SizedBox(height: AppSpacing.sm),
          _ContinueBand(enrollment: continueEnrollment),
          const SizedBox(height: AppSpacing.xl),
        ],
        if (active.isNotEmpty) ...[
          Text('THIS TERM · ${active.length} COURSES',
              style: AppTextStyles.micro(context, color: AppColors.textMuted)),
          const SizedBox(height: AppSpacing.sm),
          LayoutBuilder(builder: (context, box) {
            // 2 columns on narrow, 3 on wider surfaces (tablet/web).
            final cols = box.maxWidth > 720 ? 3 : 2;
            return GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: active.length,
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: cols,
                childAspectRatio: 0.78,
                crossAxisSpacing: AppSpacing.md,
                mainAxisSpacing: AppSpacing.md,
              ),
              itemBuilder: (context, i) => _ClassGridCard(enrollment: active[i]),
            );
          }),
        ],
      ],
    );
  }
}

// ============================================================================
// Pending banner
// ============================================================================
class _PendingBanner extends StatelessWidget {
  final List<PendingElective> pending;
  const _PendingBanner({required this.pending});

  @override
  Widget build(BuildContext context) {
    final group = pending.first.group;
    final options = pending.first.options.map((o) => o.title).join(' or ');
    final many = pending.length > 1;
    // Phase 26 · T8 — canonical WarningTile so the pending-electives
    // banner reads with the same tone as every other warn tile.
    return WarningTile(
      title: many
          ? '${pending.length} elective classes still pending'
          : 'Your ${AppConstants.prettyElectiveGroup(group).toLowerCase()} class is pending',
      message: many
          ? 'The school office will pick them for you soon.'
          : "The school office will pick $options for you soon.",
    );
  }
}

// ============================================================================
// Continue band — horizontal card
// ============================================================================
class _ContinueBand extends StatelessWidget {
  final Enrollment enrollment;
  const _ContinueBand({required this.enrollment});

  @override
  Widget build(BuildContext context) {
    final course = enrollment.course;
    if (course == null) return const SizedBox.shrink();
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          Navigator.of(context).push(
            heroRoute(CourseDetailScreen(courseId: course.id)),
          );
        },
        borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.md),
            child: Row(children: [
              _CategoryGlyph(
                category: course.category,
                url: course.thumbnailUrl,
                size: 64,
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(course.title, style: AppTextStyles.bodyStrong(context)),
                    const SizedBox(height: 2),
                    Text(
                      AppConstants.prettyCategory(course.category),
                      style: AppTextStyles.caption(context),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
                      child: LinearProgressIndicator(
                        value: (enrollment.progressPercent.clamp(0, 100)) / 100,
                        backgroundColor: AppColors.surfaceMuted,
                        color: AppColors.primary,
                        minHeight: 6,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: AppColors.primary,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                ),
                child: const Icon(Icons.play_arrow_rounded, color: Colors.white),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

// ============================================================================
// Grid card — mockup §5 shape
// ============================================================================
class _ClassGridCard extends ConsumerWidget {
  final Enrollment enrollment;
  const _ClassGridCard({required this.enrollment});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final course = enrollment.course;
    if (course == null) return const SizedBox.shrink();
    // Phase 29 · T2 — a screen reader would otherwise enumerate every
    // Text/Icon inside the card. `container: true` collapses those
    // children into one node; `button: true` announces the tap
    // affordance; the label carries the actionable summary.
    return Semantics(
      button: true,
      container: true,
      label: 'Class ${course.title}, '
          '${enrollment.progressPercent}% complete, double-tap to open',
      excludeSemantics: true,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () {
            Navigator.of(context).push(
              heroRoute(CourseDetailScreen(courseId: course.id)),
            );
          },
          borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
          child: Card(
            clipBehavior: Clip.antiAlias,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Stack(children: [
              AspectRatio(
                aspectRatio: 16 / 9,
                child: _CategoryGlyph(
                  category: course.category,
                  url: course.thumbnailUrl,
                  filled: true,
                ),
              ),
              if (enrollment.certificate != null && !enrollment.certificate!.revoked)
                Positioned(
                  top: 8, right: 8,
                  child: _CertBadge(
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => CertificateScreen(
                            certificateId: enrollment.certificate!.id,
                          ),
                        ),
                      );
                    },
                  ),
                ),
            ]),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Expanded(
                      child: Text(
                        course.title,
                        style: AppTextStyles.bodyStrong(context),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (enrollment.cachedLetter != null)
                      _MiniLetterPill(letter: enrollment.cachedLetter!),
                  ]),
                  const SizedBox(height: AppSpacing.sm),
                  Row(children: [
                    ProgressRing(percent: enrollment.progressPercent.toDouble(), size: 36),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Text(
                        AppConstants.prettyCategory(course.category),
                        style: AppTextStyles.caption(context),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    // Phase 18 — attendance chip. Shared across cards
                    // (attendance is class-level, same value for all).
                    _AttendanceChip(),
                  ]),
                ],
              ),
            ),
          ]),
          ),
        ),
      ),
    );
  }
}

// ============================================================================
// Gradient glyph — reused by the Continue band and the grid cards
// ============================================================================
class _CategoryGlyph extends StatelessWidget {
  final String category;
  final String? url;
  final double? size;
  final bool filled;
  const _CategoryGlyph({
    required this.category,
    this.url,
    this.size,
    this.filled = false,
  });

  @override
  Widget build(BuildContext context) {
    // Phase 26 · T1 — moved to shared `CategoryPalette` in
    // `core/theme/category_palette.dart` so the same swatches drive
    // the timetable grid + report card etc.
    final palette = CategoryPalette.forCategory(category);
    final colors = [palette.gradientTop, palette.gradientBottom];
    final icon = palette.icon;
    final glyphSize = filled ? 42.0 : (size ?? 56) * 0.5;
    final container = Container(
      width: filled ? null : (size ?? 56),
      height: filled ? null : (size ?? 56),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: colors,
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: filled ? null : BorderRadius.circular(AppSpacing.radiusMd),
      ),
      child: (url != null && url!.isNotEmpty)
          ? ClipRRect(
              borderRadius:
                  filled ? BorderRadius.zero : BorderRadius.circular(AppSpacing.radiusMd),
              child: CachedNetworkImage(
                imageUrl: AppConstants.resolveMediaUrl(url!),
                fit: BoxFit.cover,
                errorWidget: (_, _, _) => Center(
                  child: Icon(icon, color: Colors.white.withValues(alpha: 0.75), size: glyphSize),
                ),
              ),
            )
          : Center(
              child: Icon(icon, color: Colors.white.withValues(alpha: 0.75), size: glyphSize),
            ),
    );
    return container;
  }
}

class _CertBadge extends StatelessWidget {
  final VoidCallback onTap;
  const _CertBadge({required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: 'Certificate — tap to view',
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [AppColors.warning, AppColors.warningDeep],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(999),
            boxShadow: const [
              BoxShadow(color: Color(0x44000000), blurRadius: 6, offset: Offset(0, 2)),
            ],
          ),
          child: const Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.workspace_premium_rounded, color: Colors.white, size: 14),
            SizedBox(width: 3),
            Text('CERT',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 10,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.6,
                )),
          ]),
        ),
      ),
    );
  }
}

class _MiniLetterPill extends StatelessWidget {
  final String letter;
  const _MiniLetterPill({required this.letter});

  Color _colorFor(String l) {
    if (l.startsWith('A')) return AppColors.success;
    if (l.startsWith('B')) return AppColors.info;
    if (l.startsWith('C')) return AppColors.accent;
    if (l.startsWith('D')) return AppColors.warning;
    return AppColors.danger;
  }

  @override
  Widget build(BuildContext context) {
    final c = _colorFor(letter);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(AppSpacing.radiusPill),
      ),
      child: Text(letter,
          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: c)),
    );
  }
}

/// Phase 18 — compact attendance chip shown next to the progress ring
/// on each class card. Attendance is class-level (not per-course), so
/// the number is the same across every card; showing it here just puts
/// the info where the student actually looks. Silent when the student
/// has no attendance history yet.
class _AttendanceChip extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(myAttendanceProvider);
    return async.when(
      loading: () => const SizedBox.shrink(),
      error: (_, _) => const SizedBox.shrink(),
      data: (marks) {
        if (marks.isEmpty) return const SizedBox.shrink();
        final good = marks
            .where((m) => m.status == 'present' || m.status == 'excused')
            .length;
        final pct = (good / marks.length * 100).round();
        final passed = pct >= 80;
        final bg = passed ? AppColors.successSoft : AppColors.warningSoft;
        final fg = passed ? AppColors.success : AppColors.warning;
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text('$pct%',
              style: TextStyle(
                  color: fg, fontWeight: FontWeight.w800, fontSize: 11)),
        );
      },
    );
  }
}
