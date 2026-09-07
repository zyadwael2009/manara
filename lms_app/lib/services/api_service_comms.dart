part of 'api_service.dart';

/// Notifications, direct messages, lesson comments, the homework board, and announcements.

extension ApiServiceComms on ApiService {
  // ==========================================================================
  // Phase 21 — Notifications, DMs, lesson comments, homework board
  // ==========================================================================
  Future<NotificationsPage> myNotifications({
    int limit = 50,
    bool unreadOnly = false,
    // Phase 29 · T3 — optional pagination. When `page` OR `pageSize`
    // is supplied, the server ignores `limit` and returns the paged
    // envelope (`page/pageSize/hasMore` fields still parse into the
    // existing `NotificationsPage` shape via the shared paginator's
    // back-compat aliasing). Legacy callers can keep passing `limit`.
    int? page,
    int? pageSize,
  }) async {
    final data = await _send(
      'GET', '/notifications/mine',
      query: {
        if (page != null || pageSize != null) ...{
          'page': '${page ?? 1}',
          'pageSize': '${pageSize ?? 20}',
        } else
          'limit': '$limit',
        if (unreadOnly) 'unreadOnly': 'true',
      },
    ) as Map<String, dynamic>;
    return NotificationsPage.fromJson(data);
  }

  Future<int> markNotificationsRead({List<String>? ids, bool all = false}) async {
    final body = <String, dynamic>{if (all) 'all': true, 'ids': ?ids};
    final data = await _send('POST', '/notifications/mark-read', body: body)
        as Map<String, dynamic>;
    return (data['unreadCount'] as num?)?.toInt() ?? 0;
  }

