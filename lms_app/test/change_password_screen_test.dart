import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lms_app/screens/auth/change_password_screen.dart';

/// Widget tests for the screen that closes the "nobody can ever change their
/// password" gap. They exercise the client-side guards only — a form that
/// fails validation never reaches the network, so no API stub is needed.
void main() {
  Future<void> pump(WidgetTester tester, {bool forced = false}) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ChangePasswordScreen(forced: forced),
        ),
      ),
    );
  }

  /// The submit button, not the AppBar title of the same name.
  Future<void> submit(WidgetTester tester) async {
    final button = find.widgetWithText(ElevatedButton, 'Change password');
    await tester.ensureVisible(button);
    await tester.tap(button);
    await tester.pump();
  }

  testWidgets('renders the three password fields', (tester) async {
    await pump(tester);
    expect(find.text('Current password'), findsOneWidget);
    expect(find.text('New password'), findsOneWidget);
    expect(find.text('Confirm new password'), findsOneWidget);
    expect(find.widgetWithText(AppBar, 'Change password'), findsOneWidget);
  });

  testWidgets('refuses a new password shorter than eight characters', (tester) async {
    await pump(tester);
    final fields = find.byType(TextFormField);

    await tester.enterText(fields.at(0), 'current-pw');
    await tester.enterText(fields.at(1), 'short');
    await tester.enterText(fields.at(2), 'short');
    await submit(tester);

    expect(find.text('Password must be at least 8 characters'), findsOneWidget);
  });

  testWidgets('refuses a confirmation that does not match', (tester) async {
    await pump(tester);
    final fields = find.byType(TextFormField);

    await tester.enterText(fields.at(0), 'current-pw');
    await tester.enterText(fields.at(1), 'a-good-password');
    await tester.enterText(fields.at(2), 'a-different-password');
    await submit(tester);

    expect(find.text('Passwords do not match'), findsOneWidget);
  });

  testWidgets('the show/hide toggle flips obscureText on every field',
      (tester) async {
    await pump(tester);
    bool allObscured() => tester
        .widgetList<EditableText>(find.byType(EditableText))
        .every((w) => w.obscureText);

    expect(allObscured(), isTrue);
    final toggle = find.text('Show passwords');
    await tester.ensureVisible(toggle);
    await tester.tap(toggle);
    await tester.pump();
    expect(allObscured(), isFalse);
  });

  group('forced mode', () {
    testWidgets('explains why and offers no way back', (tester) async {
      await pump(tester, forced: true);

      expect(find.text('Choose your own password'), findsOneWidget);
      expect(find.text('Temporary password'), findsOneWidget);
      // No back button: this screen is the whole app until it is satisfied.
      expect(find.byType(BackButton), findsNothing);
      // Sign out is the only escape hatch.
      expect(find.widgetWithText(TextButton, 'Sign out'), findsOneWidget);
    });

    testWidgets('normal mode shows neither the banner nor a sign-out',
        (tester) async {
      await pump(tester, forced: false);
      expect(find.text('Choose your own password'), findsNothing);
      expect(find.widgetWithText(TextButton, 'Sign out'), findsNothing);
    });
  });
}
