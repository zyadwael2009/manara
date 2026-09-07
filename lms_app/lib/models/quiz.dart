/// Quiz + question + attempt models for Phase 4.
library;

class QuizSummary {
  final String id;
  final String moduleId;
  final String title;
  final bool isPublished;
  final int totalPoints;
  final int passingScore;
  final int? timeLimitMinutes;

  /// Phase 16 — per-student decoration. Populated by the course-detail
  /// response when the caller is a student enrolled in the course. Null
  /// (or 0 for count) when never attempted; absent entirely when the
  /// caller is not a student.
  final int myAttemptsCount;
  final double? myBestPercent;
  final double? myLastPercent;
  final bool myPassed;

  const QuizSummary({
    required this.id,
    required this.moduleId,
    required this.title,
    required this.isPublished,
    required this.totalPoints,
    required this.passingScore,
    this.timeLimitMinutes,
    this.myAttemptsCount = 0,
    this.myBestPercent,
    this.myLastPercent,
    this.myPassed = false,
  });

  /// True when the caller has at least one submitted attempt on this quiz.
  bool get hasMyHistory => myAttemptsCount > 0;

  factory QuizSummary.fromJson(Map<String, dynamic> j) => QuizSummary(
        id: j['id'] as String,
        moduleId: (j['moduleId'] ?? '') as String,
        title: (j['title'] ?? '') as String,
        isPublished: (j['isPublished'] ?? false) as bool,
        totalPoints: (j['totalPoints'] ?? 0) as int,
        passingScore: (j['passingScore'] ?? 60) as int,
        timeLimitMinutes: j['timeLimitMinutes'] as int?,
        myAttemptsCount: (j['myAttemptsCount'] ?? 0) as int,
        myBestPercent: (j['myBestPercent'] is num)
            ? (j['myBestPercent'] as num).toDouble()
            : null,
        myLastPercent: (j['myLastPercent'] is num)
            ? (j['myLastPercent'] as num).toDouble()
            : null,
        myPassed: (j['myPassed'] ?? false) as bool,
      );
}

class Quiz {
  final String id;
  final String moduleId;
  final String title;
  final String description;
  final int passingScore;
  final int? maxAttempts;
  final String scoringMode;
  final int? timeLimitMinutes;
  final String? availableFrom;
  final String? availableUntil;
  final bool isPublished;
  final int totalPoints;
  final List<QuizQuestion> questions;

  const Quiz({
    required this.id,
    required this.moduleId,
    required this.title,
    required this.description,
    required this.passingScore,
    required this.scoringMode,
    required this.isPublished,
    required this.totalPoints,
    this.maxAttempts,
    this.timeLimitMinutes,
    this.availableFrom,
    this.availableUntil,
    this.questions = const [],
  });

