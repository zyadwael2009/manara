// Phase 27 — video-inline checkpoint.
//
// One `VideoCheckpoint` = one pause-point on a video lesson. The player
// pauses at `positionSeconds`, shows the MC prompt, and only resumes on
// a correct answer. The server never records attempts — checkpoints are
// pure engagement, not gradebook input.
//
// Student callers get `correctOptionId == null`; owners see the answer
// so they can preview + edit their own checkpoints.

class VideoCheckpoint {
  final String id;
  final String lessonId;
  final int positionSeconds;
  final String prompt;
  final List<VideoCheckpointOption> options;
  final String? correctOptionId;

  const VideoCheckpoint({
    required this.id,
    required this.lessonId,
    required this.positionSeconds,
    required this.prompt,
    required this.options,
    this.correctOptionId,
  });

  factory VideoCheckpoint.fromJson(Map<String, dynamic> j) {
    final raw = (j['options'] as List?) ?? const [];
    final opts = raw
        .whereType<Map>()
        .map((o) => VideoCheckpointOption.fromJson(
              o.map((k, v) => MapEntry(k.toString(), v)),
            ))
        .toList();
    return VideoCheckpoint(
      id: j['id'] as String,
      lessonId: (j['lessonId'] as String?) ?? '',
      positionSeconds: (j['positionSeconds'] as num?)?.toInt() ?? 0,
      prompt: (j['prompt'] as String?) ?? '',
      options: opts,
      correctOptionId: j['correctOptionId'] as String?,
    );
  }
}

class VideoCheckpointOption {
  final String id;
  final String text;
  const VideoCheckpointOption({required this.id, required this.text});
  factory VideoCheckpointOption.fromJson(Map<String, dynamic> j) =>
      VideoCheckpointOption(
        id: (j['id'] as String?) ?? '',
        text: (j['text'] as String?) ?? '',
      );

  Map<String, dynamic> toJson() => {'id': id, 'text': text};
}
