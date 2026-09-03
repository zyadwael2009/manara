/// Local shape of a User as returned by the API.
class AppUser {
  final String id;
  final String name;
  final String email;
  final String role; // student | instructor | admin | parent
  final bool isActive;
  final DateTime? createdAt;

  // Present on students only (nullable when unplaced).
  final String? classId;
  final String? className;
  final String? gradeId;
  final String? gradeName;

  const AppUser({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
    required this.isActive,
    this.createdAt,
    this.classId,
    this.className,
    this.gradeId,
    this.gradeName,
  });

  bool get isStudent => role == 'student';
  bool get isInstructor => role == 'instructor';
  bool get isAdmin => role == 'admin';
  bool get isParent => role == 'parent';
  bool get canAuthor => isInstructor || isAdmin;

  factory AppUser.fromJson(Map<String, dynamic> j) => AppUser(
        id: j['id'] as String,
        name: (j['name'] ?? '') as String,
        email: (j['email'] ?? '') as String,
        role: (j['role'] ?? 'student') as String,
        isActive: (j['isActive'] ?? true) as bool,
        createdAt: j['createdAt'] != null ? DateTime.tryParse(j['createdAt'] as String) : null,
        classId: j['classId'] as String?,
        className: j['className'] as String?,
        gradeId: j['gradeId'] as String?,
        gradeName: j['gradeName'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'email': email,
        'role': role,
        'isActive': isActive,
        'createdAt': createdAt?.toIso8601String(),
        if (classId != null) 'classId': classId,
        if (className != null) 'className': className,
        if (gradeId != null) 'gradeId': gradeId,
        if (gradeName != null) 'gradeName': gradeName,
      };
}
