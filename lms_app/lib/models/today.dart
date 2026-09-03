import 'timetable.dart';

/// Phase 18 — the payload of `GET /api/students/today`, rendered by the
/// inline TodayCard on the student's My classes screen.
class TodayView {
  final String date; // YYYY-MM-DD
  final List<Period> periods;
  final List<TodayAssignment> assignmentsDueToday;
  final List<TodayOpenQuiz> openQuizzes;

  const TodayView({
    required this.date,
    this.periods = const [],
    this.assignmentsDueToday = const [],
    this.openQuizzes = const [],
  });

  bool get isEmpty =>
      periods.isEmpty &&
      assignmentsDueToday.isEmpty &&
      openQuizzes.isEmpty;

  factory TodayView.fromJson(Map<String, dynamic> j) => TodayView(
        date: (j['date'] as String?) ?? '',
        periods: (j['periods'] as List<dynamic>? ?? const [])
            .map((e) => Period.fromJson(e as Map<String, dynamic>))
            .toList(),
        assignmentsDueToday:
            (j['assignmentsDueToday'] as List<dynamic>? ?? const [])
                .map((e) => TodayAssignment.fromJson(e as Map<String, dynamic>))
                .toList(),
        openQuizzes: (j['openQuizzes'] as List<dynamic>? ?? const [])
            .map((e) => TodayOpenQuiz.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class TodayAssignment {
  final String id;
  final String title;
  final DateTime? dueAt;
  final int maxPoints;
  final String? courseId;
  final String courseTitle;
  final String moduleTitle;

  const TodayAssignment({
    required this.id,
    required this.title,
    required this.maxPoints,
    required this.courseTitle,
    required this.moduleTitle,
    this.courseId,
    this.dueAt,
  });

  factory TodayAssignment.fromJson(Map<String, dynamic> j) => TodayAssignment(
        id: j['id'] as String,
        title: (j['title'] as String?) ?? '',
        dueAt: j['dueAt'] == null
            ? null
            : DateTime.tryParse(j['dueAt'] as String),
        maxPoints: (j['maxPoints'] as num?)?.toInt() ?? 100,
        courseId: j['courseId'] as String?,
        courseTitle: (j['courseTitle'] as String?) ?? '',
        moduleTitle: (j['moduleTitle'] as String?) ?? '',
      );
}

class TodayOpenQuiz {
  final String id;
  final String title;
  final int totalPoints;
  final int attemptsUsed;
  final int? maxAttempts;
  final int passingScore;
  final String? courseId;
  final String courseTitle;
  final String moduleTitle;

  const TodayOpenQuiz({
    required this.id,
    required this.title,
    required this.totalPoints,
    required this.attemptsUsed,
    required this.passingScore,
    required this.courseTitle,
    required this.moduleTitle,
    this.maxAttempts,
    this.courseId,
  });

  factory TodayOpenQuiz.fromJson(Map<String, dynamic> j) => TodayOpenQuiz(
        id: j['id'] as String,
        title: (j['title'] as String?) ?? '',
        totalPoints: (j['totalPoints'] as num?)?.toInt() ?? 0,
        attemptsUsed: (j['attemptsUsed'] as num?)?.toInt() ?? 0,
        maxAttempts: (j['maxAttempts'] as num?)?.toInt(),
        passingScore: (j['passingScore'] as num?)?.toInt() ?? 60,
        courseId: j['courseId'] as String?,
        courseTitle: (j['courseTitle'] as String?) ?? '',
        moduleTitle: (j['moduleTitle'] as String?) ?? '',
      );
}
