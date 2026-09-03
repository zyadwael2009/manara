import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../providers/courses_provider.dart';
import '../../providers/grading_providers.dart';
import '../../services/api_service.dart';

/// Rubric editor — per course.
/// Server enforces sum == 100; UI shows a live-updated sum and disables
/// save until it's exactly 100.
class RubricEditorScreen extends ConsumerStatefulWidget {
  final String courseId;
  final String courseTitle;
  const RubricEditorScreen({super.key, required this.courseId, required this.courseTitle});

  @override
  ConsumerState<RubricEditorScreen> createState() => _RubricEditorScreenState();
}

class _Row {
  final String categoryId;
  final String categoryName;
  final TextEditingController scoreCtrl;
  _Row({required this.categoryId, required this.categoryName, required this.scoreCtrl});
}

class _RubricEditorScreenState extends ConsumerState<RubricEditorScreen> {
  List<_Row> _rows = [];
  bool _loading = true;
  bool _saving = false;
  bool _existedBefore = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    for (final r in _rows) {
      r.scoreCtrl.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final existing = await ApiService.instance.getRubric(widget.courseId);
      final categories = await ApiService.instance.listGradeCategories();
      final byCat = {for (final r in existing) r.gradeCategoryId: r};
      // Start with all categories (so admin can toggle/add), pre-fill scores
      // for the ones already in the rubric.
      final rows = <_Row>[];
      for (final c in categories) {
        final e = byCat[c.id];
        rows.add(_Row(
          categoryId: c.id,
          categoryName: c.name,
          scoreCtrl: TextEditingController(text: e == null ? '' : '${e.maxScore}'),
        ));
      }
      setState(() {
        _rows = rows;
        _existedBefore = existing.isNotEmpty;
        _loading = false;
      });
    } on ApiException catch (e) {
      setState(() {
        _loading = false;
        _error = e.message;
      });
    }
  }

  int get _currentSum {
    int s = 0;
    for (final r in _rows) {
      final n = int.tryParse(r.scoreCtrl.text.trim());
      if (n != null && n > 0) s += n;
    }
    return s;
  }

  Future<void> _save() async {
    if (_currentSum != 100) return;
    setState(() => _saving = true);
    try {
      if (_existedBefore) {
        final ok = await _confirmRecompute();
        if (ok != true) {
          setState(() => _saving = false);
          return;
        }
      }
      final items = <Map<String, dynamic>>[];
      int order = 0;
      for (final r in _rows) {
        final n = int.tryParse(r.scoreCtrl.text.trim());
        if (n == null || n <= 0) continue;
        items.add({
          'gradeCategoryId': r.categoryId,
          'maxScore': n,
          'orderIndex': order++,
        });
      }
      final result = await ApiService.instance.setRubric(widget.courseId, items);
      ref.invalidate(rubricProvider(widget.courseId));
      ref.invalidate(courseDetailProvider(widget.courseId));
      if (mounted) {
        final warning = result['warning'] as String?;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(warning ?? 'Rubric saved.'),
        ));
        Navigator.of(context).pop();
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<bool?> _confirmRecompute() {
    return showDialog<bool>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('Recompute existing grades?'),
        content: Text(
          'This rubric already has entered grades. Saving will recompute every student\'s cached percentage / letter / GPA against the new maxima.',
          style: AppTextStyles.body(d),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () => Navigator.pop(d, true),
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.warning),
            child: const Text('Save and recompute'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Rubric', style: AppTextStyles.h3(context)),
            Text(widget.courseTitle, style: AppTextStyles.caption(context)),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!, style: AppTextStyles.body(context, color: AppColors.danger)))
              : Column(children: [
                  Expanded(
                    child: ListView(
                      padding: const EdgeInsets.all(AppSpacing.xl),
                      children: [
                        for (final r in _rows)
                          Card(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                              child: Row(children: [
                                Expanded(child: Text(r.categoryName)),
                                SizedBox(
                                  width: 80,
                                  child: TextField(
                                    controller: r.scoreCtrl,
                                    keyboardType: TextInputType.number,
                                    textAlign: TextAlign.center,
                                    decoration: const InputDecoration(
                                      isDense: true,
                                      hintText: '0',
                                      contentPadding: EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                                    ),
                                    onChanged: (_) => setState(() {}),
                                  ),
                                ),
                              ]),
                            ),
                          ),
                      ],
                    ),
                  ),
                  _SumBar(sum: _currentSum),
                  SafeArea(
                    child: Padding(
                      padding: const EdgeInsets.all(AppSpacing.md),
                      child: SizedBox(
                        width: double.infinity,
                        child: ElevatedButton(
                          onPressed: (_saving || _currentSum != 100) ? null : _save,
                          child: Text(_saving ? 'Saving…' : 'Save rubric'),
                        ),
                      ),
                    ),
                  ),
                ]),
    );
  }
}

class _SumBar extends StatelessWidget {
  final int sum;
  const _SumBar({required this.sum});

  @override
  Widget build(BuildContext context) {
    final ok = sum == 100;
    final over = sum > 100;
    final color = ok ? AppColors.success : (over ? AppColors.danger : AppColors.warning);
    return Container(
      color: color.withValues(alpha: 0.1),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(children: [
        Icon(ok ? Icons.check_circle_outline : Icons.info_outline, color: color),
        const SizedBox(width: AppSpacing.sm),
        Text(
          ok ? 'Sum = 100 ✓' : 'Sum = $sum · needs to equal 100',
          style: TextStyle(fontWeight: FontWeight.w700, color: color),
        ),
      ]),
    );
  }
}
