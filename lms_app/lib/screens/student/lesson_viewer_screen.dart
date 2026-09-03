import 'dart:async';

import 'package:chewie/chewie.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:syncfusion_flutter_pdfviewer/pdfviewer.dart';
import 'package:video_player/video_player.dart';

import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_spacing.dart';
import '../../core/theme/app_text_styles.dart';
import '../../models/lesson.dart';
import '../../models/video_checkpoint.dart';
import '../../providers/enrollments_provider.dart';
import '../../providers/grading_providers.dart';
import '../../services/api_service.dart';
import '../../core/utils/friendly_error.dart';
import 'widgets/lesson_comments_panel.dart';

class LessonViewerScreen extends ConsumerStatefulWidget {
  final String lessonId;
  final String? courseTitle;

  /// Phase 6: non-null when a parent is viewing the lesson from their
  /// child's dashboard. Suppresses all progress writes + hides the
  /// Mark-complete bar. Server would 403 the write anyway.
  final String? parentViewChildName;

  const LessonViewerScreen({
    super.key,
    required this.lessonId,
    this.courseTitle,
    this.parentViewChildName,
  });

  @override
  ConsumerState<LessonViewerScreen> createState() => _LessonViewerScreenState();
}

class _LessonViewerScreenState extends ConsumerState<LessonViewerScreen> {
  bool _completed = false;
  bool _markingBusy = false;
  bool _syncFailed = false; // Phase 10 M10: video beats failing → yellow dot.

  Future<void> _markComplete() async {
    setState(() => _markingBusy = true);
    try {
      await ApiService.instance.markLessonComplete(widget.lessonId);
      // Bust caches so My Classes progress + Continue band + report card refresh.
      ref.invalidate(myEnrollmentsProvider);
      ref.invalidate(continuePointerProvider);
      if (mounted) {
        setState(() => _completed = true);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Marked complete ✓')),
        );
      }
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted) setState(() => _markingBusy = false);
    }
  }

  Future<void> _autoComplete() async {
    if (widget.parentViewChildName != null) return; // parents don't write
    if (_completed) return;
    try {
      await ApiService.instance.recordProgress(widget.lessonId,
          lastPositionSeconds: 0, viewed: true);
      ref.invalidate(myEnrollmentsProvider);
      ref.invalidate(continuePointerProvider);
      if (mounted) setState(() => _completed = true);
    } catch (_) {
      // Non-fatal — student can still tap Mark complete manually.
    }
  }

  Future<void> _videoBeat(int seconds) async {
    if (widget.parentViewChildName != null) return; // parents don't write
    if (_completed) return;
    try {
      final result = await ApiService.instance.recordProgress(
        widget.lessonId,
        lastPositionSeconds: seconds,
      );
      // Phase 10 audit fix M10: clear the sync-failed flag on a successful
      // beat so the yellow dot disappears without a screen re-open.
      if (mounted && _syncFailed) setState(() => _syncFailed = false);
      if (result.completed && mounted && !_completed) {
        setState(() => _completed = true);
        ref.invalidate(myEnrollmentsProvider);
        ref.invalidate(continuePointerProvider);
      }
    } catch (_) {
      // Phase 10 audit fix M10: mark a "some progress hasn't been saved"
      // state so the completion bar can surface it as a tooltip. No retry
      // loop, no snackbar spam — just an honest signal to the student.
      if (mounted && !_syncFailed) setState(() => _syncFailed = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(lessonProvider(widget.lessonId));
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (widget.courseTitle != null)
              Text(widget.courseTitle!, style: AppTextStyles.h3(context)),
            async.maybeWhen(
              data: (l) => Text(l.title, style: AppTextStyles.caption(context)),
              orElse: () => const SizedBox.shrink(),
            ),
          ],
        ),
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl),
            child: Text(friendlyError(e),
                style: AppTextStyles.body(context, color: AppColors.danger),
                textAlign: TextAlign.center),
          ),
        ),
        data: (lesson) => _LessonBody(
          lesson: lesson,
          onAutoComplete: _autoComplete,
          onVideoBeat: _videoBeat,
        ),
      ),
      bottomNavigationBar: async.maybeWhen(
        data: (_) => widget.parentViewChildName != null
            ? _ParentReadOnlyBar(childName: widget.parentViewChildName!)
            : _CompleteBar(
                completed: _completed,
                busy: _markingBusy,
                syncFailed: _syncFailed,
                onMarkComplete: _markComplete,
              ),
        orElse: () => null,
      ),
    );
  }
}

