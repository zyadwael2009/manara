part of 'api_service.dart';

/// Course catalogue, modules, lessons, uploads, lesson progress and the in-video checkpoints attached to them.

extension ApiServiceContent on ApiService {
  // ==========================================================================
  // Courses (unchanged calls + gradeId/electiveGroup on create)
  // ==========================================================================
  Future<List<Course>> listCourses({String? search, String? category, String? gradeId}) async {
    final q = <String, String>{};
    if (search != null && search.isNotEmpty) q['search'] = search;
    if (category != null && category.isNotEmpty) q['category'] = category;
    if (gradeId != null && gradeId.isNotEmpty) q['gradeId'] = gradeId;
    final data = await _send('GET', '/courses', query: q) as List<dynamic>;
    return data.map((e) => Course.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<Course>> listMyCourses() async {
    final data = await _send('GET', '/courses/mine') as List<dynamic>;
    return data.map((e) => Course.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Course> getCourse(String id) async {
    final data = await _send('GET', '/courses/$id') as Map<String, dynamic>;
    return Course.fromJson(data);
  }

  Future<Course> createCourse({
    required String title,
    required String gradeId,
    String description = '',
    String category = 'general',
    String? electiveGroup,
    String? thumbnailUrl,
  }) async {
    final data = await _send('POST', '/courses', body: {
      'title': title,
      'gradeId': gradeId,
      'description': description,
      'category': category,
      if (electiveGroup != null && electiveGroup.isNotEmpty) 'electiveGroup': electiveGroup,
      if (thumbnailUrl != null && thumbnailUrl.isNotEmpty) 'thumbnailUrl': thumbnailUrl,
    }) as Map<String, dynamic>;
    return Course.fromJson(data);
  }

  Future<Course> updateCourse(String id,
      {String? title, String? description, String? category, String? electiveGroup, String? thumbnailUrl}) async {
    final body = <String, dynamic>{};
    if (title != null) body['title'] = title;
    if (description != null) body['description'] = description;
    if (category != null) body['category'] = category;
    if (electiveGroup != null) body['electiveGroup'] = electiveGroup;
    if (thumbnailUrl != null) body['thumbnailUrl'] = thumbnailUrl;
    final data = await _send('PUT', '/courses/$id', body: body) as Map<String, dynamic>;
    return Course.fromJson(data);
  }

  Future<void> deleteCourse(String id) => _send('DELETE', '/courses/$id');

  Future<Course> publishCourse(String id) async {
    final data = await _send('POST', '/courses/$id/publish') as Map<String, dynamic>;
    return Course.fromJson(data);
  }

  Future<Course> unpublishCourse(String id) async {
    final data = await _send('POST', '/courses/$id/unpublish') as Map<String, dynamic>;
    return Course.fromJson(data);
  }

  // ==========================================================================
  // Modules & lessons
  // ==========================================================================
  Future<CourseModule> createModule(String courseId, {required String title}) async {
    final data = await _send('POST', '/courses/$courseId/modules', body: {'title': title})
        as Map<String, dynamic>;
    return CourseModule.fromJson(data);
  }

  Future<void> deleteModule(String id) => _send('DELETE', '/modules/$id');

  Future<Lesson> getLesson(String id) async {
    final data = await _send('GET', '/lessons/$id') as Map<String, dynamic>;
    return Lesson.fromJson(data);
  }

  Future<Lesson> createLesson(
    String moduleId, {
    required String title,
    required String type,
    String? contentUrl,
    String? contentText,
    int? durationMinutes,
  }) async {
    final data = await _send('POST', '/modules/$moduleId/lessons', body: {
      'title': title,
      'type': type,
      'contentUrl': ?contentUrl,
      'contentText': ?contentText,
      'durationMinutes': ?durationMinutes,
    }) as Map<String, dynamic>;
    return Lesson.fromJson(data);
  }

  Future<Lesson> updateLesson(
    String id, {
    String? title,
    String? type,
    String? contentUrl,
    String? contentText,
    int? durationMinutes,
    int? orderIndex,
  }) async {
    final body = <String, dynamic>{};
    if (title != null) body['title'] = title;
    if (type != null) body['type'] = type;
    if (contentUrl != null) body['contentUrl'] = contentUrl;
    if (contentText != null) body['contentText'] = contentText;
    if (durationMinutes != null) body['durationMinutes'] = durationMinutes;
    if (orderIndex != null) body['orderIndex'] = orderIndex;
    final data = await _send('PUT', '/lessons/$id', body: body) as Map<String, dynamic>;
    return Lesson.fromJson(data);
  }

  Future<void> deleteLesson(String id) => _send('DELETE', '/lessons/$id');

  Future<List<Enrollment>> listStudentEnrollments(String studentId) async {
    final data = await _send('GET', '/users/$studentId/enrollments') as List<dynamic>;
    return data.map((e) => Enrollment.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// Phase 20 — admin CSV bulk-import of users. Multipart POST of a
  /// text/csv payload; server returns a per-row envelope of
  /// created / updated / skipped / errors.
  Future<BulkImportResult> uploadBulkUsers(PlatformFile file) async {
    final uri = Uri.parse('$baseUrl/admin/users/import');
    final req = http.MultipartRequest('POST', uri);
    final token = _sessionToken ?? StorageService.instance.getSessionToken();
    if (token != null) req.headers['X-Session-Token'] = token;
    if (file.bytes != null) {
      req.files.add(http.MultipartFile.fromBytes(
        'file',
        file.bytes!,
        filename: file.name.isEmpty ? 'roster.csv' : file.name,
        contentType: MediaType('text', 'csv'),
      ));
    } else if (file.path != null) {
      req.files.add(await http.MultipartFile.fromPath(
        'file',
        file.path!,
        filename: file.name.isEmpty ? 'roster.csv' : file.name,
        contentType: MediaType('text', 'csv'),
      ));
    } else {
      throw ApiException(0, 'File has no bytes or path.');
    }
    final streamed = await _client.send(req);
    final resp = await http.Response.fromStream(streamed);
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      String msg = 'Import failed (${resp.statusCode}).';
      try {
        final decoded = jsonDecode(resp.body);
        if (decoded is Map && decoded['error'] is String) msg = decoded['error'];
      } catch (_) {}
      throw ApiException(resp.statusCode, msg);
    }
    return BulkImportResult.fromJson(jsonDecode(resp.body) as Map<String, dynamic>);
  }

  // ==========================================================================
  // Uploads
  // ==========================================================================
  Future<UploadResult> uploadFile({
    required String kind, // video | pdf | image
    required PlatformFile file,
  }) async {
    final uri = Uri.parse('$baseUrl/uploads');
    final req = http.MultipartRequest('POST', uri);
    final token = _sessionToken ?? StorageService.instance.getSessionToken();
    if (token != null) req.headers['X-Session-Token'] = token;
    req.fields['kind'] = kind;

    if (file.bytes != null) {
      req.files.add(http.MultipartFile.fromBytes(
        'file',
        file.bytes!,
        filename: file.name,
        contentType: _guessMediaType(kind, file.name),
      ));
    } else if (file.path != null) {
      req.files.add(await http.MultipartFile.fromPath(
        'file',
        file.path!,
        filename: file.name,
        contentType: _guessMediaType(kind, file.name),
      ));
    } else {
      throw ApiException(0, 'File has no bytes or path.');
    }

    final streamed = await _client.send(req);
    final resp = await http.Response.fromStream(streamed);
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      String msg = 'Upload failed (${resp.statusCode}).';
      try {
        final decoded = jsonDecode(resp.body);
        if (decoded is Map && decoded['error'] is String) msg = decoded['error'];
      } catch (_) {}
      throw ApiException(resp.statusCode, msg);
    }
    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    return UploadResult(
      url: data['url'] as String,
      kind: data['kind'] as String,
      filename: data['filename'] as String,
      sizeBytes: (data['sizeBytes'] ?? 0) as int,
    );
  }

  MediaType _guessMediaType(String kind, String filename) {
    final lower = filename.toLowerCase();
    if (kind == 'pdf') return MediaType('application', 'pdf');
    if (kind == 'video') {
      if (lower.endsWith('.webm')) return MediaType('video', 'webm');
      return MediaType('video', 'mp4');
    }
    if (kind == 'image') {
      if (lower.endsWith('.png')) return MediaType('image', 'png');
      if (lower.endsWith('.webp')) return MediaType('image', 'webp');
      return MediaType('image', 'jpeg');
    }
    return MediaType('application', 'octet-stream');
  }

  // ==========================================================================
  // Phase 3 — Progress
  // ==========================================================================
  Future<LessonProgress> markLessonComplete(String lessonId) async {
    final data = await _send('POST', '/lessons/$lessonId/complete') as Map<String, dynamic>;
    return LessonProgress.fromJson(data);
  }

  Future<LessonProgress> recordProgress(
    String lessonId, {
    required int lastPositionSeconds,
    bool viewed = false,
  }) async {
    final data = await _send('POST', '/lessons/$lessonId/progress', body: {
      'lastPositionSeconds': lastPositionSeconds,
      'viewed': viewed,
    }) as Map<String, dynamic>;
    return LessonProgress.fromJson(data);
  }

  Future<Map<String, dynamic>> getEnrollmentProgress(String enrollmentId) async {
    final data = await _send('GET', '/enrollments/$enrollmentId/progress') as Map<String, dynamic>;
    return data;
  }

  Future<ContinuePointer?> getContinuePointer() async {
    final data = await _send('GET', '/enrollments/mine/continue');
    if (data == null) return null;
    if (data is Map<String, dynamic>) return ContinuePointer.fromJson(data);
    return null;
  }

  // ==========================================================================
  // Phase 27 — Video checkpoints
  // ==========================================================================
  Future<List<VideoCheckpoint>> listCheckpoints(String lessonId) async {
    final data = await _send('GET', '/lessons/$lessonId/checkpoints')
        as List<dynamic>;
    return data
        .map((e) => VideoCheckpoint.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<VideoCheckpoint> createCheckpoint(
    String lessonId, {
    required int positionSeconds,
    required String prompt,
    required List<VideoCheckpointOption> options,
    String? correctOptionId,
  }) async {
    final data = await _send('POST', '/lessons/$lessonId/checkpoints', body: {
      'positionSeconds': positionSeconds,
      'prompt': prompt,
      'options': options.map((o) => o.toJson()).toList(),
      'correctOptionId': ?correctOptionId,
    }) as Map<String, dynamic>;
    return VideoCheckpoint.fromJson(data);
  }

  Future<VideoCheckpoint> updateCheckpoint(
    String id, {
    int? positionSeconds,
    String? prompt,
    List<VideoCheckpointOption>? options,
    String? correctOptionId,
  }) async {
    final body = <String, dynamic>{
      'positionSeconds': ?positionSeconds,
      'prompt': ?prompt,
      if (options != null)
        'options': options.map((o) => o.toJson()).toList(),
      'correctOptionId': ?correctOptionId,
    };
    final data = await _send('PUT', '/checkpoints/$id', body: body)
        as Map<String, dynamic>;
    return VideoCheckpoint.fromJson(data);
  }

  Future<void> deleteCheckpoint(String id) async {
    await _send('DELETE', '/checkpoints/$id');
  }
}
