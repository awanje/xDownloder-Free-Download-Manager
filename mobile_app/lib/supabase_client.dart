import 'package:supabase_flutter/supabase_flutter.dart';

Future<void> initSupabase(String url, String anonKey) async {
  await Supabase.initialize(url: url, publishableKey: anonKey);
}

SupabaseClient get supabase => Supabase.instance.client;
