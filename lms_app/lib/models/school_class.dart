import 'user.dart';

class SchoolClass {
  final String id;
  final String gradeId;
  final String? gradeName;
  final String name;
  final String? homeroomTeacherId;
  final String? homeroomTeacherName;
  final int studentCount;
  final List<AppUser> students;

  const SchoolClass({
    required this.id,
    required this.gradeId,
    required this.name,
    this.gradeName,
    this.homeroomTeacherId,
    this.homeroomTeacherName,
    this.studentCount = 0,
    this.students = const [],
  });

  factory SchoolClass.fromJson(Map<String, dynamic> j) => SchoolClass(
        id: j['id'] as String,
        gradeId: (j['gradeId'] ?? '') as String,
        gradeName: j['gradeName'] as String?,
        name: (j['name'] ?? '') as String,
        homeroomTeacherId: j['homeroomTeacherId'] as String?,
        homeroomTeacherName: j['homeroomTeacherName'] as String?,
        studentCount: (j['studentCount'] ?? 0) as int,
        students: (j['students'] as List<dynamic>? ?? const [])
            .map((e) => AppUser.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'gradeId': gradeId,
        'gradeName': gradeName,
        'name': name,
        'homeroomTeacherId': homeroomTeacherId,
        'homeroomTeacherName': homeroomTeacherName,
        'studentCount': studentCount,
        'students': students.map((s) => s.toJson()).toList(),
      };
}