class _CompleteBar extends StatelessWidget {
  final bool completed;
  final bool busy;
  final bool syncFailed;
  final VoidCallback onMarkComplete;
  const _CompleteBar({
    required this.completed,
    required this.busy,
    required this.syncFailed,
    required this.onMarkComplete,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          border: Border(top: BorderSide(color: AppColors.border)),
        ),
        child: Row(children: [
          // Phase 10 M10: sync-failure signal — no snackbar spam, just a
          // yellow dot with an explanatory tooltip that clears the next
          // successful beat.
          if (syncFailed)
            Padding(
              padding: const EdgeInsetsDirectional.only(end: AppSpacing.sm),
              child: Tooltip(
                message: "Some progress hasn't been saved — check your connection.",
                child: Container(
                  width: 10, height: 10,
                  decoration: const BoxDecoration(
                    color: AppColors.warning,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
            ),
          Expanded(child: SizedBox(
          width: double.infinity,
          height: 48,
          child: completed
              ? Container(
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: AppColors.successSoft,
                    borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.check_circle_rounded, color: AppColors.success),
                      const SizedBox(width: AppSpacing.sm),
                      Text('Completed', style: AppTextStyles.bodyStrong(context, color: AppColors.success)),
                    ],
                  ),
                )
              : ElevatedButton.icon(
                  onPressed: busy ? null : onMarkComplete,
                  icon: busy
                      ? const SizedBox(
                          height: 18, width: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.5,
                            valueColor: AlwaysStoppedAnimation(Colors.white),
                          ),
                        )
                      : const Icon(Icons.check_rounded),
                  label: const Text('Mark complete'),
                ),
        )),
        ]),
      ),
    );
  }
}

/// Phase 6: replaces the Mark-complete bar when a parent is viewing.
/// Same footprint (48px) so scroll insets don't shift between roles.
class _ParentReadOnlyBar extends StatelessWidget {
  final String childName;
  const _ParentReadOnlyBar({required this.childName});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          border: Border(top: BorderSide(color: AppColors.border)),
        ),
        child: Container(
          height: 48,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: AppColors.primarySoft,
            borderRadius: BorderRadius.circular(AppSpacing.radiusMd),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.remove_red_eye_outlined,
                  color: AppColors.primaryDark, size: 18),
              const SizedBox(width: AppSpacing.sm),
              Text("Viewing $childName's lesson · read-only",
                  style: AppTextStyles.bodyStrong(
                      context, color: AppColors.primaryDark)),
            ],
          ),
        ),
      ),
    );
  }
}

class _LessonBody extends StatelessWidget {
  final Lesson lesson;
  final Future<void> Function() onAutoComplete;
  final Future<void> Function(int seconds) onVideoBeat;
  const _LessonBody({
    required this.lesson,
    required this.onAutoComplete,
    required this.onVideoBeat,
  });

  @override
  Widget build(BuildContext context) {
    switch (lesson.type) {
      case 'video':
        return _VideoBody(lesson: lesson, onBeat: onVideoBeat);
      case 'pdf':
        return _PdfBody(lesson: lesson, onLastPageReached: onAutoComplete);
      case 'text':
      default:
        return _TextBody(lesson: lesson, onScrolledToBottom: onAutoComplete);
    }
  }
}

