// Phase 13 — timetable payloads.

class PeriodCourse {
  final String id;
  final String title;
  final String category;
  const PeriodCourse({required this.id, required this.title, required this.category});
  factory PeriodCourse.fromJson(Map<String, dynamic> j) => PeriodCourse(
        id: j['id'] as String,
        title: (j['title'] ?? '') as String,
        category: (j['category'] ?? 'general') as String,
      );
}

class Period {
  final String id;
  final String classId;
  final String? courseId;
  final int dayOfWeek; // 0=Mon .. 6=Sun
  final String startTime; // "09:00"
  final String endTime;   // "09:45"
  final String? room;
  final PeriodCourse? course;
  final String? teacherName;
  final String? teacherId;
  final String? className; // populated on teacher-week view
  final bool isOverride;
  final String? note;
  // Phase 27 — optional Zoom / Meet URL for this recurring period. When
  // present AND the period is currently live, the client renders a
  // "Join" button that opens the URL in a new tab.
  final String? meetingUrl;

  const Period({
    required this.id,
    required this.classId,
    required this.dayOfWeek,
    required this.startTime,
    required this.endTime,
    this.courseId,
    this.room,
    this.course,
    this.teacherName,
    this.teacherId,
    this.className,
    this.isOverride = false,
    this.note,
    this.meetingUrl,
  });

  factory Period.fromJson(Map<String, dynamic> j) => Period(
        id: (j['id'] as String?) ?? '',
        classId: (j['classId'] as String?) ?? '',
        courseId: j['courseId'] as String?,
        dayOfWeek: (j['dayOfWeek'] as num?)?.toInt() ?? 0,
        startTime: (j['startTime'] as String?) ?? '',
        endTime: (j['endTime'] as String?) ?? '',
        room: j['room'] as String?,
        course: j['course'] == null
            ? null
            : PeriodCourse.fromJson(j['course'] as Map<String, dynamic>),
        teacherName: j['teacherName'] as String?,
        teacherId: j['teacherId'] as String?,
        className: j['className'] as String?,
        isOverride: (j['isOverride'] as bool?) ?? false,
        note: j['note'] as String?,
        meetingUrl: j['meetingUrl'] as String?,
      );
}

class TimetableOverride {
  final String id;
  final String classId;
  final String date; // "YYYY-MM-DD"
  final String kind; // "canceled" | "custom"
  final String? periodId;
  final String? courseId;
  final String? courseTitle;
  final String? startTime;
  final String? endTime;
  final String? room;
  final String? note;

  const TimetableOverride({
    required this.id,
    required this.classId,
    required this.date,
    required this.kind,
    this.periodId,
    this.courseId,
    this.courseTitle,
    this.startTime,
    this.endTime,
    this.room,
    this.note,
  });

  factory TimetableOverride.fromJson(Map<String, dynamic> j) => TimetableOverride(
        id: j['id'] as String,
        classId: (j['classId'] as String?) ?? '',
        date: (j['date'] as String?) ?? '',
        kind: (j['kind'] as String?) ?? 'custom',
        periodId: j['periodId'] as String?,
        courseId: j['courseId'] as String?,
        courseTitle: j['courseTitle'] as String?,
        startTime: j['startTime'] as String?,
        endTime: j['endTime'] as String?,
        room: j['room'] as String?,
        note: j['note'] as String?,
      );
}

class TimetableWeek {
  final String? classId;
  final String? className;
  final List<Period> periods;
  final List<TimetableOverride> overridesInWindow;

  const TimetableWeek({
    this.classId,
    this.className,
    required this.periods,
    this.overridesInWindow = const [],
  });

  factory TimetableWeek.fromJson(Map<String, dynamic> j) => TimetableWeek(
        classId: j['classId'] as String?,
        className: j['className'] as String?,
        periods: (j['periods'] as List<dynamic>? ?? [])
            .map((e) => Period.fromJson(e as Map<String, dynamic>))
            .toList(),
        overridesInWindow: (j['overridesInWindow'] as List<dynamic>? ?? [])
            .map((e) => TimetableOverride.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class NowNextSlot {
  final Period period;
  final String? endsAt;
  final int? endsInMinutes;
  final String? startsAt;
  final int? startsInMinutes;
  final bool sameDay;

  const NowNextSlot({
    required this.period,
    this.endsAt,
    this.endsInMinutes,
    this.startsAt,
    this.startsInMinutes,
    this.sameDay = true,
  });

  factory NowNextSlot.fromJson(Map<String, dynamic> j) => NowNextSlot(
        period: Period.fromJson(j['period'] as Map<String, dynamic>),
        endsAt: j['endsAt'] as String?,
        endsInMinutes: (j['endsInMinutes'] as num?)?.toInt(),
        startsAt: j['startsAt'] as String?,
        startsInMinutes: (j['startsInMinutes'] as num?)?.toInt(),
        sameDay: (j['sameDay'] as bool?) ?? true,
      );
}

class NowNext {
  final NowNextSlot? now;
  final NowNextSlot? next;
  const NowNext({this.now, this.next});
  factory NowNext.fromJson(Map<String, dynamic> j) => NowNext(
        now: j['now'] == null ? null : NowNextSlot.fromJson(j['now'] as Map<String, dynamic>),
        next: j['next'] == null ? null : NowNextSlot.fromJson(j['next'] as Map<String, dynamic>),
      );
}

class PeriodInput {
  final String courseId;
  final int dayOfWeek;
  final String startTime;
  final String endTime;
  final String? room;
  // Phase 27 — optional Meet/Zoom URL. Server validates the scheme.
  final String? meetingUrl;
  const PeriodInput({
    required this.courseId,
    required this.dayOfWeek,
    required this.startTime,
    required this.endTime,
    this.room,
    this.meetingUrl,
  });
  Map<String, dynamic> toJson() => {
        'courseId': courseId,
        'dayOfWeek': dayOfWeek,
        'startTime': startTime,
        'endTime': endTime,
        if (room != null && room!.isNotEmpty) 'room': room,
        if (meetingUrl != null && meetingUrl!.isNotEmpty)
          'meetingUrl': meetingUrl,
      };
}
