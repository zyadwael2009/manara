// Phase 14 — assignments + submissions.
// Phase 18 — `MyAssignmentRow` for the cross-course "My assignments" hub.

class Assignment {
  final String id;
  final String moduleId;
  final String title;
  final String description;
  final DateTime? dueAt;
  final int maxPoints;
  final bool allowText;
  final bool allowFile;
  final bool isPublished;
  // Phase 27 — group-mode assignment metadata.
  final bool isGroup;
  final int? maxGroupSize;
  final AssignmentSubmission? mySubmission; // populated for student callers

  const Assignment({
    required this.id,
    required this.moduleId,
    required this.title,
    required this.description,
    required this.maxPoints,
    required this.allowText,
    required this.allowFile,
    required this.isPublished,
    this.isGroup = false,
    this.maxGroupSize,
    this.dueAt,
    this.mySubmission,
  });

  factory Assignment.fromJson(Map<String, dynamic> j) => Assignment(
        id: j['id'] as String,
        moduleId: (j['moduleId'] as String?) ?? '',
        title: (j['title'] as String?) ?? '',
        description: (j['description'] as String?) ?? '',
        dueAt: j['dueAt'] == null
            ? null
            : DateTime.tryParse(j['dueAt'] as String),
        maxPoints: (j['maxPoints'] as num?)?.toInt() ?? 100,
        allowText: (j['allowText'] as bool?) ?? true,
        allowFile: (j['allowFile'] as bool?) ?? true,
        isPublished: (j['isPublished'] as bool?) ?? false,
        isGroup: (j['isGroup'] as bool?) ?? false,
        maxGroupSize: (j['maxGroupSize'] as num?)?.toInt(),
        mySubmission: j['mySubmission'] == null
            ? null
            : AssignmentSubmission.fromJson(
                j['mySubmission'] as Map<String, dynamic>),
      );
}

class AssignmentSubmission {
  final String id;
  final String assignmentId;
  final String studentId;
  final String? studentName;
  final DateTime? submittedAt;
  final bool isLate;
  final String? responseText;
  final String? fileUrl;
  final String? fileKind;
  final double? gradedScore;
  final double? gradedMax;
  final String? gradedFeedback;
  final DateTime? gradedAt;
  // Phase 27 — non-null for group-mode submissions; every group-mate's
  // row carries the same groupId so the client can render "shared with
  // your group" on the review screen.
  final String? groupId;

  const AssignmentSubmission({
    required this.id,
    required this.assignmentId,
    required this.studentId,
    required this.isLate,
    this.studentName,
    this.submittedAt,
    this.responseText,
    this.fileUrl,
    this.fileKind,
    this.gradedScore,
    this.gradedMax,
    this.gradedFeedback,
    this.gradedAt,
    this.groupId,
  });

  bool get isGraded => gradedScore != null;

  factory AssignmentSubmission.fromJson(Map<String, dynamic> j) => AssignmentSubmission(
        id: j['id'] as String,
        assignmentId: (j['assignmentId'] as String?) ?? '',
        studentId: (j['studentId'] as String?) ?? '',
        studentName: j['studentName'] as String?,
        isLate: (j['isLate'] as bool?) ?? false,
        submittedAt: j['submittedAt'] == null
            ? null
            : DateTime.tryParse(j['submittedAt'] as String),
        responseText: j['responseText'] as String?,
        fileUrl: j['fileUrl'] as String?,
        fileKind: j['fileKind'] as String?,
        gradedScore: (j['gradedScore'] as num?)?.toDouble(),
        gradedMax: (j['gradedMax'] as num?)?.toDouble(),
        gradedFeedback: j['gradedFeedback'] as String?,
        gradedAt: j['gradedAt'] == null
            ? null
            : DateTime.tryParse(j['gradedAt'] as String),
        groupId: j['groupId'] as String?,
      );
}


