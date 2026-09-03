import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/comm.dart';
import '../services/api_service.dart';

/// Phase 21 — the caller's notification inbox. Auto-refreshes whenever
/// invalidated; UI is expected to poll every few minutes AND after any
/// action that could have queued a write.
final myNotificationsProvider =
    FutureProvider.autoDispose<NotificationsPage>((ref) async {
  return ApiService.instance.myNotifications();
});

/// Message threads (parent OR teacher view — the server scopes it).
final myThreadsProvider =
    FutureProvider.autoDispose<List<MessageThreadSummary>>((ref) async {
  return ApiService.instance.myMessageThreads();
});

/// One thread's history. Reading marks the OTHER party's messages as
/// read server-side, so invalidate after reading changes unread-count.
final messageThreadProvider = FutureProvider.autoDispose
    .family<MessageThreadPage, String>((ref, threadId) async {
  return ApiService.instance.getMessageThread(threadId);
});

/// Comments under one lesson.
final lessonCommentsProvider =
    FutureProvider.autoDispose.family<List<LessonComment>, String>(
        (ref, lessonId) async {
  return ApiService.instance.listLessonComments(lessonId);
});

/// Homework posts for a class in a window (from/to are 7 days back / 14
/// days forward by default). Family key is class id.
final classHomeworkProvider = FutureProvider.autoDispose
    .family<List<HomeworkPost>, String>((ref, classId) async {
  return ApiService.instance.listHomework(classId);
});
