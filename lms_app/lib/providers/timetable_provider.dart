import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/timetable.dart';
import '../services/api_service.dart';

final classTimetableProvider =
    FutureProvider.autoDispose.family<TimetableWeek, String>((ref, classId) async {
  return ApiService.instance.getClassTimetable(classId);
});

final myTimetableProvider =
    FutureProvider.autoDispose<TimetableWeek>((ref) async {
  return ApiService.instance.getMyTimetable();
});

final nowNextProvider =
    FutureProvider.autoDispose<NowNext>((ref) async {
  return ApiService.instance.getNowNext();
});
