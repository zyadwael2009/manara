/// Reusable form validators for text fields.
class Validators {
  Validators._();

  static String? required(String? v, {String field = 'This field'}) {
    if (v == null || v.trim().isEmpty) return '$field is required';
    return null;
  }

  static String? email(String? v) {
    if (v == null || v.trim().isEmpty) return 'Email is required';
    final e = v.trim();
    // Deliberately loose — the server does the authoritative check.
    if (!e.contains('@') || !e.contains('.')) return 'Enter a valid email';
    return null;
  }

  static String? password(String? v) {
    if (v == null || v.isEmpty) return 'Password is required';
    if (v.length < 8) return 'Password must be at least 8 characters';
    return null;
  }

  static String? Function(String?) minLength(int n, {String field = 'This field'}) {
    return (v) {
      if (v == null || v.trim().length < n) return '$field must be at least $n characters';
      return null;
    };
  }
}
