import 'lesson.dart';
import 'quiz.dart';

class CourseModule {
  final String id;
  final String courseId;
  final String title;
  final int orderIndex;
  final List<Lesson> lessons;
  final List<QuizSummary> quizzes;

  const CourseModule({
    required this.id,
    required this.courseId,
    required this.title,
    required this.orderIndex,
    this.lessons = const [],
    this.quizzes = const [],
  });

  factory CourseModule.fromJson(Map<String, dynamic> j) => CourseModule(
        id: j['id'] as String,
        courseId: (j['courseId'] ?? '') as String,
        title: (j['title'] ?? '') as String,
        orderIndex: (j['orderIndex'] ?? 0) as int,
        lessons: (j['lessons'] as List<dynamic>? ?? const [])
            .map((e) => Lesson.fromJson(e as Map<String, dynamic>))
            .toList(),
        quizzes: (j['quizzes'] as List<dynamic>? ?? const [])
            .map((e) => QuizSummary.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'courseId': courseId,
        'title': title,
        'orderIndex': orderIndex,
        'lessons': lessons.map((l) => l.toJson()).toList(),
      };
}
