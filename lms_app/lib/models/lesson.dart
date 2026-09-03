class Lesson {
  final String id;
  final String moduleId;
  final String title;
  final String type; // video | text | pdf
  final int? durationMinutes;
  final int orderIndex;
  final bool previewLocked;

  /// Populated only for the owning instructor / admin. Anonymous and student
  /// (pre-enrollment) requests get null here.
  final String? contentUrl;
  final String? contentText;

  const Lesson({
    required this.id,
    required this.moduleId,
    required this.title,
    required this.type,
    required this.orderIndex,
    required this.previewLocked,
    this.durationMinutes,
    this.contentUrl,
    this.contentText,
  });

  factory Lesson.fromJson(Map<String, dynamic> j) => Lesson(
        id: j['id'] as String,
        moduleId: (j['moduleId'] ?? '') as String,
        title: (j['title'] ?? '') as String,
        type: (j['type'] ?? 'text') as String,
        durationMinutes: j['durationMinutes'] as int?,
        orderIndex: (j['orderIndex'] ?? 0) as int,
        previewLocked: (j['previewLocked'] ?? true) as bool,
        contentUrl: j['contentUrl'] as String?,
        contentText: j['contentText'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'moduleId': moduleId,
        'title': title,
        'type': type,
        'durationMinutes': durationMinutes,
        'orderIndex': orderIndex,
        'previewLocked': previewLocked,
        if (contentUrl != null) 'contentUrl': contentUrl,
        if (contentText != null) 'contentText': contentText,
      };
}
