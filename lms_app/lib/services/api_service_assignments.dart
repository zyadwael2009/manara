part of 'api_service.dart';

/// Assignments, submissions, grading, and group work.

extension ApiServiceAssignments on ApiService {
  // ==========================================================================
  // Phase 14 — Assignments
  // ==========================================================================
  Future<List<Assignment>> listCourseAssignments(String courseId) async {
    final data = await _send('GET', '/courses/$courseId/assignments')
        as List<dynamic>;
    return data.map((e) => Assignment.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Assignment> getAssignment(String assignmentId) async {
    final data = await _send('GET', '/assignments/$assignmentId')
        as Map<String, dynamic>;
    return Assignment.fromJson(data);
  }

  Future<Assignment> createAssignment(
    String moduleId, {
    required String title,
    String description = '',
    DateTime? dueAt,
    int maxPoints = 100,
    bool allowText = true,
    bool allowFile = true,
    // Phase 27 — group-mode options.
    bool isGroup = false,
    int? maxGroupSize,
  }) async {
    final data = await _send('POST', '/modules/$moduleId/assignments', body: {
      'title': title,
      'description': description,
      'maxPoints': maxPoints,
      'allowText': allowText,
      'allowFile': allowFile,
      if (dueAt != null) 'dueAt': dueAt.toIso8601String(),
      if (isGroup) 'isGroup': true,
      if (isGroup && maxGroupSize != null) 'maxGroupSize': maxGroupSize,
    }) as Map<String, dynamic>;
    return Assignment.fromJson(data);
  }

  Future<Assignment> updateAssignment(
    String id, {
    String? title,
    String? description,
    DateTime? dueAt,
    int? maxPoints,
    bool? allowText,
    bool? allowFile,
    // Phase 27 — group-mode toggles.
    bool? isGroup,
    int? maxGroupSize,
    bool clearMaxGroupSize = false,
  }) async {
    final body = <String, dynamic>{
      'title': ?title,
      'description': ?description,
      if (dueAt != null) 'dueAt': dueAt.toIso8601String(),
      'maxPoints': ?maxPoints,
      'allowText': ?allowText,
      'allowFile': ?allowFile,
      'isGroup': ?isGroup,
      'maxGroupSize': ?maxGroupSize,
      if (clearMaxGroupSize) 'maxGroupSize': null,
    };
    final data = await _send('PUT', '/assignments/$id', body: body)
        as Map<String, dynamic>;
    return Assignment.fromJson(data);
  }

  Future<void> deleteAssignment(String id) async {
    await _send('DELETE', '/assignments/$id');
  }

  Future<Assignment> publishAssignment(String id) async {
    final data = await _send('POST', '/assignments/$id/publish')
        as Map<String, dynamic>;
    return Assignment.fromJson(data);
  }

  Future<Assignment> unpublishAssignment(String id) async {
    final data = await _send('POST', '/assignments/$id/unpublish')
        as Map<String, dynamic>;
    return Assignment.fromJson(data);
  }

  Future<AssignmentSubmission> submitAssignment(
    String assignmentId, {
    String? responseText,
    String? fileUrl,
    String? fileKind,
  }) async {
    final data = await _send(
      'POST', '/assignments/$assignmentId/submissions',
      body: {
        'responseText': ?responseText,
        'fileUrl': ?fileUrl,
        'fileKind': ?fileKind,
      },
    ) as Map<String, dynamic>;
    return AssignmentSubmission.fromJson(data);
  }

  Future<List<AssignmentSubmission>> listAssignmentSubmissions(
    String assignmentId,
  ) async {
    final data = await _send('GET', '/assignments/$assignmentId/submissions')
        as List<dynamic>;
    return data
        .map((e) => AssignmentSubmission.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<AssignmentSubmission> gradeSubmission(
    String submissionId, {
    required double score,
    String? feedback,
  }) async {
    final data = await _send('PUT', '/submissions/$submissionId/grade', body: {
      'score': score,
      if (feedback != null && feedback.isNotEmpty) 'feedback': feedback,
    }) as Map<String, dynamic>;
    return AssignmentSubmission.fromJson(data);
  }

  // ==========================================================================
  // Phase 27 — Group assignments
  // ==========================================================================
  Future<({List<AssignmentGroup> groups, bool isGroup, int? maxSize})>
      listAssignmentGroups(String assignmentId) async {
    final data = await _send('GET', '/assignments/$assignmentId/groups')
        as Map<String, dynamic>;
    final raw = (data['groups'] as List?) ?? const [];
    return (
      groups: raw
          .whereType<Map<String, dynamic>>()
          .map(AssignmentGroup.fromJson)
          .toList(),
      isGroup: (data['isGroup'] as bool?) ?? false,
      maxSize: (data['maxGroupSize'] as num?)?.toInt(),
    );
  }

  Future<AssignmentGroup> createAssignmentGroup(
    String assignmentId, {
    required String name,
  }) async {
    final data = await _send('POST', '/assignments/$assignmentId/groups', body: {
      'name': name,
    }) as Map<String, dynamic>;
    return AssignmentGroup.fromJson(data);
  }

  Future<AssignmentGroup> joinAssignmentGroup(String groupId) async {
    final data = await _send('POST', '/assignment-groups/$groupId/join')
        as Map<String, dynamic>;
    return AssignmentGroup.fromJson(data);
  }

  Future<void> leaveAssignmentGroup(String groupId) async {
    await _send('POST', '/assignment-groups/$groupId/leave');
  }

  Future<void> deleteAssignmentGroup(String groupId) async {
    await _send('DELETE', '/assignment-groups/$groupId');
  }
}
