part of 'api_service.dart';

/// Attendance, timetables, meeting links, and the exported calendar feed.

extension ApiServiceSchedule on ApiService {
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
      'periodId': ?periodId,
      'courseId': ?courseId,
      'startTime': ?startTime,
      'endTime': ?endTime,
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
}
