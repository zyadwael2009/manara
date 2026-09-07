part of 'api_service.dart';

/// Authoring, taking, and reviewing quizzes, plus the question bank.

extension ApiServiceQuizzes on ApiService {
  // ==========================================================================
  // Phase 4 — Quizzes (author)
  // ==========================================================================
  Future<Quiz> createQuiz(String moduleId,
      {required String title, int passingScore = 60, int? maxAttempts, String scoringMode = 'best', int? timeLimitMinutes}) async {
    final data = await _send('POST', '/modules/$moduleId/quizzes', body: {
      'title': title,
      'passingScore': passingScore,
      'maxAttempts': ?maxAttempts,
      'scoringMode': scoringMode,
      'timeLimitMinutes': ?timeLimitMinutes,
    }) as Map<String, dynamic>;
    return Quiz.fromJson(data);
  }

  Future<Quiz> getQuiz(String quizId) async {
    final data = await _send('GET', '/quizzes/$quizId') as Map<String, dynamic>;
    return Quiz.fromJson(data);
  }

  Future<Quiz> updateQuiz(String quizId, Map<String, dynamic> patch) async {
    final data = await _send('PUT', '/quizzes/$quizId', body: patch) as Map<String, dynamic>;
    return Quiz.fromJson(data);
  }

  Future<void> deleteQuiz(String quizId) => _send('DELETE', '/quizzes/$quizId');

  Future<Quiz> publishQuiz(String quizId) async {
    final data = await _send('POST', '/quizzes/$quizId/publish') as Map<String, dynamic>;
    return Quiz.fromJson(data);
  }

  Future<Quiz> unpublishQuiz(String quizId) async {
    final data = await _send('POST', '/quizzes/$quizId/unpublish') as Map<String, dynamic>;
    return Quiz.fromJson(data);
  }

  Future<QuizQuestion> createQuizQuestion(String quizId,
      {required String type, required String prompt, int points = 1, bool required = true}) async {
    final data = await _send('POST', '/quizzes/$quizId/questions', body: {
      'type': type,
      'prompt': prompt,
      'points': points,
      'required': required,
    }) as Map<String, dynamic>;
    return QuizQuestion.fromJson(data);
  }

  Future<QuizQuestion> updateQuizQuestion(String qqId, Map<String, dynamic> patch) async {
    final data = await _send('PUT', '/quiz-questions/$qqId', body: patch) as Map<String, dynamic>;
    return QuizQuestion.fromJson(data);
  }

  Future<void> deleteQuizQuestion(String qqId) => _send('DELETE', '/quiz-questions/$qqId');

  Future<QuizOption> createQuizOption(String qqId,
      {required String text, bool isCorrect = false}) async {
    final data = await _send('POST', '/quiz-questions/$qqId/options', body: {
      'text': text,
      'isCorrect': isCorrect,
    }) as Map<String, dynamic>;
    return QuizOption.fromJson(data);
  }

  Future<QuizOption> updateQuizOption(String optId, Map<String, dynamic> patch) async {
    final data = await _send('PUT', '/quiz-options/$optId', body: patch) as Map<String, dynamic>;
    return QuizOption.fromJson(data);
  }

  Future<void> deleteQuizOption(String optId) => _send('DELETE', '/quiz-options/$optId');

  Future<void> addAcceptableAnswer(String qqId,
      {required String text, bool caseSensitive = false}) async {
    await _send('POST', '/quiz-questions/$qqId/acceptable-answers', body: {
      'text': text,
      'caseSensitive': caseSensitive,
    });
  }

  // ==========================================================================
  // Phase 4 — Quizzes (take)
  // ==========================================================================
  Future<QuizAttemptEnvelope> startAttempt(String quizId) async {
    final data = await _send('POST', '/quizzes/$quizId/start') as Map<String, dynamic>;
    return QuizAttemptEnvelope.fromJson(data);
  }

  /// answers: list of `{ questionId, responseText?, selectedOptionIds? }`.
  Future<QuizAttemptEnvelope> submitAttempt(
    String attemptId, {
    required List<Map<String, dynamic>> answers,
  }) async {
    final data = await _send('POST', '/quiz-attempts/$attemptId/submit', body: {
      'answers': answers,
    }) as Map<String, dynamic>;
    return QuizAttemptEnvelope.fromJson(data);
  }

  Future<QuizAttemptEnvelope> getAttempt(String attemptId) async {
    final data = await _send('GET', '/quiz-attempts/$attemptId') as Map<String, dynamic>;
    return QuizAttemptEnvelope.fromJson(data);
  }

  // ==========================================================================
  // Phase 4 — Quizzes (admin/teacher)
  // ==========================================================================
  Future<List<QuizAttempt>> listQuizAttempts(String quizId) async {
    final data = await _send('GET', '/quizzes/$quizId/attempts') as List<dynamic>;
    return data.map((e) => QuizAttempt.fromJson(e as Map<String, dynamic>)).toList();
  }

  // ==========================================================================
  // Phase 24 — Streak, badges, search, question bank
  // ==========================================================================
  Future<StreakState> tickStreak() async {
    final data = await _send('POST', '/streak/tick') as Map<String, dynamic>;
    return StreakState.fromJson(data);
  }

  Future<StreakState> getStreak() async {
    final data = await _send('GET', '/streak/mine') as Map<String, dynamic>;
    return StreakState.fromJson(data);
  }

  Future<BadgesPage> getMyBadges() async {
    final data = await _send('GET', '/badges/mine') as Map<String, dynamic>;
    return BadgesPage.fromJson(data);
  }

  Future<List<SearchResult>> globalSearch(String q, {String? scope}) async {
    if (q.trim().length < 2) return const [];
    final data = await _send(
      'GET', '/search',
      query: {'q': q.trim(), 'scope': ?scope},
    ) as Map<String, dynamic>;
    final rows = data['results'] as List<dynamic>? ?? const [];
    return rows
        .map((e) => SearchResult.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<QuestionBankItem>> listQuestionBank(String courseId) async {
    final data = await _send('GET', '/courses/$courseId/question-bank')
        as List<dynamic>;
    return data
        .map((e) => QuestionBankItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<QuestionBankItem> createBankItem({
    required String courseId,
    required String type,
    required String prompt,
    int points = 1,
    List<Map<String, dynamic>>? options,
  }) async {
    final data = await _send(
      'POST', '/courses/$courseId/question-bank',
      body: {
        'type': type,
        'prompt': prompt,
        'points': points,
        'options': ?options,
      },
    ) as Map<String, dynamic>;
    return QuestionBankItem.fromJson(data);
  }

  Future<void> deleteBankItem(String itemId) async {
    await _send('DELETE', '/bank-items/$itemId');
  }

  Future<int> adoptBankItemsIntoQuiz({
    required String quizId,
    required List<String> itemIds,
  }) async {
    final data = await _send(
      'POST', '/quizzes/$quizId/adopt-bank-items',
      body: {'itemIds': itemIds},
    ) as Map<String, dynamic>;
    return (data['adopted'] as num?)?.toInt() ?? 0;
  }
}
