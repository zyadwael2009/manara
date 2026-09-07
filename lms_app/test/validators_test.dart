import 'package:flutter_test/flutter_test.dart';
import 'package:lms_app/core/utils/friendly_error.dart';
import 'package:lms_app/core/utils/validators.dart';
import 'package:lms_app/services/api_service.dart';

void main() {
  group('Validators.password', () {
    test('rejects empty and short values', () {
      expect(Validators.password(null), isNotNull);
      expect(Validators.password(''), isNotNull);
      expect(Validators.password('short7'), isNotNull);
    });

    test('accepts eight characters, matching the server rule', () {
      expect(Validators.password('12345678'), isNull);
      expect(Validators.password('a-decent-password'), isNull);
    });

    test('does not trim — a password of spaces is still eight characters', () {
      // Deliberate: the server hashes exactly what it is sent, so the client
      // must not quietly disagree with it about what the password is.
      expect(Validators.password('        '), isNull);
    });
  });

  group('Validators.email', () {
    test('requires an @ and a dot', () {
      expect(Validators.email('amira'), isNotNull);
      expect(Validators.email('amira@school'), isNotNull);
      expect(Validators.email(''), isNotNull);
      expect(Validators.email(null), isNotNull);
    });

    test('accepts an ordinary address', () {
      expect(Validators.email('amira@school.local'), isNull);
      expect(Validators.email('  amira@school.local  '), isNull);
    });
  });

  group('Validators.required / minLength', () {
    test('required rejects whitespace-only input', () {
      expect(Validators.required('   '), isNotNull);
      expect(Validators.required('x'), isNull);
    });

    test('minLength names the field in its message', () {
      final check = Validators.minLength(3, field: 'Class name');
      expect(check('ab'), contains('Class name'));
      expect(check('abc'), isNull);
    });
  });

  group('friendlyError', () {
    test('never leaks a raw transport error to the screen', () {
      // ApiException(0) is what a CORS/DNS/offline failure arrives as. The
      // user should not be shown "ClientException: Failed to fetch".
      final message = friendlyError(ApiException(0, 'ClientException: Failed to fetch'));
      expect(message, isNot(contains('ClientException')));
      expect(message.toLowerCase(), contains('connection'));
    });

    test('explains an expired session', () {
      final message = friendlyError(SessionExpiredException('nope'));
      expect(message.toLowerCase(), contains('sign in'));
    });

    test('handles null', () {
      expect(friendlyError(null), isNotEmpty);
    });
  });
}
