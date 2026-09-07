/// Phase 24 — streak + badges + search + question bank envelopes.
library;

class StreakState {
  final int currentStreak;
  final int longestStreak;
  final String? lastActivityDate;
  const StreakState({
    this.currentStreak = 0,
    this.longestStreak = 0,
    this.lastActivityDate,
  });
  factory StreakState.fromJson(Map<String, dynamic> j) => StreakState(
        currentStreak: (j['currentStreak'] as num?)?.toInt() ?? 0,
        longestStreak: (j['longestStreak'] as num?)?.toInt() ?? 0,
        lastActivityDate: j['lastActivityDate'] as String?,
      );
}

class Badge {
  final String id;
  final String title;
  final String icon; // material icon name from the API
  final String description;
  final bool earned;
  const Badge({
    required this.id,
    required this.title,
    required this.icon,
    required this.description,
    this.earned = false,
  });
  factory Badge.fromJson(Map<String, dynamic> j) => Badge(
        id: (j['id'] as String?) ?? '',
        title: (j['title'] as String?) ?? '',
        icon: (j['icon'] as String?) ?? 'star',
        description: (j['description'] as String?) ?? '',
        earned: (j['earned'] as bool?) ?? false,
      );
}

class BadgesPage {
  final List<Badge> badges;
  final int earnedCount;
  const BadgesPage({this.badges = const [], this.earnedCount = 0});
  factory BadgesPage.fromJson(Map<String, dynamic> j) => BadgesPage(
        badges: (j['badges'] as List<dynamic>? ?? const [])
            .map((e) => Badge.fromJson(e as Map<String, dynamic>))
            .toList(),
        earnedCount: (j['earnedCount'] as num?)?.toInt() ?? 0,
      );
}

/// One search result — kind + a couple of identifiers so the caller can
/// route to the right screen (course / lesson / assignment / quiz / student).
class SearchResult {
  final String kind;       // course | lesson | assignment | quiz | student
  final String id;
  final String title;
  final String subtitle;
  final String? courseId;
  final String? lessonId;
  final String? assignmentId;
  final String? quizId;
  final String? studentId;

  const SearchResult({
    required this.kind,
    required this.id,
    required this.title,
    required this.subtitle,
    this.courseId,
    this.lessonId,
    this.assignmentId,
    this.quizId,
    this.studentId,
  });

  factory SearchResult.fromJson(Map<String, dynamic> j) => SearchResult(
        kind: (j['kind'] as String?) ?? '',
        id: (j['id'] as String?) ?? '',
        title: (j['title'] as String?) ?? '',
        subtitle: (j['subtitle'] as String?) ?? '',
        courseId: j['courseId'] as String?,
        lessonId: j['lessonId'] as String?,
        assignmentId: j['assignmentId'] as String?,
        quizId: j['quizId'] as String?,
        studentId: j['studentId'] as String?,
      );
}

/// One item in a course-scoped question bank.
class QuestionBankItem {
  final String id;
  final String courseId;
  final String type;
  final String prompt;
  final int points;
  final List<QuestionBankOption> options;

  const QuestionBankItem({
    required this.id,
    required this.courseId,
    required this.type,
    required this.prompt,
    required this.points,
    this.options = const [],
  });

  factory QuestionBankItem.fromJson(Map<String, dynamic> j) => QuestionBankItem(
        id: (j['id'] as String?) ?? '',
        courseId: (j['courseId'] as String?) ?? '',
        type: (j['type'] as String?) ?? 'mc_single',
        prompt: (j['prompt'] as String?) ?? '',
        points: (j['points'] as num?)?.toInt() ?? 1,
        options: (j['options'] as List<dynamic>? ?? const [])
            .map(
                (e) => QuestionBankOption.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class QuestionBankOption {
  final String id;
  final String text;
  final bool isCorrect;
  const QuestionBankOption({
    required this.id,
    required this.text,
    required this.isCorrect,
  });
  factory QuestionBankOption.fromJson(Map<String, dynamic> j) =>
      QuestionBankOption(
        id: (j['id'] as String?) ?? '',
        text: (j['text'] as String?) ?? '',
        isCorrect: (j['isCorrect'] as bool?) ?? false,
      );
}
