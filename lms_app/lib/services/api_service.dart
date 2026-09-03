import 'dart:async';
import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../core/constants/app_constants.dart';
import '../models/announcement.dart';
import '../models/assignment.dart';
import '../models/attendance.dart';
import '../models/bulk_import.dart';
import '../models/comm.dart';
import '../models/gamify.dart';
import '../models/insight.dart';
import '../models/certificate.dart';
import '../models/course.dart';
import '../models/dashboard.dart';
import '../models/timetable.dart';
import '../models/enrollment.dart';
import '../models/grade.dart';
import '../models/parent_link.dart';
import '../models/grading.dart';
import '../models/lesson.dart';
import '../models/module.dart';
import '../models/quiz.dart';
import '../models/school_class.dart';
import '../models/school_year.dart';
import '../models/section.dart';
import '../models/term.dart';
import '../models/today.dart';
import '../models/cohort.dart';
import '../models/diploma.dart';
import '../models/fees.dart';
import '../models/standard.dart';
import '../models/user.dart';
import '../models/video_checkpoint.dart';
import 'api_client_factory.dart' show createApiClient;
import 'storage_service.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);

  bool get isAuth => statusCode == 401 || statusCode == 423;
  bool get isForbidden => statusCode == 403;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class SessionExpiredException extends ApiException {
  SessionExpiredException(String message) : super(401, message);
}

class AuthBundle {
  final AppUser user;
  final String sessionToken;
  const AuthBundle({required this.user, required this.sessionToken});
}

class UploadResult {
  final String url;
  final String kind;
  final String filename;
  final int sizeBytes;
  const UploadResult({
    required this.url,
    required this.kind,
    required this.filename,
    required this.sizeBytes,
  });
}

class ClassCourse {
  final Course course;
  final Map<String, dynamic>? classTeacher; // null if unassigned
  const ClassCourse({required this.course, this.classTeacher});
}

class GradeCurriculum {
  final String gradeId;
  final String gradeName;
  final String? sectionId;
  final String? sectionName;
  final List<Course> mandatory;
  /// Map of `elective_group` -> alternatives.
  final Map<String, List<Course>> electiveGroups;

  const GradeCurriculum({
    required this.gradeId,
    required this.gradeName,
    this.sectionId,
    this.sectionName,
    this.mandatory = const [],
    this.electiveGroups = const {},
  });
}

class DepartmentLeader {
  final String id;
  final String department;
  final String sectionId;
  final String? sectionName;
  final String teacherId;
  final String? teacherName;

  const DepartmentLeader({
    required this.id,
    required this.department,
    required this.sectionId,
    required this.teacherId,
    this.sectionName,
    this.teacherName,
  });

  factory DepartmentLeader.fromJson(Map<String, dynamic> j) => DepartmentLeader(
        id: j['id'] as String,
        department: (j['department'] ?? '') as String,
        sectionId: (j['sectionId'] ?? '') as String,
        sectionName: j['sectionName'] as String?,
        teacherId: (j['teacherId'] ?? '') as String,
        teacherName: j['teacherName'] as String?,
      );
}

class PlacementDiff {
  final bool sameClass;
  final bool sameGrade;
  final String? oldClassId;
  final String newClassId;
  final int willDropEnrollments;
  final int willAutoEnroll;
  const PlacementDiff({
    required this.sameClass,
    required this.sameGrade,
    required this.newClassId,
    required this.willDropEnrollments,
    required this.willAutoEnroll,
    this.oldClassId,
  });
  factory PlacementDiff.fromJson(Map<String, dynamic> j) => PlacementDiff(
        sameClass: (j['sameClass'] ?? false) as bool,
        sameGrade: (j['sameGrade'] ?? false) as bool,
        oldClassId: j['oldClassId'] as String?,
        newClassId: (j['newClassId'] ?? '') as String,
        willDropEnrollments: (j['willDropEnrollments'] ?? 0) as int,
        willAutoEnroll: (j['willAutoEnroll'] ?? 0) as int,
      );
}

