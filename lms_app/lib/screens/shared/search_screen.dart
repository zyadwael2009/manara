import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../core/utils/friendly_error.dart';
import '../../core/utils/transitions.dart';
import '../../core/widgets/empty_state.dart';
import '../../models/gamify.dart';
import '../../services/api_service.dart';
import '../admin/student_detail_screen.dart';
import '../catalog/course_detail_screen.dart';
import '../../core/widgets/trailing_chevron.dart';

/// Phase 24 — global cross-cutting search. Same UI for every role;
/// the server scopes what's visible.
class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});
  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _ctrl = TextEditingController();
  Timer? _debounce;
  List<SearchResult>? _results;
  bool _searching = false;
  String? _error;
  String _query = '';

  @override
  void dispose() {
    _debounce?.cancel();
    _ctrl.dispose();
    super.dispose();
  }

  void _onChanged(String q) {
    _debounce?.cancel();
    setState(() {
      _query = q;
      _error = null;
    });
    if (q.trim().length < 2) {
      setState(() {
        _results = null;
        _searching = false;
      });
      return;
    }
    setState(() => _searching = true);
    _debounce = Timer(const Duration(milliseconds: 300), () async {
      try {
        final rows = await ApiService.instance.globalSearch(q);
        if (!mounted) return;
        setState(() {
          _results = rows;
          _searching = false;
        });
      } on ApiException catch (e) {
        if (!mounted) return;
        setState(() {
          _error = friendlyError(e);
          _searching = false;
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: TextField(
          controller: _ctrl,
          autofocus: true,
          onChanged: _onChanged,
          decoration: const InputDecoration(
            hintText: 'Search courses, lessons, quizzes…',
            border: InputBorder.none,
          ),
          style: AppTextStyles.body(context),
        ),
      ),
      body: _body(),
    );
  }

  Widget _body() {
    if (_query.trim().length < 2) {
      return Padding(
        padding: const EdgeInsets.all(AppSpacing.xxxl),
        child: Center(
          child: Text('Type at least 2 characters to search.',
              style:
                  AppTextStyles.body(context, color: AppColors.textMuted)),
        ),
      );
    }
    if (_searching) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Padding(
        padding: const EdgeInsets.all(AppSpacing.xxxl),
        child: Center(child: Text(_error!)),
      );
    }
    final rows = _results ?? const [];
    if (rows.isEmpty) {
      // Phase 26 · T2 — canonical EmptyState instead of centered text.
      return EmptyState(
        icon: Icons.search_off_rounded,
        title: 'No matches',
        message: 'Nothing matches "${_query.trim()}". Try a different word.',
      );
    }
    return ListView.separated(
      itemCount: rows.length,
      separatorBuilder: (_, __) =>
          const Divider(height: 1, color: AppColors.divider),
      itemBuilder: (context, i) => _ResultTile(result: rows[i]),
    );
  }
}

class _ResultTile extends StatelessWidget {
  final SearchResult result;
  const _ResultTile({required this.result});
  @override
  Widget build(BuildContext context) {
    late IconData icon;
    late Color color;
    switch (result.kind) {
      case 'course':
        icon = Icons.school_outlined;
        color = AppColors.primaryDark;
        break;
      case 'lesson':
        icon = Icons.menu_book_outlined;
        color = AppColors.success;
        break;
      case 'assignment':
        icon = Icons.assignment_outlined;
        color = AppColors.warning;
        break;
      case 'quiz':
        icon = Icons.quiz_outlined;
        color = AppColors.info;
        break;
      case 'student':
        icon = Icons.person_outline;
        color = AppColors.danger;
        break;
      default:
        icon = Icons.article_outlined;
        color = AppColors.textMuted;
    }
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: color.withValues(alpha: 0.15),
        child: Icon(icon, color: color, size: 18),
      ),
      title: Text(result.title,
          style: AppTextStyles.body(context)
              .copyWith(fontWeight: FontWeight.w700)),
      subtitle: Text(result.subtitle,
          style: AppTextStyles.caption(context, color: AppColors.textMuted)),
      trailing: const TrailingChevron(),
      onTap: () => _navigate(context),
    );
  }

  void _navigate(BuildContext context) {
    if (result.kind == 'course' || result.courseId != null) {
      Navigator.of(context).push(fadeThroughRoute(
        CourseDetailScreen(courseId: result.courseId ?? result.id),
      ));
      return;
    }
    if (result.kind == 'student' && result.studentId != null) {
      Navigator.of(context).push(fadeThroughRoute(
        StudentDetailScreen(studentId: result.studentId!),
      ));
      return;
    }
  }
}
