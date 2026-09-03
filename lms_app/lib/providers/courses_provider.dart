import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/course.dart';
import '../services/api_service.dart';

/// Public catalog (used by teacher home / admin curriculum browsing).
@immutable
class CatalogState {
  final bool loading;
  final String? error;
  final List<Course> courses;
  final String search;
  final String? category;

  const CatalogState({
    this.loading = false,
    this.error,
    this.courses = const [],
    this.search = '',
    this.category,
  });

  CatalogState copyWith({
    bool? loading,
    String? error,
    List<Course>? courses,
    String? search,
    Object? category = _sentinel,
  }) =>
      CatalogState(
        loading: loading ?? this.loading,
        error: error,
        courses: courses ?? this.courses,
        search: search ?? this.search,
        category: identical(category, _sentinel) ? this.category : category as String?,
      );
}

const Object _sentinel = Object();

class CatalogNotifier extends StateNotifier<CatalogState> {
  CatalogNotifier() : super(const CatalogState());
  final _api = ApiService.instance;

  Future<void> refresh() async {
    state = state.copyWith(loading: true, error: null);
    try {
      final rows = await _api.listCourses(search: state.search, category: state.category);
      state = state.copyWith(loading: false, courses: rows);
    } on ApiException catch (e) {
      state = state.copyWith(loading: false, error: e.message);
    }
  }

  Future<void> setSearch(String q) async {
    state = state.copyWith(search: q);
    await refresh();
  }

  Future<void> setCategory(String? cat) async {
    state = state.copyWith(category: cat);
    await refresh();
  }
}

final catalogProvider =
    StateNotifierProvider<CatalogNotifier, CatalogState>((ref) => CatalogNotifier());

/// Single-course detail — FutureProvider.family so screens can watch by id.
final courseDetailProvider = FutureProvider.family<Course, String>((ref, id) async {
  return ApiService.instance.getCourse(id);
});

// -----------------------------------------------------------------------------
// Instructor "my courses" (via class_course_teachers on the server).
// -----------------------------------------------------------------------------
@immutable
class MyCoursesState {
  final bool loading;
  final String? error;
  final List<Course> courses;
  const MyCoursesState({this.loading = false, this.error, this.courses = const []});

  MyCoursesState copyWith({bool? loading, String? error, List<Course>? courses}) =>
      MyCoursesState(
        loading: loading ?? this.loading,
        error: error,
        courses: courses ?? this.courses,
      );
}

class MyCoursesNotifier extends StateNotifier<MyCoursesState> {
  MyCoursesNotifier() : super(const MyCoursesState());
  final _api = ApiService.instance;

  Future<void> refresh() async {
    state = state.copyWith(loading: true, error: null);
    try {
      final rows = await _api.listMyCourses();
      state = state.copyWith(loading: false, courses: rows);
    } on ApiException catch (e) {
      state = state.copyWith(loading: false, error: e.message);
    }
  }
}

final myCoursesProvider =
    StateNotifierProvider<MyCoursesNotifier, MyCoursesState>((ref) => MyCoursesNotifier());
