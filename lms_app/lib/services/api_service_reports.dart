part of 'api_service.dart';

/// Everything read-only and derived: dashboards, certificates, diplomas, the parent portal, at-risk insight, fees, and curriculum standards.

extension ApiServiceReports on ApiService {
  // ==========================================================================
  // Phase 22 — Insight & intervention
  // ==========================================================================
  Future<List<AtRiskRow>> classAtRisk(String classId) async {
    final data = await _send('GET', '/classes/$classId/at-risk') as List<dynamic>;
    return data
        .map((e) => AtRiskRow.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<GradeHistory> myGradeHistory() async {
    final data = await _send('GET', '/students/mine/grade-history')
        as Map<String, dynamic>;
    return GradeHistory.fromJson(data);
  }

  Future<AttendancePatterns> attendancePatterns({int topN = 10}) async {
    final data = await _send('GET', '/attendance/patterns',
            query: {'topN': '$topN'}) as Map<String, dynamic>;
    return AttendancePatterns.fromJson(data);
  }

  // ==========================================================================
  // Phase 5 — Certificates
  // ==========================================================================
  Future<List<Certificate>> listMyCertificates() async {
    final data = await _send('GET', '/certificates/mine') as List<dynamic>;
    return data.map((e) => Certificate.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Certificate> getCertificate(String id) async {
    final data = await _send('GET', '/certificates/$id') as Map<String, dynamic>;
    return Certificate.fromJson(data);
  }

  /// URL for the browser / OS to fetch the PDF (uses session cookie).
  String certificatePdfUrl(String id) => '$baseUrl/certificates/$id/pdf';

  /// Phase 23 — direct-open URLs for the report card + transcript PDFs.
  /// Same auth caveat as the certificate PDF: the browser must carry
  /// the same session cookie the app is authenticated with, so this
  /// works cleanly when the Flutter web app and the backend share an
  /// origin (or the browser has an active login tab).
  String reportCardPdfUrl(String studentId, {String? termId}) {
    final q = termId != null ? '?termId=$termId' : '';
    return '$baseUrl/students/$studentId/report-card.pdf$q';
  }

  String transcriptPdfUrl(String studentId) =>
      '$baseUrl/students/$studentId/transcript.pdf';

  /// `POST /api/users/<id>/withdraw` — admin only.
  Future<Map<String, dynamic>> withdrawStudent(String studentId, {
    String? reason, DateTime? effectiveDate,
  }) async {
    final body = <String, dynamic>{
      'reason': ?reason,
      if (effectiveDate != null)
        'effectiveDate':
            '${effectiveDate.year}-${effectiveDate.month.toString().padLeft(2, '0')}-${effectiveDate.day.toString().padLeft(2, '0')}',
    };
    return await _send('POST', '/users/$studentId/withdraw', body: body)
        as Map<String, dynamic>;
  }

  Future<Certificate> revokeCertificate(String id, {required String reason}) async {
    final data = await _send('POST', '/certificates/$id/revoke',
        body: {'reason': reason}) as Map<String, dynamic>;
    return Certificate.fromJson(data);
  }

  /// Public verify — no auth required. Returns null on 404.
  Future<VerifyResult?> verifyCertificate(String certificateNumber) async {
    try {
      final data =
          await _send('GET', '/verify/$certificateNumber') as Map<String, dynamic>;
      return VerifyResult.fromJson(data);
    } on ApiException catch (e) {
      if (e.statusCode == 404) return null;
      rethrow;
    }
  }

  // ==========================================================================
  // Phase 7 — Dashboards & Reports
  // ==========================================================================
  Future<InstructorDashboard> getInstructorDashboard() async {
    final data = await _send('GET', '/dashboard/instructor') as Map<String, dynamic>;
    return InstructorDashboard.fromJson(data);
  }

  Future<CourseDrilldown> getInstructorCourseDrilldown(String courseId) async {
    final data = await _send('GET', '/dashboard/instructor/courses/$courseId')
        as Map<String, dynamic>;
    return CourseDrilldown.fromJson(data);
  }

  Future<AdminDashboard> getAdminDashboard() async {
    final data = await _send('GET', '/dashboard/admin') as Map<String, dynamic>;
    return AdminDashboard.fromJson(data);
  }

  // ==========================================================================
  // Phase 6 — Parent portal (read-only)
  // ==========================================================================
  Future<List<LinkedChild>> listMyChildren() async {
    final data = await _send('GET', '/parents/mine/children') as List<dynamic>;
    return data
        .map((e) => LinkedChild.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<ChildSummary> getChildSummary(String childId) async {
    final data = await _send(
      'GET', '/parents/mine/children/$childId/summary',
    ) as Map<String, dynamic>;
    return ChildSummary.fromJson(data);
  }

  Future<List<Enrollment>> getChildEnrollments(String childId) async {
    final data = await _send(
      'GET', '/parents/mine/children/$childId/enrollments',
    ) as List<dynamic>;
    return data
        .map((e) => Enrollment.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<QuizAttempt>> getChildQuizAttempts(String childId) async {
    final data = await _send(
      'GET', '/parents/mine/children/$childId/quiz-attempts',
    ) as List<dynamic>;
    return data
        .map((e) => QuizAttempt.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<List<Certificate>> getChildCertificates(String childId) async {
    final data = await _send(
      'GET', '/parents/mine/children/$childId/certificates',
    ) as List<dynamic>;
    return data
        .map((e) => Certificate.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  // ---- Admin-side link management --------------------------------------
  Future<List<StudentParent>> listStudentParents(String studentId) async {
    final data =
        await _send('GET', '/users/$studentId/parents') as List<dynamic>;
    return data
        .map((e) => StudentParent.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<void> linkParentToStudent({
    required String studentId,
    required String parentId,
    String relationship = 'guardian',
  }) async {
    await _send('POST', '/users/$studentId/parents', body: {
      'parentId': parentId,
      'relationship': relationship,
    });
  }

  Future<void> unlinkParentFromStudent({
    required String studentId,
    required String parentId,
  }) async {
    await _send('DELETE', '/users/$studentId/parents/$parentId');
  }

  Future<List<AppUser>> listParents({String? search}) async {
    final data = await _send(
      'GET', '/users/parents',
      query: (search == null || search.isEmpty) ? null : {'search': search},
    ) as List<dynamic>;
    return data.map((e) => AppUser.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<AppUser> adminCreateUser({
    required String name,
    required String email,
    required String password,
    required String role,
  }) async {
    final data = await _send('POST', '/users', body: {
      'name': name,
      'email': email,
      'password': password,
      'role': role,
    }) as Map<String, dynamic>;
    return AppUser.fromJson(data);
  }

  // ==========================================================================
  // Phase 32 · T1 — Notification preferences
  // ==========================================================================
  Future<({List<String> kinds, Map<String, bool> preferences})>
      getNotificationPreferences() async {
    final data = await _send('GET', '/notifications/preferences')
        as Map<String, dynamic>;
    final rawKinds = (data['kinds'] as List?) ?? const [];
    final rawPrefs = (data['preferences'] as Map?) ?? const {};
    return (
      kinds: rawKinds.map((e) => e.toString()).toList(),
      preferences: {
        for (final entry in rawPrefs.entries)
          entry.key.toString(): entry.value == true,
      },
    );
  }

  Future<({List<String> kinds, Map<String, bool> preferences})>
      updateNotificationPreferences(Map<String, bool> patch) async {
    final data = await _send(
      'PUT', '/notifications/preferences',
      body: {'preferences': patch},
    ) as Map<String, dynamic>;
    final rawKinds = (data['kinds'] as List?) ?? const [];
    final rawPrefs = (data['preferences'] as Map?) ?? const {};
    return (
      kinds: rawKinds.map((e) => e.toString()).toList(),
      preferences: {
        for (final entry in rawPrefs.entries)
          entry.key.toString(): entry.value == true,
      },
    );
  }

  // ==========================================================================
  // Phase 32 · T2 — Digital diploma
  // ==========================================================================
  Future<Diploma?> myDiploma() async {
    final data = await _send('GET', '/diplomas/mine') as Map<String, dynamic>;
    final d = data['diploma'];
    if (d == null) return null;
    return Diploma.fromJson(d as Map<String, dynamic>);
  }

  Future<Diploma?> studentDiploma(String studentId) async {
    final data = await _send('GET', '/students/$studentId/diploma')
        as Map<String, dynamic>;
    final d = data['diploma'];
    if (d == null) return null;
    return Diploma.fromJson(d as Map<String, dynamic>);
  }

  Future<Diploma> revokeDiploma(String diplomaId,
      {String? reason, bool restore = false}) async {
    final data = await _send('POST', '/diplomas/$diplomaId/revoke', body: {
      'reason': ?reason,
      if (restore) 'restore': true,
    }) as Map<String, dynamic>;
    return Diploma.fromJson(data);
  }

  String studentDiplomaPdfUrl(String studentId) =>
      '${AppConstants.apiBaseUrl}/students/$studentId/diploma.pdf';

  String verifyDiplomaUrl(String diplomaNumber) =>
      '${AppConstants.apiBaseUrl}/verify-diploma/$diplomaNumber';

  // ==========================================================================
  // Phase 32 · T3 — Curriculum standards + student mastery
  // ==========================================================================
  Future<List<Standard>> listStandards({String? subject}) async {
    final data = await _send(
      'GET', '/standards',
      query: {if (subject != null && subject.isNotEmpty) 'subject': subject},
    ) as List<dynamic>;
    return data
        .map((e) => Standard.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Standard> createStandard({
    required String code,
    required String name,
    String description = '',
    String? subject,
  }) async {
    final data = await _send('POST', '/standards', body: {
      'code': code,
      'name': name,
      'description': description,
      if (subject != null && subject.isNotEmpty) 'subject': subject,
    }) as Map<String, dynamic>;
    return Standard.fromJson(data);
  }

  Future<void> deleteStandard(String id) async {
    await _send('DELETE', '/standards/$id');
  }

  Future<Map<String, dynamic>> tagStandard(
    String standardId, {
    required String taggableType,
    required String taggableId,
  }) async {
    return await _send('POST', '/standards/$standardId/tags', body: {
      'taggableType': taggableType,
      'taggableId': taggableId,
    }) as Map<String, dynamic>;
  }

  Future<void> untagStandard(String tagId) async {
    await _send('DELETE', '/standard-tags/$tagId');
  }

  Future<List<StandardMastery>> studentStandardsMastery(
    String studentId,
  ) async {
    final data = await _send(
      'GET', '/students/$studentId/standards-mastery',
    ) as Map<String, dynamic>;
    final rows = (data['standards'] as List?) ?? const [];
    return rows
        .map((e) => StandardMastery.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<FeeItem> createFee(
    String studentId, {
    required String label,
    required double amount,
    String currency = 'USD',
    DateTime? dueDate,
    String? notes,
  }) async {
    final data = await _send('POST', '/students/$studentId/fees', body: {
      'label': label,
      'amount': amount,
      'currency': currency,
      if (dueDate != null)
        'dueDate':
            '${dueDate.year}-${dueDate.month.toString().padLeft(2, '0')}-${dueDate.day.toString().padLeft(2, '0')}',
      if (notes != null && notes.isNotEmpty) 'notes': notes,
    }) as Map<String, dynamic>;
    return FeeItem.fromJson(data);
  }

  Future<FeeItem> updateFee(
    String feeId, {
    String? label,
    double? amount,
    DateTime? dueDate,
    bool clearDueDate = false,
    String? notes,
  }) async {
    final body = <String, dynamic>{
      'label': ?label,
      'amount': ?amount,
      if (dueDate != null)
        'dueDate':
            '${dueDate.year}-${dueDate.month.toString().padLeft(2, '0')}-${dueDate.day.toString().padLeft(2, '0')}',
      if (clearDueDate) 'dueDate': null,
      'notes': ?notes,
    };
    final data = await _send('PUT', '/fees/$feeId', body: body)
        as Map<String, dynamic>;
    return FeeItem.fromJson(data);
  }

  Future<void> deleteFee(String feeId) async {
    await _send('DELETE', '/fees/$feeId');
  }

  Future<FeeItem> logFeePayment(
    String feeId, {
    required double amount,
    String? method,
    String? note,
  }) async {
    final data = await _send('POST', '/fees/$feeId/payments', body: {
      'amount': amount,
      if (method != null && method.isNotEmpty) 'method': method,
      if (note != null && note.isNotEmpty) 'note': note,
    }) as Map<String, dynamic>;
    return FeeItem.fromJson(data['fee'] as Map<String, dynamic>);
  }

  Future<void> deleteFeePayment(String paymentId) async {
    await _send('DELETE', '/fee-payments/$paymentId');
  }

  /// Full URL for launching the fees PDF in a browser tab. Same shape
  /// as `reportCardPdfUrl` — the endpoint needs the caller's session
  /// cookie via the `?session=` query param the client attaches.
  String feesPdfUrl(String studentId) =>
      '${AppConstants.apiBaseUrl}/students/$studentId/fees.pdf';

  Future<CohortComparison> getCohortComparison({
    required String termAId,
    required String termBId,
  }) async {
    final data = await _send(
      'GET',
      '/dashboards/cohort-comparison?termAId=$termAId&termBId=$termBId',
    ) as Map<String, dynamic>;
    return CohortComparison.fromJson(data);
  }

  Future<QuizAttempt> overrideAttemptScore(
    String attemptId, {
    required double finalScore,
    String? reason,
    List<Map<String, dynamic>>? perQuestionScores,
  }) async {
    final data = await _send('POST', '/quiz-attempts/$attemptId/override', body: {
      'finalScore': finalScore,
      'reason': ?reason,
      'perQuestionScores': ?perQuestionScores,
    }) as Map<String, dynamic>;
    return QuizAttempt.fromJson(data);
  }
}
