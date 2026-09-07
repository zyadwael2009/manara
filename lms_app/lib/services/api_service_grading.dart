part of 'api_service.dart';

/// School years and terms, rubrics, the gradebook and report cards.

extension ApiServiceGrading on ApiService {
  // ==========================================================================
  // Phase 3 — Grading admin: school years
  // ==========================================================================
  Future<List<SchoolYear>> listSchoolYears() async {
    final data = await _send('GET', '/school-years') as List<dynamic>;
    return data.map((e) => SchoolYear.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<SchoolYear> createSchoolYear({
    required String name,
    String? startDate,
    String? endDate,
    bool isCurrent = false,
  }) async {
    final data = await _send('POST', '/school-years', body: {
      'name': name,
      'startDate': ?startDate,
      'endDate': ?endDate,
      'isCurrent': isCurrent,
    }) as Map<String, dynamic>;
    return SchoolYear.fromJson(data);
  }

  Future<SchoolYear> updateSchoolYear(String id,
      {String? name, String? startDate, String? endDate, bool? isCurrent}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (startDate != null) body['startDate'] = startDate;
    if (endDate != null) body['endDate'] = endDate;
    if (isCurrent != null) body['isCurrent'] = isCurrent;
    final data = await _send('PUT', '/school-years/$id', body: body) as Map<String, dynamic>;
    return SchoolYear.fromJson(data);
  }

  Future<void> deleteSchoolYear(String id) => _send('DELETE', '/school-years/$id');

  // Terms
  Future<List<Term>> listTerms(String yearId) async {
    final data = await _send('GET', '/school-years/$yearId/terms') as List<dynamic>;
    return data.map((e) => Term.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Term> createTerm(String yearId,
      {required String name, int orderIndex = 0, String? startDate, String? endDate}) async {
    final data = await _send('POST', '/school-years/$yearId/terms', body: {
      'name': name,
      'orderIndex': orderIndex,
      'startDate': ?startDate,
      'endDate': ?endDate,
    }) as Map<String, dynamic>;
    return Term.fromJson(data);
  }

  Future<Term> updateTerm(String id, {String? name, int? orderIndex}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (orderIndex != null) body['orderIndex'] = orderIndex;
    final data = await _send('PUT', '/terms/$id', body: body) as Map<String, dynamic>;
    return Term.fromJson(data);
  }

  Future<void> deleteTerm(String id) => _send('DELETE', '/terms/$id');

  Future<Term> lockTerm(String id) async {
    final data = await _send('POST', '/terms/$id/lock') as Map<String, dynamic>;
    return Term.fromJson(data);
  }

  Future<Term> unlockTerm(String id) async {
    final data = await _send('POST', '/terms/$id/unlock') as Map<String, dynamic>;
    return Term.fromJson(data);
  }

  // Grade categories
  Future<List<GradeCategory>> listGradeCategories() async {
    final data = await _send('GET', '/grade-categories') as List<dynamic>;
    return data.map((e) => GradeCategory.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<GradeCategory> createGradeCategory({required String name, String? slug}) async {
    final data = await _send('POST', '/grade-categories', body: {
      'name': name,
      'slug': ?slug,
    }) as Map<String, dynamic>;
    return GradeCategory.fromJson(data);
  }

  Future<GradeCategory> updateGradeCategory(String id, {String? name, int? orderIndex}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (orderIndex != null) body['orderIndex'] = orderIndex;
    final data = await _send('PUT', '/grade-categories/$id', body: body) as Map<String, dynamic>;
    return GradeCategory.fromJson(data);
  }

  Future<void> deleteGradeCategory(String id) => _send('DELETE', '/grade-categories/$id');

  // Grading scale
  Future<List<GradingScaleBand>> listGradingScale() async {
    final data = await _send('GET', '/grading-scale') as List<dynamic>;
    return data.map((e) => GradingScaleBand.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<GradingScaleBand> createGradingBand({
    required int minPercent,
    required int maxPercent,
    required String letter,
    required double gpaValue,
  }) async {
    final data = await _send('POST', '/grading-scale', body: {
      'minPercent': minPercent,
      'maxPercent': maxPercent,
      'letter': letter,
      'gpaValue': gpaValue,
    }) as Map<String, dynamic>;
    return GradingScaleBand.fromJson(data);
  }

  Future<GradingScaleBand> updateGradingBand(
    String id, {
    int? minPercent,
    int? maxPercent,
    String? letter,
    double? gpaValue,
  }) async {
    final body = <String, dynamic>{};
    if (minPercent != null) body['minPercent'] = minPercent;
    if (maxPercent != null) body['maxPercent'] = maxPercent;
    if (letter != null) body['letter'] = letter;
    if (gpaValue != null) body['gpaValue'] = gpaValue;
    final data = await _send('PUT', '/grading-scale/$id', body: body) as Map<String, dynamic>;
    return GradingScaleBand.fromJson(data);
  }

  Future<void> deleteGradingBand(String id) => _send('DELETE', '/grading-scale/$id');

  // ==========================================================================
  // Phase 3 — Rubrics
  // ==========================================================================
  Future<List<RubricItem>> getRubric(String courseId) async {
    final data = await _send('GET', '/courses/$courseId/rubric') as List<dynamic>;
    return data.map((e) => RubricItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Map<String, dynamic>> setRubric(String courseId, List<Map<String, dynamic>> items) async {
    final data = await _send('PUT', '/courses/$courseId/rubric', body: {
      'items': items,
    }) as Map<String, dynamic>;
    return data;
  }

  // ==========================================================================
  // Phase 3 — Gradebook + report cards
  // ==========================================================================
  Future<Gradebook> getGradebook({
    required String classId,
    required String courseId,
    required String termId,
  }) async {
    final data = await _send(
      'GET',
      '/classes/$classId/gradebook',
      query: {'courseId': courseId, 'termId': termId},
    ) as Map<String, dynamic>;
    return Gradebook.fromJson(data);
  }

  Future<void> putGrades(
    String enrollmentId, {
    required String termId,
    required List<Map<String, dynamic>> entries,
  }) async {
    await _send('PUT', '/enrollments/$enrollmentId/grades', body: {
      'termId': termId,
      'entries': entries,
    });
  }

  Future<ReportCard> getMyReportCard({String? termId}) async {
    final data = await _send(
      'GET',
      '/reports/mine',
      query: termId != null ? {'termId': termId} : null,
    ) as Map<String, dynamic>;
    return ReportCard.fromJson(data);
  }

  Future<ReportCard> getStudentReportCard(String studentId, {String? termId}) async {
    final data = await _send(
      'GET',
      '/reports/students/$studentId',
      query: termId != null ? {'termId': termId} : null,
    ) as Map<String, dynamic>;
    return ReportCard.fromJson(data);
  }
}