// -----------------------------------------------------------------------------
// Text — scroll-to-bottom auto-completes
// -----------------------------------------------------------------------------
class _TextBody extends StatefulWidget {
  final Lesson lesson;
  final Future<void> Function() onScrolledToBottom;
  const _TextBody({required this.lesson, required this.onScrolledToBottom});

  @override
  State<_TextBody> createState() => _TextBodyState();
}

class _TextBodyState extends State<_TextBody> {
  late final ScrollController _scroll;
  bool _fired = false;

  @override
  void initState() {
    super.initState();
    _scroll = ScrollController();
    _scroll.addListener(_onScroll);
  }

  void _onScroll() {
    if (_fired) return;
    if (!_scroll.hasClients) return;
    final pos = _scroll.position;
    // Consider "bottom" as within 40px of maxScrollExtent, and only if there's
    // actually room to scroll (short lessons auto-complete on mount below).
    if (pos.maxScrollExtent > 0 && pos.pixels >= pos.maxScrollExtent - 40) {
      _fired = true;
      widget.onScrolledToBottom();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Short-content case: nothing to scroll → mark complete once visible.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _fired) return;
      if (_scroll.hasClients && _scroll.position.maxScrollExtent == 0) {
        _fired = true;
        widget.onScrolledToBottom();
      }
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      controller: _scroll,
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Column(children: [
            Markdown(
              data: widget.lesson.contentText ?? '',
              shrinkWrap: true,
              padding: EdgeInsets.zero,
              physics: const NeverScrollableScrollPhysics(),
              styleSheet: MarkdownStyleSheet(
                h1: AppTextStyles.h1(context),
                h2: AppTextStyles.h2(context),
                h3: AppTextStyles.h3(context),
                p: AppTextStyles.body(context).copyWith(height: 1.65),
                code: TextStyle(
                  fontFamily: 'monospace',
                  backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                ),
                codeblockDecoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusSm),
                ),
              ),
            ),
            // Phase 21 — Q&A panel appended to every text lesson.
            LessonCommentsPanel(lessonId: widget.lesson.id),
          ]),
        ),
      ),
    );
  }
}

// -----------------------------------------------------------------------------
// Video — position beat every ~10 s
// -----------------------------------------------------------------------------
class _VideoBody extends StatefulWidget {
  final Lesson lesson;
  final Future<void> Function(int seconds) onBeat;
  const _VideoBody({required this.lesson, required this.onBeat});

  @override
  State<_VideoBody> createState() => _VideoBodyState();
}

class _VideoBodyState extends State<_VideoBody> {
  VideoPlayerController? _controller;
  ChewieController? _chewie;
  Timer? _beatTimer;
  String? _error;
  int _lastReportedSeconds = -1;

  // Phase 27 — video-inline checkpoints. Fetched once on init; the
  // controller listener pauses playback the first time each checkpoint
  // is crossed and shows the MC overlay via `_showCheckpoint`.
  List<VideoCheckpoint> _checkpoints = const [];
  final Set<String> _answered = <String>{};
  bool _overlayOpen = false;

  @override
  void initState() {
    super.initState();
    _loadCheckpoints();
    _initialize();
  }

  Future<void> _loadCheckpoints() async {
    try {
      final rows = await ApiService.instance.listCheckpoints(widget.lesson.id);
      if (!mounted) return;
      setState(() {
        // Sort ascending so the "next unanswered checkpoint" lookup is
        // linear + monotonic while the student watches forward.
        _checkpoints = [...rows]
          ..sort((a, b) =>
              a.positionSeconds.compareTo(b.positionSeconds));
      });
    } catch (_) {
      // Silent: checkpoints are an engagement feature, not a gate.
    }
  }

