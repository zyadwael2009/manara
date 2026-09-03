import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/gamify.dart';
import '../services/api_service.dart';

/// Phase 24 — student's current streak. Ticks fired by the caller
/// (typically once per session start).
final myStreakProvider =
    FutureProvider.autoDispose<StreakState>((ref) async {
  return ApiService.instance.getStreak();
});

/// Computed-on-the-fly badges for the caller.
final myBadgesProvider =
    FutureProvider.autoDispose<BadgesPage>((ref) async {
  return ApiService.instance.getMyBadges();
});

/// Question-bank rows for a course (family key = course id).
final questionBankProvider =
    FutureProvider.autoDispose.family<List<QuestionBankItem>, String>(
        (ref, courseId) async {
  return ApiService.instance.listQuestionBank(courseId);
});