/// Phase 27 — group in a group-mode assignment.
///
/// Roster is served alongside the group; the client uses `memberCount`
/// vs the assignment's `maxGroupSize` to decide whether to enable the
/// "Join" button.
class AssignmentGroup {
  final String id;
  final String assignmentId;
  final String name;
  final String? createdById;
  final int memberCount;
  final List<AssignmentGroupMember> members;

  const AssignmentGroup({
    required this.id,
    required this.assignmentId,
    required this.name,
    required this.memberCount,
    required this.members,
    this.createdById,
  });

  factory AssignmentGroup.fromJson(Map<String, dynamic> j) {
    final rawMembers = (j['members'] as List?) ?? const [];
    final members = rawMembers
        .whereType<Map<String, dynamic>>()
        .map(AssignmentGroupMember.fromJson)
        .toList();
    return AssignmentGroup(
      id: j['id'] as String,
      assignmentId: (j['assignmentId'] as String?) ?? '',
      name: (j['name'] as String?) ?? '',
      createdById: j['createdById'] as String?,
      memberCount: (j['memberCount'] as num?)?.toInt() ?? members.length,
      members: members,
    );
  }
}

class AssignmentGroupMember {
  final String id;
  final String groupId;
  final String studentId;
  final String? studentName;
  final DateTime? joinedAt;

  const AssignmentGroupMember({
    required this.id,
    required this.groupId,
    required this.studentId,
    this.studentName,
    this.joinedAt,
  });

  factory AssignmentGroupMember.fromJson(Map<String, dynamic> j) =>
      AssignmentGroupMember(
        id: j['id'] as String,
        groupId: (j['groupId'] as String?) ?? '',
        studentId: (j['studentId'] as String?) ?? '',
        studentName: j['studentName'] as String?,
        joinedAt: j['joinedAt'] == null
            ? null
            : DateTime.tryParse(j['joinedAt'] as String),
      );
}

/// Phase 18 — row in the student "My assignments" hub.
///
/// Extends the base `Assignment` shape with the course + module context
/// the hub screen needs to group and label rows.
class MyAssignmentRow {
  final Assignment assignment;
  final String moduleTitle;
  final MyAssignmentCourse course;

  const MyAssignmentRow({
    required this.assignment,
    required this.moduleTitle,
    required this.course,
  });

  factory MyAssignmentRow.fromJson(Map<String, dynamic> j) {
    final courseJson = (j['course'] as Map<String, dynamic>?) ?? const {};
    return MyAssignmentRow(
      // The base assignment fields live at the top level; the `course` and
      // `moduleTitle` keys are the hub-only additions.
      assignment: Assignment.fromJson(j),
      moduleTitle: (j['moduleTitle'] as String?) ?? '',
      course: MyAssignmentCourse.fromJson(courseJson),
    );
  }

  /// Ordering buckets used by the hub screen's three tabs.
  bool get isSubmitted => assignment.mySubmission?.submittedAt != null;
  bool get isGraded => assignment.mySubmission?.isGraded ?? false;

  /// A submission that's late per the server flag OR an un-submitted one
  /// whose due-date has passed.
  bool get isPastDue {
    final due = assignment.dueAt;
    if (due == null) return false;
    if (assignment.mySubmission?.submittedAt != null) return false;
    return due.isBefore(DateTime.now());
  }

  bool get isDueSoon {
    final due = assignment.dueAt;
    if (due == null) return false;
    final now = DateTime.now();
    return !due.isBefore(now) && due.isBefore(now.add(const Duration(days: 3)));
  }
}

class MyAssignmentCourse {
  final String? id;
  final String title;
  final String category;
  const MyAssignmentCourse({this.id, required this.title, required this.category});
  factory MyAssignmentCourse.fromJson(Map<String, dynamic> j) => MyAssignmentCourse(
        id: j['id'] as String?,
        title: (j['title'] as String?) ?? '',
        category: (j['category'] as String?) ?? 'general',
      );
}
