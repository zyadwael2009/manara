/// Phase 21 — communication models: notifications, DM threads/messages,
/// lesson comments, homework posts. Kept in one file — the four features
/// are all light-weight envelopes with no shared substructure.
library;

class AppNotification {
  final String id;
  final String userId;
  final String kind;    // grade_updated | assignment_graded | ... | message
  final String title;
  final String body;
  final String? refType;
  final String? refId;
  final DateTime? readAt;
  final DateTime? createdAt;

  const AppNotification({
    required this.id,
    required this.userId,
    required this.kind,
    required this.title,
    required this.body,
    this.refType,
    this.refId,
    this.readAt,
    this.createdAt,
  });

  bool get isUnread => readAt == null;

  factory AppNotification.fromJson(Map<String, dynamic> j) => AppNotification(
        id: j['id'] as String,
        userId: (j['userId'] as String?) ?? '',
        kind: (j['kind'] as String?) ?? 'unknown',
        title: (j['title'] as String?) ?? '',
        body: (j['body'] as String?) ?? '',
        refType: j['refType'] as String?,
        refId: j['refId'] as String?,
        readAt: j['readAt'] == null
            ? null
            : DateTime.tryParse(j['readAt'] as String),
        createdAt: j['createdAt'] == null
            ? null
            : DateTime.tryParse(j['createdAt'] as String),
      );
}

class NotificationsPage {
  final List<AppNotification> notifications;
  final int unreadCount;
  // Phase 30 · T4 — pagination fields. Nullable so legacy responses
  // (pre-Phase-29 or `?limit=` calls) parse cleanly.
  final int? page;
  final int? pageSize;
  final bool? hasMore;
  const NotificationsPage({
    this.notifications = const [],
    this.unreadCount = 0,
    this.page,
    this.pageSize,
    this.hasMore,
  });
  factory NotificationsPage.fromJson(Map<String, dynamic> j) => NotificationsPage(
        // Backend now sends both `items` (new) and `notifications`
        // (legacy alias) — accept either.
        notifications: ((j['items'] as List<dynamic>?) ??
                (j['notifications'] as List<dynamic>?) ?? const [])
            .map((e) => AppNotification.fromJson(e as Map<String, dynamic>))
            .toList(),
        unreadCount: (j['unreadCount'] as num?)?.toInt() ?? 0,
        page: (j['page'] as num?)?.toInt(),
        pageSize: (j['pageSize'] as num?)?.toInt(),
        hasMore: j['hasMore'] as bool?,
      );
}

// ---------------------------------------------------------------------------
// DMs
// ---------------------------------------------------------------------------
class MessageThreadSummary {
  final String id;
  final String parentId;
  final String? parentName;
  final String teacherId;
  final String? teacherName;
  final String subject;
  final DateTime? createdAt;
  final DateTime? lastMessageAt;
  final String lastMessagePreview;
  final bool hasUnreadForViewer;

  const MessageThreadSummary({
    required this.id,
    required this.parentId,
    required this.teacherId,
    required this.subject,
    this.parentName,
    this.teacherName,
    this.createdAt,
    this.lastMessageAt,
    this.lastMessagePreview = '',
    this.hasUnreadForViewer = false,
  });

  /// The party OTHER than the viewer — used to label the row.
  String otherName({required String viewerId}) {
    if (viewerId == parentId) return teacherName ?? 'Teacher';
    return parentName ?? 'Parent';
  }

  factory MessageThreadSummary.fromJson(Map<String, dynamic> j) =>
      MessageThreadSummary(
        id: j['id'] as String,
        parentId: (j['parentId'] as String?) ?? '',
        parentName: j['parentName'] as String?,
        teacherId: (j['teacherId'] as String?) ?? '',
        teacherName: j['teacherName'] as String?,
        subject: (j['subject'] as String?) ?? '',
        createdAt: j['createdAt'] == null
            ? null
            : DateTime.tryParse(j['createdAt'] as String),
        lastMessageAt: j['lastMessageAt'] == null
            ? null
            : DateTime.tryParse(j['lastMessageAt'] as String),
        lastMessagePreview: (j['lastMessagePreview'] as String?) ?? '',
        hasUnreadForViewer: (j['hasUnreadForViewer'] as bool?) ?? false,
      );
}