  factory Quiz.fromJson(Map<String, dynamic> j) => Quiz(
        id: j['id'] as String,
        moduleId: (j['moduleId'] ?? '') as String,
        title: (j['title'] ?? '') as String,
        description: (j['description'] ?? '') as String,
        passingScore: (j['passingScore'] ?? 60) as int,
        maxAttempts: j['maxAttempts'] as int?,
        scoringMode: (j['scoringMode'] ?? 'best') as String,
        timeLimitMinutes: j['timeLimitMinutes'] as int?,
        availableFrom: j['availableFrom'] as String?,
        availableUntil: j['availableUntil'] as String?,
        isPublished: (j['isPublished'] ?? false) as bool,
        totalPoints: (j['totalPoints'] ?? 0) as int,
        questions: (j['questions'] as List<dynamic>? ?? const [])
            .map((e) => QuizQuestion.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class QuizQuestion {
  final String id;
  final String quizId;
  final int orderIndex;
  final String type; // mc_single | mc_multi | true_false | short_answer | essay
  final String prompt;
  final int points;
  final bool required;
  final List<QuizOption> options;
  /// Only present when the caller is an author.
  final List<AcceptableAnswer>? acceptableAnswers;

  const QuizQuestion({
    required this.id,
    required this.quizId,
    required this.type,
    required this.prompt,
    required this.orderIndex,
    required this.points,
    required this.required,
    this.options = const [],
    this.acceptableAnswers,
  });

  factory QuizQuestion.fromJson(Map<String, dynamic> j) {
    return QuizQuestion(
      id: j['id'] as String,
      quizId: (j['quizId'] ?? '') as String,
      orderIndex: (j['orderIndex'] ?? 0) as int,
      type: (j['type'] ?? 'mc_single') as String,
      prompt: (j['prompt'] ?? '') as String,
      points: (j['points'] ?? 1) as int,
      required: (j['required'] ?? true) as bool,
      options: (j['options'] as List<dynamic>? ?? const [])
          .map((e) => QuizOption.fromJson(e as Map<String, dynamic>))
          .toList(),
      acceptableAnswers: j['acceptableAnswers'] == null
          ? null
          : (j['acceptableAnswers'] as List<dynamic>)
              .map((e) => AcceptableAnswer.fromJson(e as Map<String, dynamic>))
              .toList(),
    );
  }
}

class QuizOption {
  final String id;
  final String questionId;
  final int orderIndex;
  final String text;
  /// True if the server exposed correctness (author view). Null when hidden.
  final bool? isCorrect;

  const QuizOption({
    required this.id,
    required this.questionId,
    required this.orderIndex,
    required this.text,
    this.isCorrect,
  });

  factory QuizOption.fromJson(Map<String, dynamic> j) => QuizOption(
        id: j['id'] as String,
        questionId: (j['questionId'] ?? '') as String,
        orderIndex: (j['orderIndex'] ?? 0) as int,
        text: (j['text'] ?? '') as String,
        isCorrect: j['isCorrect'] as bool?,
      );
}

class AcceptableAnswer {
  final String text;
  final bool caseSensitive;
  const AcceptableAnswer({required this.text, this.caseSensitive = false});
  factory AcceptableAnswer.fromJson(Map<String, dynamic> j) => AcceptableAnswer(
        text: (j['text'] ?? '') as String,
        caseSensitive: (j['caseSensitive'] ?? false) as bool,
      );
}

class QuizAttempt {
  final String id;
  final String quizId;
  final String studentId;
  final String? studentName;
  final String? studentEmail;
  final String? startedAt;
  final String? submittedAt;
  final int attemptNumber;
  final double? autoScore;
  final double? manualScore;
  final double? finalScore;
  final double maxScore;
  final bool passed;
  final bool needsManualReview;
  final List<QuizAnswerEntry> answers;

  const QuizAttempt({
    required this.id,
    required this.quizId,
    required this.studentId,
    required this.attemptNumber,
    required this.maxScore,
    this.studentName,
    this.studentEmail,
    this.startedAt,
    this.submittedAt,
    this.autoScore,
    this.manualScore,
    this.finalScore,
    this.passed = false,
    this.needsManualReview = false,
    this.answers = const [],
  });

  bool get inProgress => submittedAt == null;

  factory QuizAttempt.fromJson(Map<String, dynamic> j) => QuizAttempt(
        id: j['id'] as String,
        quizId: (j['quizId'] ?? '') as String,
        studentId: (j['studentId'] ?? '') as String,
        studentName: j['studentName'] as String?,
        studentEmail: j['studentEmail'] as String?,
        startedAt: j['startedAt'] as String?,
        submittedAt: j['submittedAt'] as String?,
        attemptNumber: (j['attemptNumber'] ?? 1) as int,
        autoScore: (j['autoScore'] is num) ? (j['autoScore'] as num).toDouble() : null,
        manualScore: (j['manualScore'] is num) ? (j['manualScore'] as num).toDouble() : null,
        finalScore: (j['finalScore'] is num) ? (j['finalScore'] as num).toDouble() : null,
        maxScore: (j['maxScore'] is num) ? (j['maxScore'] as num).toDouble() : 0.0,
        passed: (j['passed'] ?? false) as bool,
        needsManualReview: (j['needsManualReview'] ?? false) as bool,
        answers: (j['answers'] as List<dynamic>? ?? const [])
            .map((e) => QuizAnswerEntry.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class QuizAnswerEntry {
  final String id;
  final String attemptId;
  final String questionId;
  final String? responseText;
  final List<String> selectedOptionIds;
  final double? perQuestionScore;
  final bool isManuallyGraded;
  final String? manualFeedback;

  const QuizAnswerEntry({
    required this.id,
    required this.attemptId,
    required this.questionId,
    this.responseText,
    this.selectedOptionIds = const [],
    this.perQuestionScore,
    this.isManuallyGraded = false,
    this.manualFeedback,
  });

  factory QuizAnswerEntry.fromJson(Map<String, dynamic> j) => QuizAnswerEntry(
        id: (j['id'] ?? '') as String,
        attemptId: (j['attemptId'] ?? '') as String,
        questionId: (j['questionId'] ?? '') as String,
        responseText: j['responseText'] as String?,
        selectedOptionIds: (j['selectedOptionIds'] as List<dynamic>? ?? const [])
            .map((e) => e.toString())
            .toList(),
        perQuestionScore:
            (j['perQuestionScore'] is num) ? (j['perQuestionScore'] as num).toDouble() : null,
        isManuallyGraded: (j['isManuallyGraded'] ?? false) as bool,
        manualFeedback: j['manualFeedback'] as String?,
      );
}

/// One row of the student "Quizzes" hub (`GET /api/quizzes/my`). Everything
/// the hub screen needs: which course/module the quiz belongs to, the
/// student's attempt history, and the rolled-up best/last projections.
class MyQuizRow {
  final MyQuizStub quiz;
  final MyQuizCourse course;
  final List<MyQuizAttemptStub> attempts;
  final int attemptsCount;
  final double? bestPercent;
  final double? lastPercent;
  final int? lastAttemptNumber;
  final bool passed;
  final bool canRetake;

  const MyQuizRow({
    required this.quiz,
    required this.course,
    this.attempts = const [],
    this.attemptsCount = 0,
    this.bestPercent,
    this.lastPercent,
    this.lastAttemptNumber,
    this.passed = false,
    this.canRetake = true,
  });

  bool get hasHistory => attemptsCount > 0;

  factory MyQuizRow.fromJson(Map<String, dynamic> j) => MyQuizRow(
        quiz: MyQuizStub.fromJson(j['quiz'] as Map<String, dynamic>),
        course: MyQuizCourse.fromJson(j['course'] as Map<String, dynamic>),
        attempts: (j['attempts'] as List<dynamic>? ?? const [])
            .map((e) => MyQuizAttemptStub.fromJson(e as Map<String, dynamic>))
            .toList(),
        attemptsCount: (j['attemptsCount'] ?? 0) as int,
        bestPercent: (j['bestPercent'] is num)
            ? (j['bestPercent'] as num).toDouble()
            : null,
        lastPercent: (j['lastPercent'] is num)
            ? (j['lastPercent'] as num).toDouble()
            : null,
        lastAttemptNumber: j['lastAttemptNumber'] as int?,
        passed: (j['passed'] ?? false) as bool,
        canRetake: (j['canRetake'] ?? true) as bool,
      );
}

class MyQuizStub {
  final String id;
  final String title;
  final String moduleId;
  final String moduleTitle;
  final int totalPoints;
  final int passingScore;
  final int? maxAttempts;
  final int? timeLimitMinutes;

  const MyQuizStub({
    required this.id,
    required this.title,
    required this.moduleId,
    required this.moduleTitle,
    required this.totalPoints,
    required this.passingScore,
    this.maxAttempts,
    this.timeLimitMinutes,
  });

  factory MyQuizStub.fromJson(Map<String, dynamic> j) => MyQuizStub(
        id: j['id'] as String,
        title: (j['title'] ?? '') as String,
        moduleId: (j['moduleId'] ?? '') as String,
        moduleTitle: (j['moduleTitle'] ?? '') as String,
        totalPoints: (j['totalPoints'] ?? 0) as int,
        passingScore: (j['passingScore'] ?? 60) as int,
        maxAttempts: j['maxAttempts'] as int?,
        timeLimitMinutes: j['timeLimitMinutes'] as int?,
      );
}

class MyQuizCourse {
  final String id;
  final String title;
  final String category;
  final String? gradeName;
  const MyQuizCourse({
    required this.id,
    required this.title,
    required this.category,
    this.gradeName,
  });
  factory MyQuizCourse.fromJson(Map<String, dynamic> j) => MyQuizCourse(
        id: j['id'] as String,
        title: (j['title'] ?? '') as String,
        category: (j['category'] ?? 'general') as String,
        gradeName: j['gradeName'] as String?,
      );
}

/// Trimmed attempt record for the quizzes hub — no per-question answers,
/// just enough to render the timeline row.
class MyQuizAttemptStub {
  final String id;
  final int attemptNumber;
  final String? submittedAt;
  final double? finalScore;
  final double? maxScore;
  final double? percent;
  final bool passed;
  final bool needsManualReview;

  const MyQuizAttemptStub({
    required this.id,
    required this.attemptNumber,
    this.submittedAt,
    this.finalScore,
    this.maxScore,
    this.percent,
    this.passed = false,
    this.needsManualReview = false,
  });

  factory MyQuizAttemptStub.fromJson(Map<String, dynamic> j) => MyQuizAttemptStub(
        id: j['id'] as String,
        attemptNumber: (j['attemptNumber'] ?? 1) as int,
        submittedAt: j['submittedAt'] as String?,
        finalScore:
            (j['finalScore'] is num) ? (j['finalScore'] as num).toDouble() : null,
        maxScore:
            (j['maxScore'] is num) ? (j['maxScore'] as num).toDouble() : null,
        percent: (j['percent'] is num) ? (j['percent'] as num).toDouble() : null,
        passed: (j['passed'] ?? false) as bool,
        needsManualReview: (j['needsManualReview'] ?? false) as bool,
      );
}

/// Result envelope returned by `/quiz-attempts/<id>/submit` and
/// `POST /quizzes/<id>/start` — the attempt + the full quiz shape.
class QuizAttemptEnvelope {
  final QuizAttempt attempt;
  final Quiz quiz;
  const QuizAttemptEnvelope({required this.attempt, required this.quiz});

  factory QuizAttemptEnvelope.fromJson(Map<String, dynamic> j) => QuizAttemptEnvelope(
        attempt: QuizAttempt.fromJson(j['attempt'] as Map<String, dynamic>),
        quiz: Quiz.fromJson(j['quiz'] as Map<String, dynamic>),
      );
}
