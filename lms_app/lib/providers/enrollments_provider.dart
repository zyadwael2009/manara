import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/enrollment.dart';
import '../services/api_service.dart';

@immutable
class MyEnrollmentsState {
  final bool loading;
  final String? error;
  final List<Enrollment> enrollments;
  final List<PendingElective> pendingElectives;

  const MyEnrollmentsState({
    this.loading = false,
    this.error,
    this.enrollments = const [],
    this.pendingElectives = const [],
  });

  List<Enrollment> get active =>
      enrollments.where((e) => e.status == 'active' || e.status == 'completed').toList();

  MyEnrollmentsState copyWith({
    bool? loading,
    String? error,
    List<Enrollment>? enrollments,
    List<PendingElective>? pendingElectives,
  }) =>
      MyEnrollmentsState(
        loading: loading ?? this.loading,
        error: error,
        enrollments: enrollments ?? this.enrollments,
        pendingElectives: pendingElectives ?? this.pendingElectives,
      );
}

class MyEnrollmentsNotifier extends StateNotifier<MyEnrollmentsState> {
  MyEnrollmentsNotifier() : super(const MyEnrollmentsState());
  final _api = ApiService.instance;

  Future<void> refresh({String? currentUserId}) async {
    state = state.copyWith(loading: true, error: null);
    try {
      final enrolls = await _api.listMyEnrollments();
      List<PendingElective> pending = const [];
      if (currentUserId != null) {
        try {
          pending = await _api.getPendingElectives(currentUserId);
        } on ApiException {
          // Non-fatal — placement may not have happened yet.
          pending = const [];
        }
      }
      state = state.copyWith(
        loading: false,
        enrollments: enrolls,
        pendingElectives: pending,
      );
    } on ApiException catch (e) {
      state = state.copyWith(loading: false, error: e.message);
    }
  }
}

final myEnrollmentsProvider =
    StateNotifierProvider<MyEnrollmentsNotifier, MyEnrollmentsState>(
        (ref) => MyEnrollmentsNotifier());

// Single-lesson fetch — used by the lesson viewer.
final lessonProvider = FutureProvider.family((ref, String id) async {
  return ApiService.instance.getLesson(id);
});