/// Hand-rolled REST client — singleton so we don't spin new http.Client per
/// request (which would lose the browser cookie jar on native platforms).
class ApiService {
  ApiService._internal();
  static final ApiService instance = ApiService._internal();

  final http.Client _client = createApiClient();
  String? _sessionToken;

  String get baseUrl => AppConstants.apiBaseUrl;

  void setSessionToken(String? token) {
    _sessionToken = (token == null || token.isEmpty) ? null : token;
  }

  Map<String, String> _headers({bool json = true}) {
    final h = <String, String>{'Accept': 'application/json'};
    if (json) h['Content-Type'] = 'application/json';
    final token = _sessionToken ?? StorageService.instance.getSessionToken();
    if (token != null && token.isNotEmpty) h['X-Session-Token'] = token;
    return h;
  }

  Future<dynamic> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    bool expectJson = true,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: (query == null || query.isEmpty) ? null : query,
    );

    late http.Response resp;
    try {
      switch (method) {
        case 'GET':
          resp = await _client.get(uri, headers: _headers(json: false));
          break;
        case 'DELETE':
          resp = await _client.delete(uri, headers: _headers(json: false));
          break;
        case 'POST':
          resp = await _client.post(uri, headers: _headers(), body: jsonEncode(body ?? {}));
          break;
        case 'PUT':
          resp = await _client.put(uri, headers: _headers(), body: jsonEncode(body ?? {}));
          break;
        case 'PATCH':
          resp = await _client.patch(uri, headers: _headers(), body: jsonEncode(body ?? {}));
          break;
        default:
          throw ArgumentError('Unsupported method $method');
      }
    } catch (e) {
      throw ApiException(0, 'Cannot reach server. Check your connection. ($e)');
    }

    Map<String, dynamic>? bodyMap;
    if (resp.body.isNotEmpty) {
      try {
        final decoded = jsonDecode(resp.body);
        if (decoded is Map<String, dynamic>) {
          bodyMap = decoded;
          final newToken = decoded['sessionToken'];
          if (newToken is String && newToken.isNotEmpty) {
            _sessionToken = newToken;
            StorageService.instance.setSessionToken(newToken);
          }
        }
      } catch (_) {/* non-JSON body */}
    }

    if (resp.statusCode >= 200 && resp.statusCode < 300) {
      if (!expectJson) return null;
      if (resp.body.isEmpty) return null;
      return bodyMap ?? jsonDecode(resp.body);
    }

    final message = (bodyMap != null && bodyMap['error'] is String)
        ? bodyMap['error'] as String
        : 'Request failed (${resp.statusCode}).';

    if (resp.statusCode == 401) throw SessionExpiredException(message);
    throw ApiException(resp.statusCode, message);
  }

  // ==========================================================================
  // Auth
  // ==========================================================================
  Future<AuthBundle> register({
    required String name,
    required String email,
    required String password,
    required String role,
  }) async {
    final data = await _send('POST', '/auth/register', body: {
      'name': name,
      'email': email,
      'password': password,
      'role': role,
    }) as Map<String, dynamic>;
    return AuthBundle(
      user: AppUser.fromJson(data['user'] as Map<String, dynamic>),
      sessionToken: data['sessionToken'] as String,
    );
  }

  Future<AuthBundle> login({required String email, required String password}) async {
    final data = await _send('POST', '/auth/login', body: {
      'email': email,
      'password': password,
    }) as Map<String, dynamic>;
    return AuthBundle(
      user: AppUser.fromJson(data['user'] as Map<String, dynamic>),
      sessionToken: data['sessionToken'] as String,
    );
  }

  Future<AuthBundle> me() async {
    final data = await _send('GET', '/auth/me') as Map<String, dynamic>;
    return AuthBundle(
      user: AppUser.fromJson(data['user'] as Map<String, dynamic>),
      sessionToken: data['sessionToken'] as String,
    );
  }

  Future<void> logout() async {
    try {
      await _send('POST', '/auth/logout');
    } finally {
      _sessionToken = null;
      await StorageService.instance.clearSession();
    }
  }

  // ==========================================================================
  // Sections
  // ==========================================================================
  Future<List<Section>> listSections() async {
    final data = await _send('GET', '/sections') as List<dynamic>;
    return data.map((e) => Section.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Section> createSection({required String name, int orderIndex = 0}) async {
    final data = await _send('POST', '/sections',
        body: {'name': name, 'orderIndex': orderIndex}) as Map<String, dynamic>;
    return Section.fromJson(data);
  }

  Future<Section> updateSection(String id, {String? name, int? orderIndex}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (orderIndex != null) body['orderIndex'] = orderIndex;
    final data = await _send('PUT', '/sections/$id', body: body) as Map<String, dynamic>;
    return Section.fromJson(data);
  }

  Future<void> deleteSection(String id) => _send('DELETE', '/sections/$id');

  // ==========================================================================
  // Grades + curriculum
  // ==========================================================================
  Future<List<Grade>> listGrades({String? sectionId}) async {
    final q = <String, String>{};
    if (sectionId != null && sectionId.isNotEmpty) q['sectionId'] = sectionId;
    final data = await _send('GET', '/grades', query: q) as List<dynamic>;
    return data.map((e) => Grade.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Grade> createGrade({required String name, String? sectionId, int orderIndex = 0}) async {
    final data = await _send('POST', '/grades', body: {
      'name': name,
      if (sectionId != null) 'sectionId': sectionId,
      'orderIndex': orderIndex,
    }) as Map<String, dynamic>;
    return Grade.fromJson(data);
  }

  Future<Grade> updateGrade(String id,
      {String? name, String? sectionId, int? orderIndex}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (sectionId != null) body['sectionId'] = sectionId;
    if (orderIndex != null) body['orderIndex'] = orderIndex;
    final data = await _send('PUT', '/grades/$id', body: body) as Map<String, dynamic>;
    return Grade.fromJson(data);
  }

  Future<void> deleteGrade(String id) => _send('DELETE', '/grades/$id');

  Future<GradeCurriculum> getGradeCurriculum(String gradeId) async {
    final data = await _send('GET', '/grades/$gradeId/curriculum') as Map<String, dynamic>;
    final mandatory = (data['mandatory'] as List<dynamic>? ?? const [])
        .map((e) => Course.fromJson(e as Map<String, dynamic>))
        .toList();
    final electivesRaw = (data['electiveGroups'] as Map<String, dynamic>? ?? const {});
    final electives = <String, List<Course>>{};
    electivesRaw.forEach((k, v) {
      electives[k] = (v as List<dynamic>)
          .map((e) => Course.fromJson(e as Map<String, dynamic>))
          .toList();
    });
    return GradeCurriculum(
      gradeId: (data['gradeId'] ?? gradeId) as String,
      gradeName: (data['gradeName'] ?? '') as String,
      sectionId: data['sectionId'] as String?,
      sectionName: data['sectionName'] as String?,
      mandatory: mandatory,
      electiveGroups: electives,
    );
  }

  // ==========================================================================
  // Classes
  // ==========================================================================
  Future<List<SchoolClass>> listClasses({String? gradeId}) async {
    final q = <String, String>{};
    if (gradeId != null && gradeId.isNotEmpty) q['gradeId'] = gradeId;
    final data = await _send('GET', '/classes', query: q) as List<dynamic>;
    return data.map((e) => SchoolClass.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<SchoolClass> getClass(String id) async {
    final data = await _send('GET', '/classes/$id') as Map<String, dynamic>;
    return SchoolClass.fromJson(data);
  }

  Future<SchoolClass> createClass({
    required String gradeId,
    required String name,
    String? homeroomTeacherId,
  }) async {
    final data = await _send('POST', '/classes', body: {
      'gradeId': gradeId,
      'name': name,
      if (homeroomTeacherId != null) 'homeroomTeacherId': homeroomTeacherId,
    }) as Map<String, dynamic>;
    return SchoolClass.fromJson(data);
  }

  Future<SchoolClass> updateClass(String id, {String? name, String? homeroomTeacherId}) async {
    final body = <String, dynamic>{};
    if (name != null) body['name'] = name;
    if (homeroomTeacherId != null) body['homeroomTeacherId'] = homeroomTeacherId;
    final data = await _send('PUT', '/classes/$id', body: body) as Map<String, dynamic>;
    return SchoolClass.fromJson(data);
  }

  Future<void> deleteClass(String id) => _send('DELETE', '/classes/$id');

  /// End-of-year promotion: bulk-move students from `srcClassId` to `toClassId`.
  Future<Map<String, dynamic>> promoteClass(
    String srcClassId, {
    required String toClassId,
    List<String>? excludeStudentIds,
  }) async {
    final data = await _send(
      'POST',
      '/classes/$srcClassId/promote',
      body: {
        'toClassId': toClassId,
        if (excludeStudentIds != null) 'excludeStudentIds': excludeStudentIds,
      },
    ) as Map<String, dynamic>;
    return data;
  }

  /// Grade-12 graduation: mark students inactive + set graduated_at.
  Future<Map<String, dynamic>> graduateClass(
    String srcClassId, {
    List<String>? excludeStudentIds,
  }) async {
    final data = await _send(
      'POST',
      '/classes/$srcClassId/graduate',
      body: {
        if (excludeStudentIds != null) 'excludeStudentIds': excludeStudentIds,
      },
    ) as Map<String, dynamic>;
    return data;
  }

  Future<List<ClassCourse>> listClassCourses(String classId) async {
    final data = await _send('GET', '/classes/$classId/courses') as List<dynamic>;
    return data.map((raw) {
      final m = raw as Map<String, dynamic>;
      return ClassCourse(
        course: Course.fromJson(m),
        classTeacher: m['classTeacher'] as Map<String, dynamic>?,
      );
    }).toList();
  }

  Future<Map<String, dynamic>> assignClassCourseTeacher(
      String classId, String courseId, String teacherId) async {
    final data = await _send('PUT', '/classes/$classId/courses/$courseId/teacher',
        body: {'teacherId': teacherId}) as Map<String, dynamic>;
    return data;
  }

  // ==========================================================================
  // Placement + electives (admin's write verbs on a student)
  // ==========================================================================
  Future<PlacementDiff> placeStudent(String studentId, String classId, {bool dryRun = false}) async {
    final data = await _send(
      'PUT',
      '/users/$studentId/class',
      body: {'classId': classId, if (dryRun) 'dryRun': true},
    ) as Map<String, dynamic>;
    return PlacementDiff.fromJson(data);
  }

  Future<void> unassignStudent(String studentId) => _send('DELETE', '/users/$studentId/class');

  Future<List<PendingElective>> getPendingElectives(String studentId) async {
    final data = await _send('GET', '/users/$studentId/electives/pending') as List<dynamic>;
    return data.map((e) => PendingElective.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Enrollment> setElective(String studentId, String group, String courseId) async {
    final data = await _send(
      'PUT',
      '/users/$studentId/electives/$group',
      body: {'courseId': courseId},
    ) as Map<String, dynamic>;
    return Enrollment.fromJson(data);
  }

  // ==========================================================================
  // Enrollments
  // ==========================================================================
  Future<List<Enrollment>> listMyEnrollments() async {
    final data = await _send('GET', '/enrollments/mine') as List<dynamic>;
    return data.map((e) => Enrollment.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Enrollment> getEnrollment(String id) async {
    final data = await _send('GET', '/enrollments/$id') as Map<String, dynamic>;
    return Enrollment.fromJson(data);
  }

  // ==========================================================================
  // Users search (roster picker)
  // ==========================================================================
  Future<List<AppUser>> searchStudents({String? search, bool unassigned = false, int limit = 20}) async {
    final q = <String, String>{
      'role': 'student',
      if (search != null) 'search': search,
      if (unassigned) 'unassigned': 'true',
      'limit': '$limit',
    };
    final data = await _send('GET', '/users', query: q) as List<dynamic>;
    return data.map((e) => AppUser.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<AppUser>> listInstructors({String? search}) async {
    final q = <String, String>{};
    if (search != null && search.isNotEmpty) q['search'] = search;
    final data = await _send('GET', '/users/instructors', query: q) as List<dynamic>;
    return data.map((e) => AppUser.fromJson(e as Map<String, dynamic>)).toList();
  }

  // ==========================================================================
  // Department leaders
  // ==========================================================================
  Future<List<DepartmentLeader>> listDepartmentLeaders() async {
    final data = await _send('GET', '/department-leaders') as List<dynamic>;
    return data.map((e) => DepartmentLeader.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<DepartmentLeader> setDepartmentLeader({
    required String department,
    required String sectionId,
    required String teacherId,
  }) async {
    final data = await _send('POST', '/department-leaders', body: {
      'department': department,
      'sectionId': sectionId,
      'teacherId': teacherId,
    }) as Map<String, dynamic>;
    return DepartmentLeader.fromJson(data);
  }

  Future<void> clearDepartmentLeader(String id) => _send('DELETE', '/department-leaders/$id');

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
      if (contentUrl != null) 'contentUrl': contentUrl,
      if (contentText != null) 'contentText': contentText,
      if (durationMinutes != null) 'durationMinutes': durationMinutes,
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
      if (startDate != null) 'startDate': startDate,
      if (endDate != null) 'endDate': endDate,
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
      if (startDate != null) 'startDate': startDate,
      if (endDate != null) 'endDate': endDate,
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
      if (slug != null) 'slug': slug,
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

  // ==========================================================================
  // Phase 4 — Quizzes (author)
  // ==========================================================================
  Future<Quiz> createQuiz(String moduleId,
      {required String title, int passingScore = 60, int? maxAttempts, String scoringMode = 'best', int? timeLimitMinutes}) async {
    final data = await _send('POST', '/modules/$moduleId/quizzes', body: {
      'title': title,
      'passingScore': passingScore,
      if (maxAttempts != null) 'maxAttempts': maxAttempts,
      'scoringMode': scoringMode,
      if (timeLimitMinutes != null) 'timeLimitMinutes': timeLimitMinutes,
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
  // Phase 25 — admin CSV export URLs + ICS calendar token
  // ==========================================================================
  /// Direct-open URL for a CSV export kind. Same auth caveat as the PDF
  /// endpoints (browser must carry the session cookie).
  String csvExportUrl(String kind, {Map<String, String>? params}) {
    final query = params == null || params.isEmpty
        ? ''
        : '?${params.entries.map((e) => '${Uri.encodeQueryComponent(e.key)}=${Uri.encodeQueryComponent(e.value)}').join('&')}';
    return '$baseUrl/admin/export/$kind.csv$query';
  }

  Future<List<Map<String, dynamic>>> listExportKinds() async {
    final data = await _send('GET', '/admin/export/kinds')
        as Map<String, dynamic>;
    return (data['kinds'] as List<dynamic>? ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  Future<Map<String, dynamic>> getCalendarToken() async {
    return await _send('GET', '/calendar/mine/token') as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> rotateCalendarToken() async {
    return await _send('POST', '/calendar/mine/token') as Map<String, dynamic>;
  }

  Future<void> revokeCalendarToken() async {
    await _send('DELETE', '/calendar/mine/token');
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
      query: {'q': q.trim(), if (scope != null) 'scope': scope},
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
        if (options != null) 'options': options,
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
    final body = <String, dynamic>{if (all) 'all': true, if (ids != null) 'ids': ids};
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
      if (parentCommentId != null) 'parentCommentId': parentCommentId,
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
  // Phase 4 — Quizzes (admin/teacher)
  // ==========================================================================
  Future<List<QuizAttempt>> listQuizAttempts(String quizId) async {
    final data = await _send('GET', '/quizzes/$quizId/attempts') as List<dynamic>;
    return data.map((e) => QuizAttempt.fromJson(e as Map<String, dynamic>)).toList();
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

  /// POST /api/users/<id>/withdraw — admin only.
  Future<Map<String, dynamic>> withdrawStudent(String studentId, {
    String? reason, DateTime? effectiveDate,
  }) async {
    final body = <String, dynamic>{
      if (reason != null) 'reason': reason,
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
  // Phase 12 — Attendance
  // ==========================================================================
  Future<ClassAttendance> getClassAttendance(String classId, DateTime date) async {
    final iso = _dateOnly(date);
    final data = await _send(
      'GET', '/classes/$classId/attendance',
      query: {'date': iso},
    ) as Map<String, dynamic>;
    return ClassAttendance.fromJson(data);
  }

  Future<void> saveClassAttendance(
    String classId,
    DateTime date,
    List<AttendanceMarkInput> marks,
  ) async {
    await _send('PUT', '/classes/$classId/attendance', body: {
      'date': _dateOnly(date),
      'marks': marks.map((m) => m.toJson()).toList(),
    });
  }

  Future<List<AttendanceMark>> getStudentAttendance(
    String studentId, {
    DateTime? from,
    DateTime? to,
  }) async {
    final q = <String, String>{};
    if (from != null) q['from'] = _dateOnly(from);
    if (to != null) q['to'] = _dateOnly(to);
    final data = await _send(
      'GET', '/users/$studentId/attendance',
      query: q.isEmpty ? null : q,
    ) as List<dynamic>;
    return data.map((e) => AttendanceMark.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<AttendanceMark>> getMyAttendance({
    DateTime? from,
    DateTime? to,
  }) async {
    final q = <String, String>{};
    if (from != null) q['from'] = _dateOnly(from);
    if (to != null) q['to'] = _dateOnly(to);
    final data = await _send(
      'GET', '/attendance/mine',
      query: q.isEmpty ? null : q,
    ) as List<dynamic>;
    return data.map((e) => AttendanceMark.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<AttendanceMark>> getChildAttendance(
    String childId, {
    DateTime? from,
    DateTime? to,
  }) async {
    final q = <String, String>{};
    if (from != null) q['from'] = _dateOnly(from);
    if (to != null) q['to'] = _dateOnly(to);
    final data = await _send(
      'GET', '/parents/mine/children/$childId/attendance',
      query: q.isEmpty ? null : q,
    ) as List<dynamic>;
    return data.map((e) => AttendanceMark.fromJson(e as Map<String, dynamic>)).toList();
  }

  static String _dateOnly(DateTime d) =>
      '${d.year.toString().padLeft(4, "0")}-'
      '${d.month.toString().padLeft(2, "0")}-'
      '${d.day.toString().padLeft(2, "0")}';

  // ==========================================================================
  // Phase 13 — Timetables
  // ==========================================================================
  Future<TimetableWeek> getClassTimetable(String classId) async {
    final data = await _send('GET', '/classes/$classId/timetable')
        as Map<String, dynamic>;
    return TimetableWeek.fromJson(data);
  }

  Future<TimetableWeek> saveClassPeriods(
    String classId, List<PeriodInput> periods,
  ) async {
    final data = await _send('PUT', '/classes/$classId/timetable/periods',
        body: {'periods': periods.map((p) => p.toJson()).toList()})
        as Map<String, dynamic>;
    return TimetableWeek.fromJson(data);
  }

  Future<TimetableOverride> addTimetableOverride(
    String classId, {
    required DateTime date,
    required String kind, // canceled | custom
    String? periodId,
    String? courseId,
    String? startTime,
    String? endTime,
    String? room,
    String? note,
  }) async {
    final body = <String, dynamic>{
      'date': _dateOnly(date),
      'kind': kind,
      if (periodId != null) 'periodId': periodId,
      if (courseId != null) 'courseId': courseId,
      if (startTime != null) 'startTime': startTime,
      if (endTime != null) 'endTime': endTime,
      if (room != null && room.isNotEmpty) 'room': room,
      if (note != null && note.isNotEmpty) 'note': note,
    };
    final data = await _send(
      'POST', '/classes/$classId/timetable/overrides', body: body,
    ) as Map<String, dynamic>;
    return TimetableOverride.fromJson(data);
  }

  Future<void> deleteTimetableOverride(String overrideId) async {
    await _send('DELETE', '/timetable/overrides/$overrideId');
  }

  Future<TimetableWeek> getMyTimetable() async {
    final data = await _send('GET', '/timetable/mine/week')
        as Map<String, dynamic>;
    return TimetableWeek.fromJson(data);
  }

  Future<NowNext> getNowNext() async {
    final data = await _send('GET', '/timetable/mine/nownext')
        as Map<String, dynamic>;
    return NowNext.fromJson(data);
  }

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
      if (title != null) 'title': title,
      if (description != null) 'description': description,
      if (dueAt != null) 'dueAt': dueAt.toIso8601String(),
      if (maxPoints != null) 'maxPoints': maxPoints,
      if (allowText != null) 'allowText': allowText,
      if (allowFile != null) 'allowFile': allowFile,
      if (isGroup != null) 'isGroup': isGroup,
      if (maxGroupSize != null) 'maxGroupSize': maxGroupSize,
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
        if (responseText != null) 'responseText': responseText,
        if (fileUrl != null) 'fileUrl': fileUrl,
        if (fileKind != null) 'fileKind': fileKind,
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
      if (correctOptionId != null) 'correctOptionId': correctOptionId,
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
      if (positionSeconds != null) 'positionSeconds': positionSeconds,
      if (prompt != null) 'prompt': prompt,
      if (options != null)
        'options': options.map((o) => o.toJson()).toList(),
      if (correctOptionId != null) 'correctOptionId': correctOptionId,
    };
    final data = await _send('PUT', '/checkpoints/$id', body: body)
        as Map<String, dynamic>;
    return VideoCheckpoint.fromJson(data);
  }

  Future<void> deleteCheckpoint(String id) async {
    await _send('DELETE', '/checkpoints/$id');
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

  // ==========================================================================
  // Phase 27 — Period Meet URL (teacher-editable in-place)
  // ==========================================================================
  Future<Period> setPeriodMeetingUrl({
    required String classId,
    required String periodId,
    required String? meetingUrl,
  }) async {
    final data = await _send(
      'PUT',
      '/classes/$classId/timetable/periods/$periodId/meeting-url',
      body: {'meetingUrl': meetingUrl},
    ) as Map<String, dynamic>;
    return Period.fromJson(data);
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
      if (userAgent != null) 'userAgent': userAgent,
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
      if (reason != null) 'reason': reason,
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
      if (label != null) 'label': label,
      if (amount != null) 'amount': amount,
      if (dueDate != null)
        'dueDate':
            '${dueDate.year}-${dueDate.month.toString().padLeft(2, '0')}-${dueDate.day.toString().padLeft(2, '0')}',
      if (clearDueDate) 'dueDate': null,
      if (notes != null) 'notes': notes,
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
      if (reason != null) 'reason': reason,
      if (perQuestionScores != null) 'perQuestionScores': perQuestionScores,
    }) as Map<String, dynamic>;
    return QuizAttempt.fromJson(data);
  }
}
