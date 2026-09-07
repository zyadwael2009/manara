part of 'api_service.dart';

/// The school's structure: sections, grades, classes, placement, enrolment, and the roster pickers built on top of them.

extension ApiServiceSchool on ApiService {
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
      'sectionId': ?sectionId,
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
      'homeroomTeacherId': ?homeroomTeacherId,
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
        'excludeStudentIds': ?excludeStudentIds,
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
        'excludeStudentIds': ?excludeStudentIds,
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
      'search': ?search,
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
}
