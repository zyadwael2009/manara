import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../models/announcement.dart';
import '../../models/school_class.dart';
import '../../providers/announcements_provider.dart';
import '../../providers/auth_provider.dart';
import '../../providers/courses_provider.dart';
import '../../providers/school_providers.dart';
import '../../services/api_service.dart';

/// Phase 19 — modal composer for admin / homeroom / course-teacher.
///
/// The audience picker only surfaces options the caller can actually use:
///   - Admin: all three (school / class / course).
///   - Homeroom teacher: "class" only, class-picker limited to homerooms.
///   - Course teacher: "course" only, course-picker limited to what they
///     teach (via `myCoursesProvider`).
///
/// Opens with `showModalBottomSheet`. Submit posts, invalidates the
/// audience feed, and pops. Failures show a snackbar inside the sheet.
class AnnouncementComposerSheet extends ConsumerStatefulWidget {
  const AnnouncementComposerSheet({super.key});

  static Future<void> open(BuildContext context) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(ctx).viewInsets.bottom,
        ),
        child: const AnnouncementComposerSheet(),
      ),
    );
  }

  @override
  ConsumerState<AnnouncementComposerSheet> createState() =>
      _AnnouncementComposerSheetState();
}

class _AnnouncementComposerSheetState
    extends ConsumerState<AnnouncementComposerSheet> {
  String _audience = 'class';
  String? _classId;
  String? _courseId;
  final _title = TextEditingController();
  final _body = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authProvider).user;
    final isAdmin = user?.role == 'admin';
    final classesAsync = ref.watch(classesProvider(null));
    final myCoursesState = ref.watch(myCoursesProvider);

    // Which options is the caller allowed to pick?
    final availableAudiences = <String>[
      if (isAdmin) 'school',
      'class',
      'course',
    ];
    if (!availableAudiences.contains(_audience)) {
      _audience = availableAudiences.first;
    }

    // Class picker source: admin sees all; teacher sees only their homerooms.
    final allClasses = classesAsync.value ?? const <SchoolClass>[];
    final classChoices = isAdmin
        ? allClasses
        : allClasses.where((c) => c.homeroomTeacherId == user?.id).toList();
    // Course picker source: admin sees all their published; teacher sees myCourses.
    final courseChoices = myCoursesState.courses;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
            AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xl),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Row(children: [
            const Icon(Icons.campaign_outlined, color: AppColors.accent),
            const SizedBox(width: AppSpacing.sm),
            Text('New announcement',
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
          _AudienceSegments(
            audiences: availableAudiences,
            selected: _audience,
            onChanged: (v) => setState(() {
              _audience = v;
              _classId = null;
              _courseId = null;
            }),
          ),
          const SizedBox(height: AppSpacing.md),
          if (_audience == 'class') ...[
            DropdownButtonFormField<String>(
              value: _classId,
              hint: const Text('Which class?'),
              decoration: const InputDecoration(
                labelText: 'Class',
                border: OutlineInputBorder(),
              ),
              items: [
                for (final c in classChoices)
                  DropdownMenuItem(value: c.id, child: Text(c.name)),
              ],
              onChanged: (v) => setState(() => _classId = v),
            ),
            const SizedBox(height: AppSpacing.md),
          ] else if (_audience == 'course') ...[
            DropdownButtonFormField<String>(
              value: _courseId,
              hint: const Text('Which course?'),
              decoration: const InputDecoration(
                labelText: 'Course',
                border: OutlineInputBorder(),
              ),
              items: [
                for (final c in courseChoices)
                  DropdownMenuItem(value: c.id, child: Text(c.title)),
              ],
              onChanged: (v) => setState(() => _courseId = v),
            ),
            const SizedBox(height: AppSpacing.md),
          ],
          TextField(
            controller: _title,
            decoration: const InputDecoration(
              labelText: 'Title',
              border: OutlineInputBorder(),
            ),
            maxLength: 200,
          ),
          const SizedBox(height: AppSpacing.md),
          TextField(
            controller: _body,
            decoration: const InputDecoration(
              labelText: 'Message',
              border: OutlineInputBorder(),
              alignLabelWithHint: true,
            ),
            minLines: 3,
            maxLines: 6,
            maxLength: 5000,
          ),
          const SizedBox(height: AppSpacing.lg),
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton.icon(
              onPressed: _sending ? null : _submit,
              icon: _sending
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.5,
                        valueColor: AlwaysStoppedAnimation(Colors.white),
                      ),
                    )
                  : const Icon(Icons.send_rounded),
              label: Text(_sending ? 'Posting…' : 'Post announcement'),
            ),
          ),
        ]),
      ),
    );
  }

  Future<void> _submit() async {
    if (_title.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Title is required.')),
      );
      return;
    }
    if (_audience == 'class' && _classId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Pick a class.')),
      );
      return;
    }
    if (_audience == 'course' && _courseId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Pick a course.')),
      );
      return;
    }
    setState(() => _sending = true);
    try {
      await ApiService.instance.createAnnouncement(AnnouncementInput(
        audience: _audience,
        title: _title.text.trim(),
        body: _body.text.trim(),
        classId: _audience == 'class' ? _classId : null,
        courseId: _audience == 'course' ? _courseId : null,
      ));
      ref.invalidate(myAnnouncementsProvider);
      if (!mounted) return;
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Announcement posted.')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _sending = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(friendlyError(e))),
      );
    }
  }
}

class _AudienceSegments extends StatelessWidget {
  final List<String> audiences;
  final String selected;
  final ValueChanged<String> onChanged;
  const _AudienceSegments({
    required this.audiences,
    required this.selected,
    required this.onChanged,
  });
  @override
  Widget build(BuildContext context) {
    return Row(children: [
      for (final a in audiences) ...[
        Expanded(
          child: InkWell(
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
            onTap: () => onChanged(a),
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 10),
              decoration: BoxDecoration(
                color: a == selected
                    ? AppColors.primary
                    : AppColors.surfaceMuted,
                borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
              ),
              alignment: Alignment.center,
              child: Text(
                _label(a),
                style: TextStyle(
                  color:
                      a == selected ? Colors.white : AppColors.textSecondary,
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                ),
              ),
            ),
          ),
        ),
        if (a != audiences.last) const SizedBox(width: AppSpacing.sm),
      ],
    ]);
  }

  static String _label(String a) => switch (a) {
        'school' => 'School',
        'class' => 'Class',
        'course' => 'Course',
        _ => a,
      };
}
