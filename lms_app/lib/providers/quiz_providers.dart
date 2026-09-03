import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_service.dart';

/// Full quiz detail (with questions). Authors see answer keys; students don't.
final quizProvider = FutureProvider.autoDispose.family((ref, String quizId) async {
  return ApiService.instance.getQuiz(quizId);
});

/// All attempts on a quiz — for the teacher's Attempts screen.
final quizAttemptsProvider =
    FutureProvider.autoDispose.family((ref, String quizId) async {
  return ApiService.instance.listQuizAttempts(quizId);
});

/// Student's own history of attempts for one quiz.
final myQuizAttemptsProvider =
    FutureProvider.autoDispose.family((ref, String quizId) async {
  return ApiService.instance.myAttempts(quizId);
});

/// Phase 16 — top-level student quizzes hub. Every published quiz across
/// every course the student is enrolled in, with best/last/attempts.
final myQuizzesAllProvider = FutureProvider.autoDispose((ref) async {
  return ApiService.instance.myQuizzesAll();
});

/// A single attempt envelope (attempt + quiz with keys if allowed).
final attemptProvider =
    FutureProvider.autoDispose.family((ref, String attemptId) async {
  return ApiService.instance.getAttempt(attemptId);
});
