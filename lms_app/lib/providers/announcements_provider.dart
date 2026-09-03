import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/announcement.dart';
import '../services/api_service.dart';

/// Phase 19 — the caller's audience-scoped announcement feed. Student /
/// parent get their child+course fan-out; teacher / admin get their own
/// authored posts.
final myAnnouncementsProvider =
    FutureProvider.autoDispose<List<Announcement>>((ref) async {
  return ApiService.instance.myAnnouncements();
});

/// Class-average stats for one quiz, used by the teacher's attempts screen.
final quizAttemptStatsProvider =
    FutureProvider.autoDispose.family<QuizAttemptStats, String>((ref, quizId) async {
  return ApiService.instance.getQuizAttemptStats(quizId);
});
