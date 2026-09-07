/// The HTTP client for the Manara API.
///
/// `ApiService` was a single 2,300-line file holding 207 methods — every
/// screen in the app funnelled through it, so it was both the hardest file to
/// navigate and the one most likely to conflict on any branch.
///
/// The class itself now holds only the transport: the singleton, the session
/// token, header construction, and `_send`, which is the one place a request
/// is built, sent, and turned into either a decoded body or an
/// `ApiException`. Every endpoint lives in a `part` file grouped by feature
/// area (see the `part` directives below).
///
/// The parts are `extension`s rather than a class hierarchy because Dart
/// cannot split one class across files — but a `part` shares the library, so
/// they still reach `_send` and the other private members, and callers see a
/// single flat `ApiService.instance` exactly as before.
library;

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

// The API surface is split by feature area across these parts. They are
// `extension`s on ApiService in the same library, so they still reach
// `_send` and the other private members, and every call site is unchanged.
part 'api_service_auth.dart';
part 'api_service_school.dart';
part 'api_service_content.dart';
part 'api_service_grading.dart';
part 'api_service_quizzes.dart';
part 'api_service_assignments.dart';
part 'api_service_schedule.dart';
part 'api_service_comms.dart';
part 'api_service_reports.dart';

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
}

