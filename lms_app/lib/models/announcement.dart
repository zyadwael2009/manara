/// Phase 19 — one announcement row (school / class / course).
library;

class Announcement {
  final String id;
  final String audience;        // "school" | "class" | "course"
  final String? classId;
  final String? className;
  final String? courseId;
  final String? courseTitle;
  final String authorId;
  final String? authorName;
  final String title;
  final String body;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? expiresAt;

  const Announcement({
    required this.id,
    required this.audience,
    required this.authorId,
    required this.title,
    required this.body,
    this.classId,
    this.className,
    this.courseId,
    this.courseTitle,
    this.authorName,
    this.createdAt,
    this.updatedAt,
    this.expiresAt,
  });

  bool get isSchool => audience == 'school';
  bool get isClass => audience == 'class';
  bool get isCourse => audience == 'course';

  /// Short human label for the audience chip.
  String get audienceLabel {
    switch (audience) {
      case 'school':
        return 'School';
      case 'class':
        return className == null ? 'Class' : 'Class $className';
      case 'course':
        return courseTitle ?? 'Course';
      default:
        return audience;
    }
  }

  factory Announcement.fromJson(Map<String, dynamic> j) => Announcement(
        id: j['id'] as String,
        audience: (j['audience'] as String?) ?? 'school',
        classId: j['classId'] as String?,
        className: j['className'] as String?,
        courseId: j['courseId'] as String?,
        courseTitle: j['courseTitle'] as String?,
        authorId: (j['authorId'] as String?) ?? '',
        authorName: j['authorName'] as String?,
        title: (j['title'] as String?) ?? '',
        body: (j['body'] as String?) ?? '',
        createdAt: j['createdAt'] == null
            ? null
            : DateTime.tryParse(j['createdAt'] as String),
        updatedAt: j['updatedAt'] == null
            ? null
            : DateTime.tryParse(j['updatedAt'] as String),
        expiresAt: j['expiresAt'] == null
            ? null
            : DateTime.tryParse(j['expiresAt'] as String),
      );
}

/// Payload for POST /api/announcements.
class AnnouncementInput {
  final String audience;    // "school" | "class" | "course"
  final String title;
  final String body;
  final String? classId;    // required when audience=class
  final String? courseId;   // required when audience=course
  final DateTime? expiresAt;

  const AnnouncementInput({
    required this.audience,
    required this.title,
    this.body = '',
    this.classId,
    this.courseId,
    this.expiresAt,
  });

  Map<String, dynamic> toJson() => {
        'audience': audience,
        'title': title,
        'body': body,
        if (classId != null) 'classId': classId,
        if (courseId != null) 'courseId': courseId,
        if (expiresAt != null)
          'expiresAt': expiresAt!.toUtc().toIso8601String(),
      };
}

/// Payload for GET /api/quizzes/:id/attempts/stats (Phase 19 addition to
/// the teacher's quiz-attempts screen).
class QuizAttemptStats {
  final int count;
  final int submittedCount;
  final double? avgPercent;
  final double? minPercent;
  final double? maxPercent;
  final double? passRate;

  const QuizAttemptStats({
    this.count = 0,
    this.submittedCount = 0,
    this.avgPercent,
    this.minPercent,
    this.maxPercent,
    this.passRate,
  });

  bool get hasSubmissions => submittedCount > 0;

  factory QuizAttemptStats.fromJson(Map<String, dynamic> j) => QuizAttemptStats(
        count: (j['count'] as num?)?.toInt() ?? 0,
        submittedCount: (j['submittedCount'] as num?)?.toInt() ?? 0,
        avgPercent: (j['avgPercent'] as num?)?.toDouble(),
        minPercent: (j['minPercent'] as num?)?.toDouble(),
        maxPercent: (j['maxPercent'] as num?)?.toDouble(),
        passRate: (j['passRate'] as num?)?.toDouble(),
      );
}