class DmMessage {
  final String id;
  final String threadId;
  final String authorId;
  final String? authorName;
  final String body;
  final DateTime? createdAt;
  final DateTime? readByOtherAt;
  const DmMessage({
    required this.id,
    required this.threadId,
    required this.authorId,
    required this.body,
    this.authorName,
    this.createdAt,
    this.readByOtherAt,
  });
  factory DmMessage.fromJson(Map<String, dynamic> j) => DmMessage(
        id: j['id'] as String,
        threadId: (j['threadId'] as String?) ?? '',
        authorId: (j['authorId'] as String?) ?? '',
        authorName: j['authorName'] as String?,
        body: (j['body'] as String?) ?? '',
        createdAt: j['createdAt'] == null
            ? null
            : DateTime.tryParse(j['createdAt'] as String),
        readByOtherAt: j['readByOtherAt'] == null
            ? null
            : DateTime.tryParse(j['readByOtherAt'] as String),
      );
}

class MessageThreadPage {
  final MessageThreadSummary thread;
  final List<DmMessage> messages;
  const MessageThreadPage({required this.thread, this.messages = const []});
  factory MessageThreadPage.fromJson(Map<String, dynamic> j) => MessageThreadPage(
        thread: MessageThreadSummary.fromJson(
            j['thread'] as Map<String, dynamic>),
        messages: (j['messages'] as List<dynamic>? ?? const [])
            .map((e) => DmMessage.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

// ---------------------------------------------------------------------------
// Lesson comments
// ---------------------------------------------------------------------------
class LessonComment {
  final String id;
  final String lessonId;
  final String authorId;
  final String? authorName;
  final String? authorRole;
  final String? parentCommentId;
  final String body;
  final DateTime? createdAt;
  const LessonComment({
    required this.id,
    required this.lessonId,
    required this.authorId,
    required this.body,
    this.authorName,
    this.authorRole,
    this.parentCommentId,
    this.createdAt,
  });
  bool get isQuestion => parentCommentId == null;
  factory LessonComment.fromJson(Map<String, dynamic> j) => LessonComment(
        id: j['id'] as String,
        lessonId: (j['lessonId'] as String?) ?? '',
        authorId: (j['authorId'] as String?) ?? '',
        authorName: j['authorName'] as String?,
        authorRole: j['authorRole'] as String?,
        parentCommentId: j['parentCommentId'] as String?,
        body: (j['body'] as String?) ?? '',
        createdAt: j['createdAt'] == null
            ? null
            : DateTime.tryParse(j['createdAt'] as String),
      );
}

// ---------------------------------------------------------------------------
// Homework
// ---------------------------------------------------------------------------
class HomeworkPost {
  final String id;
  final String classId;
  final String? className;
  final String authorId;
  final String? authorName;
  final DateTime date;
  final String title;
  final String body;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  const HomeworkPost({
    required this.id,
    required this.classId,
    required this.authorId,
    required this.date,
    required this.title,
    required this.body,
    this.className,
    this.authorName,
    this.createdAt,
    this.updatedAt,
  });
  factory HomeworkPost.fromJson(Map<String, dynamic> j) => HomeworkPost(
        id: j['id'] as String,
        classId: (j['classId'] as String?) ?? '',
        className: j['className'] as String?,
        authorId: (j['authorId'] as String?) ?? '',
        authorName: j['authorName'] as String?,
        date: DateTime.tryParse((j['date'] as String?) ?? '') ??
            DateTime(1970),
        title: (j['title'] as String?) ?? '',
        body: (j['body'] as String?) ?? '',
        createdAt: j['createdAt'] == null
            ? null
            : DateTime.tryParse(j['createdAt'] as String),
        updatedAt: j['updatedAt'] == null
            ? null
            : DateTime.tryParse(j['updatedAt'] as String),
      );
}
