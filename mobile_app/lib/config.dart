import 'package:shared_preferences/shared_preferences.dart';

/// Local, per-install Supabase project configuration - matches the same
/// "paste your own project's URL/key" pattern as the desktop app's
/// Settings -> Cloud Sync tab. Nothing here is a secret: the anon key only
/// ever acts within the row-level-security policies in supabase_schema.sql.
class AppConfig {
  static const _urlKey = 'supabase_url';
  static const _anonKeyKey = 'supabase_anon_key';

  // Ships pointing at the app's own backend. The publishable key is safe to
  // embed; row-level security in supabase_schema.sql protects the data.
  // A user-saved override (Settings) still takes precedence.
  static const defaultUrl = 'https://kxadbtptfkfsiaxtiovc.supabase.co';
  static const defaultKey = 'sb_publishable_hWdxtZFbMkIyWwUMIq2Hbg_TRc33rRo';

  static Future<(String, String)?> load() async {
    final prefs = await SharedPreferences.getInstance();
    final url = prefs.getString(_urlKey);
    final key = prefs.getString(_anonKeyKey);
    if (url == null || key == null || url.isEmpty || key.isEmpty) {
      return (defaultUrl, defaultKey);
    }
    return (url, key);
  }

  static Future<void> save(String url, String anonKey) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_urlKey, url);
    await prefs.setString(_anonKeyKey, anonKey);
  }

  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_urlKey);
    await prefs.remove(_anonKeyKey);
  }
}