  Future<void> _initialize() async {
    final url = widget.lesson.contentUrl;
    if (url == null || url.isEmpty) {
      setState(() => _error = 'No video URL provided.');
      return;
    }
    final resolved = AppConstants.resolveMediaUrl(url);
    try {
      final c = VideoPlayerController.networkUrl(Uri.parse(resolved));
      await c.initialize();
      final ch = ChewieController(
        videoPlayerController: c,
        autoPlay: false,
        looping: false,
        materialProgressColors: ChewieProgressColors(
          playedColor: AppColors.primary,
          handleColor: AppColors.primary,
          backgroundColor: AppColors.surfaceMuted,
          bufferedColor: AppColors.primary.withValues(alpha: 0.3),
        ),
      );
      if (!mounted) {
        c.dispose();
        ch.dispose();
        return;
      }
      setState(() {
        _controller = c;
        _chewie = ch;
      });
      _beatTimer = Timer.periodic(const Duration(seconds: 10), (_) => _beat());
      // Phase 27 — listen for playback-position changes so we can pop
      // the checkpoint overlay when the head crosses the next unanswered
      // checkpoint. Runs at Flutter's frame rate (16ms via player ticks)
      // so a 1-second granularity check is cheap.
      c.addListener(_maybeShowCheckpoint);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not load video: $e');
    }
  }

  /// Phase 27 — if the current position is at-or-past the earliest
  /// unanswered checkpoint, pause and open the overlay.
  void _maybeShowCheckpoint() {
    if (_overlayOpen || !mounted) return;
    final c = _controller;
    if (c == null || !c.value.isInitialized || !c.value.isPlaying) return;
    if (_checkpoints.isEmpty) return;
    final pos = c.value.position.inSeconds;
    VideoCheckpoint? due;
    for (final cp in _checkpoints) {
      if (_answered.contains(cp.id)) continue;
      if (cp.positionSeconds <= pos) {
        due = cp;
        break;
      }
    }
    if (due == null) return;
    _overlayOpen = true;
    c.pause();
    _showCheckpoint(due).then((_) {
      _overlayOpen = false;
    });
  }

  Future<void> _showCheckpoint(VideoCheckpoint cp) async {
    // Modal barrier — the student MUST answer correctly to resume,
    // matching the "resume on correct answer" contract from the plan.
    // A wrong answer just clears the selection and lets them retry.
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (d) => _CheckpointDialog(
        checkpoint: cp,
        onCorrect: () {
          _answered.add(cp.id);
          Navigator.of(d).pop();
        },
      ),
    );
    // Auto-resume playback after a correct answer.
    if (mounted && _answered.contains(cp.id)) {
      _controller?.play();
    }
  }

  void _beat() {
    final c = _controller;
    if (c == null || !c.value.isInitialized) return;
    final seconds = c.value.position.inSeconds;
    // Phase 10 audit fix M11: report every ~10s tick, regardless of
    // direction. Previous `<=` guard hid rewinds — a student who watched
    // to minute 6 then rewound to minute 2 to review would resume at
    // minute 6 next time, past the material they wanted to revisit.
    if (seconds == _lastReportedSeconds) return;
    _lastReportedSeconds = seconds;
    widget.onBeat(seconds);
  }

  @override
  void dispose() {
    _beatTimer?.cancel();
    _controller?.removeListener(_maybeShowCheckpoint);
    _chewie?.dispose();
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl),
          child: Text(_error!, style: AppTextStyles.body(context, color: AppColors.danger)),
        ),
      );
    }
    if (_chewie == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return Column(children: [
      AspectRatio(
        aspectRatio: _controller!.value.aspectRatio == 0 ? 16 / 9 : _controller!.value.aspectRatio,
        child: Chewie(controller: _chewie!),
      ),
      Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.lesson.title, style: AppTextStyles.h2(context)),
            if ((widget.lesson.contentText ?? '').isNotEmpty) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(widget.lesson.contentText!, style: AppTextStyles.body(context)),
            ],
          ],
        ),
      ),
    ]);
  }
}

