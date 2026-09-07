import 'package:flutter_test/flutter_test.dart';
import 'package:lms_app/models/bulk_import.dart';
import 'package:lms_app/models/user.dart';

void main() {
  group('AppUser', () {
    test('parses the API envelope', () {
      final user = AppUser.fromJson({
        'id': 'u1',
        'name': 'Amira',
        'email': 'amira@school.local',
        'role': 'student',
        'isActive': true,
        'mustChangePassword': false,
        'createdAt': '2026-01-15T09:30:00',
        'classId': 'c1',
        'className': '9-A',
        'gradeId': 'g1',
        'gradeName': 'Grade 9',
      });

      expect(user.id, 'u1');
      expect(user.isStudent, isTrue);
      expect(user.canAuthor, isFalse);
      expect(user.className, '9-A');
      expect(user.createdAt, DateTime(2026, 1, 15, 9, 30));
    });

    test('defaults mustChangePassword to false when the key is absent', () {
      // Older cached snapshots in SharedPreferences predate the field; they
      // must not deserialize into "force this user to change their password".
      final user = AppUser.fromJson({
        'id': 'u1',
        'name': 'A',
        'email': 'a@t.local',
        'role': 'student',
        'isActive': true,
      });
      expect(user.mustChangePassword, isFalse);
    });

    test('carries mustChangePassword through a JSON round trip', () {
      final user = AppUser.fromJson({
        'id': 'u1',
        'name': 'A',
        'email': 'a@t.local',
        'role': 'instructor',
        'isActive': true,
        'mustChangePassword': true,
      });
      expect(user.mustChangePassword, isTrue);

      // The app caches this snapshot and re-reads it on the next launch. If
      // the flag were dropped here, a bulk-imported user would sail past the
      // forced change screen simply by restarting the app.
      final restored = AppUser.fromJson(user.toJson());
      expect(restored.mustChangePassword, isTrue);
    });

    test('role predicates are mutually exclusive', () {
      AppUser withRole(String role) => AppUser.fromJson({
            'id': 'u',
            'name': 'n',
            'email': 'e@t.local',
            'role': role,
            'isActive': true,
          });

      expect(withRole('admin').canAuthor, isTrue);
      expect(withRole('instructor').canAuthor, isTrue);
      expect(withRole('parent').isParent, isTrue);
      expect(withRole('parent').canAuthor, isFalse);
      expect(withRole('student').isStudent, isTrue);
    });
  });

  group('BulkImportResult', () {
    test('reads a per-row temporary password on created rows', () {
      // The server used to return one shared password for the whole import.
      // Each created user now gets their own, and this response is the only
      // place it is ever readable.
      final result = BulkImportResult.fromJson({
        'created': [
          {'row': 2, 'email': 'a@t.local', 'id': 'u1', 'temporaryPassword': 'aaa-111'},
          {'row': 3, 'email': 'b@t.local', 'id': 'u2', 'temporaryPassword': 'bbb-222'},
        ],
        'updated': [
          {'row': 4, 'email': 'c@t.local', 'id': 'u3'},
        ],
        'skipped': [],
        'errors': [],
        'notice': 'hand these out now',
      });

      expect(result.created, hasLength(2));
      expect(result.created.map((r) => r.temporaryPassword), ['aaa-111', 'bbb-222']);
      // Updated rows keep their existing password, so they carry none.
      expect(result.updated.single.temporaryPassword, isNull);
      expect(result.totalTouched, 3);
    });

    test('tolerates a response with every list missing', () {
      final result = BulkImportResult.fromJson({});
      expect(result.totalTouched, 0);
      expect(result.notice, isEmpty);
    });

    test('collects skipped rows and errors with their reasons', () {
      final result = BulkImportResult.fromJson({
        'skipped': [
          {'row': 5, 'email': 'd@t.local', 'reason': 'already exists as parent'},
        ],
        'errors': [
          {'row': 6, 'error': 'email looks malformed.'},
        ],
      });
      expect(result.skipped.single.reason, contains('already exists'));
      expect(result.errors.single.row, 6);
    });
  });
}
