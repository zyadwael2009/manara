// Phase 12 — attendance value types.
//
// Backend contract:
//   AttendanceMark  = one row in attendance_marks
//   ClassAttendance = the GET /classes/<id>/attendance payload (roster + marks
//                     for a specific date, plus the caller's write scope)

class AttendanceMark {
  final String id;
  final String studentId;
  final String classId;
  final DateTime date;
  final String status; // present | absent | late | excused
  final String? reason;
  final String? markedById;

  const AttendanceMark({
    required this.id,
    required this.studentId,
    required this.classId,
    required this.date,
    required this.status,
    this.reason,
    this.markedById,
  });

  factory AttendanceMark.fromJson(Map<String, dynamic> j) => AttendanceMark(
        id: j['id'] as String,
        studentId: j['studentId'] as String,
        classId: j['classId'] as String,
        date: DateTime.parse(j['date'] as String),
        status: (j['status'] as String?) ?? 'present',
        reason: j['reason'] as String?,
        markedById: j['markedById'] as String?,
      );
}

class AttendanceStudent {
  final String id;
  final String name;
  final String? email;
  const AttendanceStudent({required this.id, required this.name, this.email});
  factory AttendanceStudent.fromJson(Map<String, dynamic> j) => AttendanceStudent(
        id: j['id'] as String,
        name: (j['name'] as String?) ?? '',
        email: j['email'] as String?,
      );
}

class ClassAttendanceRow {
  final AttendanceStudent student;
  final AttendanceMark? mark; // null if unmarked
  const ClassAttendanceRow({required this.student, this.mark});
  factory ClassAttendanceRow.fromJson(Map<String, dynamic> j) => ClassAttendanceRow(
        student: AttendanceStudent.fromJson(j['student'] as Map<String, dynamic>),
        mark: j['mark'] == null
            ? null
            : AttendanceMark.fromJson(j['mark'] as Map<String, dynamic>),
      );
}

class ClassAttendance {
  final String classId;
  final String className;
  final DateTime date;
  final List<ClassAttendanceRow> rows;
  final bool canWrite;
  final bool isToday;

  const ClassAttendance({
    required this.classId,
    required this.className,
    required this.date,
    required this.rows,
    required this.canWrite,
    required this.isToday,
  });

  factory ClassAttendance.fromJson(Map<String, dynamic> j) => ClassAttendance(
        classId: j['classId'] as String,
        className: (j['className'] as String?) ?? '',
        date: DateTime.parse(j['date'] as String),
        rows: (j['rows'] as List<dynamic>? ?? [])
            .map((e) => ClassAttendanceRow.fromJson(e as Map<String, dynamic>))
            .toList(),
        canWrite: (j['canWrite'] as bool?) ?? false,
        isToday: (j['isToday'] as bool?) ?? false,
      );
}

/// One row in the payload sent up via PUT /classes/<id>/attendance.
class AttendanceMarkInput {
  final String studentId;
  final String status;
  final String? reason;
  const AttendanceMarkInput({
    required this.studentId,
    required this.status,
    this.reason,
  });
  Map<String, dynamic> toJson() => {
        'studentId': studentId,
        'status': status,
        if (reason != null && reason!.isNotEmpty) 'reason': reason,
      };
}