// -----------------------------------------------------------------------------
// Phase 27 — Checkpoint dialog
//
// Modal barrier: student MUST answer correctly to close it. A wrong
// pick shows a soft red hint and lets them retry — nothing is recorded
// server-side either way. Auto-resume happens in `_showCheckpoint` once
// this dialog closes with the checkpoint marked answered.
// -----------------------------------------------------------------------------
class _CheckpointDialog extends StatefulWidget {
  final VideoCheckpoint checkpoint;
  final VoidCallback onCorrect;
  const _CheckpointDialog({
    required this.checkpoint,
    required this.onCorrect,
  });
  @override
  State<_CheckpointDialog> createState() => _CheckpointDialogState();
}

class _CheckpointDialogState extends State<_CheckpointDialog> {
  String? _picked;
  bool _wrong = false;

  void _submit() {
    if (_picked == null) return;
    if (_picked == widget.checkpoint.correctOptionId) {
      widget.onCorrect();
    } else {
      setState(() => _wrong = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    // If the server didn't send a correctOptionId (shouldn't happen for
    // student callers because we tolerate no answer set), treat any
    // pick as "correct" so the video isn't permanently paused.
    final noAnswerConfigured =
        widget.checkpoint.correctOptionId == null;
    return AlertDialog(
      title: Row(children: [
        const Icon(Icons.pause_circle_outline_rounded,
            color: AppColors.primary),
        const SizedBox(width: AppSpacing.sm),
        Text('Checkpoint', style: AppTextStyles.h3(context)),
      ]),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.checkpoint.prompt, style: AppTextStyles.body(context)),
          const SizedBox(height: AppSpacing.md),
          for (final o in widget.checkpoint.options)
            RadioListTile<String>(
              value: o.id,
              groupValue: _picked,
              onChanged: (v) => setState(() {
                _picked = v;
                _wrong = false;
              }),
              title: Text(o.text),
              dense: true,
              contentPadding: EdgeInsets.zero,
            ),
          if (_wrong) ...[
            const SizedBox(height: AppSpacing.sm),
            Text('Not quite — give it another try.',
                style: AppTextStyles.caption(context,
                    color: AppColors.danger)),
          ],
        ],
      ),
      actions: [
        ElevatedButton(
          onPressed: _picked == null
              ? null
              : (noAnswerConfigured
                  ? () => widget.onCorrect()
                  : _submit),
          child: const Text('Submit'),
        ),
      ],
    );
  }
}


// -----------------------------------------------------------------------------
// PDF — last page auto-completes
// -----------------------------------------------------------------------------
class _PdfBody extends StatefulWidget {
  final Lesson lesson;
  final Future<void> Function() onLastPageReached;
  const _PdfBody({required this.lesson, required this.onLastPageReached});

  @override
  State<_PdfBody> createState() => _PdfBodyState();
}

class _PdfBodyState extends State<_PdfBody> {
  bool _fired = false;
  int _totalPages = 0;

  @override
  Widget build(BuildContext context) {
    final url = widget.lesson.contentUrl;
    if (url == null || url.isEmpty) {
      return Center(
        child: Text("This lesson's PDF is missing — please ask your teacher.",
            style: AppTextStyles.body(context, color: AppColors.danger)),
      );
    }
    return SfPdfViewer.network(
      AppConstants.resolveMediaUrl(url),
      onDocumentLoaded: (details) {
        _totalPages = details.document.pages.count;
      },
      onPageChanged: (details) {
        // Phase 9 audit fix F12: real last-page detection (previous
        // implementation was a self-comparison + 15-second timer that
        // marked any PDF complete regardless of whether the student read
        // it). Trust-core adjacent — a student opening a 400-page PDF
        // and walking away used to auto-complete the lesson.
        if (_fired || _totalPages == 0) return;
        if (details.newPageNumber >= _totalPages) {
          _fired = true;
          widget.onLastPageReached();
        }
      },
    );
  }
}