  Future<List<MessageThreadSummary>> myMessageThreads() async {
    final data = await _send('GET', '/messages/threads/mine') as List<dynamic>;
    return data
        .map((e) => MessageThreadSummary.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<MessageThreadPage> getMessageThread(String id) async {
    final data = await _send('GET', '/messages/threads/$id')
        as Map<String, dynamic>;
    return MessageThreadPage.fromJson(data);
  }

  Future<MessageThreadPage> createMessageThread({
    required String recipientId,
    required String subject,
    required String body,
  }) async {
    final data = await _send('POST', '/messages/threads', body: {
      'recipientId': recipientId, 'subject': subject, 'body': body,
    }) as Map<String, dynamic>;
    return MessageThreadPage(
      thread: MessageThreadSummary.fromJson(
          data['thread'] as Map<String, dynamic>),
      messages: [
        DmMessage.fromJson(data['message'] as Map<String, dynamic>),
      ],
    );
  }

  Future<DmMessage> replyMessageThread(String threadId, String body) async {
    final data = await _send('POST', '/messages/threads/$threadId/messages',
            body: {'body': body}) as Map<String, dynamic>;
    return DmMessage.fromJson(data);
  }

  Future<List<LessonComment>> listLessonComments(String lessonId) async {
    final data = await _send('GET', '/lessons/$lessonId/comments')
        as List<dynamic>;
    return data
        .map((e) => LessonComment.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<LessonComment> postLessonComment({
    required String lessonId,
    required String body,
    String? parentCommentId,
  }) async {
    final data = await _send('POST', '/lessons/$lessonId/comments', body: {
      'body': body,
      'parentCommentId': ?parentCommentId,
    }) as Map<String, dynamic>;
    return LessonComment.fromJson(data);
  }

  Future<void> deleteLessonComment(String commentId) async {
    await _send('DELETE', '/comments/$commentId');
  }

  Future<List<HomeworkPost>> listHomework(
    String classId, {
    DateTime? from,
    DateTime? to,
  }) async {
    String yyyymmdd(DateTime d) =>
        '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    final data = await _send('GET', '/classes/$classId/homework', query: {
      if (from != null) 'from': yyyymmdd(from),
      if (to != null) 'to': yyyymmdd(to),
    }) as List<dynamic>;
    return data
        .map((e) => HomeworkPost.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<HomeworkPost> upsertHomework({
    required String classId,
    required DateTime date,
    required String title,
    String body = '',
  }) async {
    final yyyymmdd =
        '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
    final data = await _send(
      'PUT', '/classes/$classId/homework/$yyyymmdd',
      body: {'title': title, 'body': body},
    ) as Map<String, dynamic>;
    return HomeworkPost.fromJson(data);
  }

  Future<void> deleteHomework(String classId, DateTime date) async {
    final yyyymmdd =
        '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
    await _send('DELETE', '/classes/$classId/homework/$yyyymmdd');
  }

  // ==========================================================================
  // Phase 19 — Announcements + quiz-attempts stats
  // ==========================================================================
  Future<List<Announcement>> myAnnouncements({int limit = 50}) async {
    final data = await _send(
      'GET', '/announcements/mine',
      query: {'limit': '$limit'},
    ) as List<dynamic>;
    return data
        .map((e) => Announcement.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Announcement> createAnnouncement(AnnouncementInput input) async {
    final data = await _send('POST', '/announcements', body: input.toJson())
        as Map<String, dynamic>;
    return Announcement.fromJson(data);
  }

  Future<void> deleteAnnouncement(String id) async {
    await _send('DELETE', '/announcements/$id');
  }

  Future<QuizAttemptStats> getQuizAttemptStats(String quizId) async {
    final data = await _send('GET', '/quizzes/$quizId/attempts/stats')
        as Map<String, dynamic>;
    return QuizAttemptStats.fromJson(data);
  }

  /// Phase 18 — student "Today" landing: today's periods, assignments
  /// due today, and open quizzes with attempts remaining. One round trip.
  Future<TodayView> getToday() async {
    final data = await _send('GET', '/students/today') as Map<String, dynamic>;
    return TodayView.fromJson(data);
  }

  /// Phase 18 — every published assignment across the caller's live
  /// enrollments, with per-row submission state + course context.
  Future<List<MyAssignmentRow>> myAssignmentsAll() async {
    final data = await _send('GET', '/assignments/my') as List<dynamic>;
    return data
        .map((e) => MyAssignmentRow.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  /// Phase 16 — the student "Quizzes" hub: every published quiz across
  /// the caller's live enrollments, plus their own attempt history for each.
  Future<List<MyQuizRow>> myQuizzesAll() async {
    final data = await _send('GET', '/quizzes/my') as List<dynamic>;
    return data
        .map((e) => MyQuizRow.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<QuizAttempt>> myAttempts(String quizId) async {
    final data = await _send('GET', '/quizzes/$quizId/my-attempts') as List<dynamic>;
    return data.map((e) => QuizAttempt.fromJson(e as Map<String, dynamic>)).toList();
  }

  // ==========================================================================
  // Phase 28 — Web push, fees, cohort comparison
  // ==========================================================================
  Future<({bool pushEnabled, String? publicKey})> getPushPublicKey() async {
    final data = await _send('GET', '/push/public-key') as Map<String, dynamic>;
    return (
      pushEnabled: (data['pushEnabled'] as bool?) ?? false,
      publicKey: data['publicKey'] as String?,
    );
  }

  Future<Map<String, dynamic>> pushSubscribe({
    required String endpoint,
    required String p256dh,
    required String auth,
    String? userAgent,
  }) async {
    return await _send('POST', '/push/subscribe', body: {
      'endpoint': endpoint,
      'keys': {'p256dh': p256dh, 'auth': auth},
      'userAgent': ?userAgent,
      'platform': 'web',
    }) as Map<String, dynamic>;
  }

  /// Phase 30 · T6 — mobile shape. `platform` is either "fcm" or
  /// "apns"; the server stores the token in the `endpoint` column and
  /// routes deliveries through `utils/push.py::send_mobile_push` once
  /// the Firebase service-account JSON is dropped in place.
  Future<Map<String, dynamic>> pushSubscribeMobile({
    required String token,
    required String platform,
  }) async {
    return await _send('POST', '/push/subscribe', body: {
      'token': token,
      'platform': platform,
    }) as Map<String, dynamic>;
  }

  Future<void> pushUnsubscribe(String endpoint) async {
    await _send('POST', '/push/unsubscribe', body: {'endpoint': endpoint});
  }

  Future<FeeStatement> listStudentFees(String studentId) async {
    final data = await _send('GET', '/students/$studentId/fees')
        as Map<String, dynamic>;
    return FeeStatement.fromJson(data);
  }

  Future<FeeStatement> listMyFees() async {
    final data = await _send('GET', '/fees/mine') as Map<String, dynamic>;
    return FeeStatement.fromJson(data);
  }

  /// Phase 30 · T2 — compact rollup for the student home chip.
  /// Returns `(outstanding, overdueCount, currency)`.
  Future<({double outstanding, int overdueCount, String currency})>
      getMyFeeSummary() async {
    final data =
        await _send('GET', '/fees/summary') as Map<String, dynamic>;
    return (
      outstanding: (data['outstanding'] as num?)?.toDouble() ?? 0.0,
      overdueCount: (data['overdueCount'] as num?)?.toInt() ?? 0,
      currency: (data['currency'] as String?) ?? 'USD',
    );
  }

  /// Phase 31 · T2 — parent-portal per-child fee summary. Same shape
  /// as `getMyFeeSummary`. Read-scope reuses the same rule as
  /// `listStudentFees` (admin / student-self / linked-parent).
  Future<({double outstanding, int overdueCount, String currency})>
      getStudentFeeSummary(String studentId) async {
    final data = await _send('GET', '/students/$studentId/fees/summary')
        as Map<String, dynamic>;
    return (
      outstanding: (data['outstanding'] as num?)?.toDouble() ?? 0.0,
      overdueCount: (data['overdueCount'] as num?)?.toInt() ?? 0,
      currency: (data['currency'] as String?) ?? 'USD',
    );
  }

  /// Phase 31 · T1 — admin trigger for the overdue-fee reminder sweep.
  /// Idempotent by day (server-side dedupe); returns reminder count.
  Future<int> sendOverdueFeeReminders() async {
    final data = await _send('POST', '/fees/send-overdue-reminders')
        as Map<String, dynamic>;
    return (data['reminded'] as num?)?.toInt() ?? 0;
  }

  /// Phase 31 · T3 — cohort comparison PDF URL (for `launchUrl`).
  String cohortComparisonPdfUrl({
    required String termAId,
    required String termBId,
  }) =>
      '${AppConstants.apiBaseUrl}/dashboards/cohort-comparison.pdf'
      '?termAId=$termAId&termBId=$termBId';
}
