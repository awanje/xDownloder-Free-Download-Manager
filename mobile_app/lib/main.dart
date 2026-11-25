import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:shared_preferences_android/shared_preferences_android.dart';
import 'package:shared_preferences_foundation/shared_preferences_foundation.dart';

import 'config.dart';
import 'screens/auth_gate.dart';
import 'screens/setup_screen.dart';
import 'supabase_client.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Workaround: this Flutter SDK build isn't emitting the dartPluginClass
  // metadata that normally auto-registers federated plugins, so
  // shared_preferences silently falls back to a channel the native side no
  // longer implements. Registering explicitly here sidesteps that bug.
  // (Confirmed needed on Android; applied to iOS/macOS preemptively too
  // since it's the same underlying flutter_tools bug and this machine has
  // no Mac to verify it against directly.)
  if (!kIsWeb && Platform.isAndroid) {
    SharedPreferencesAndroid.registerWith();
  } else if (!kIsWeb && (Platform.isIOS || Platform.isMacOS)) {
    SharedPreferencesFoundation.registerWith();
  }
  runApp(const XDownloaderApp());
}

class XDownloaderApp extends StatelessWidget {
  const XDownloaderApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'X Downloader',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF4F46E5),
        useMaterial3: true,
        brightness: Brightness.light,
      ),
      darkTheme: ThemeData(
        colorSchemeSeed: const Color(0xFF4F46E5),
        useMaterial3: true,
        brightness: Brightness.dark,
      ),
      home: const RootDecider(),
    );
  }
}

class RootDecider extends StatefulWidget {
  const RootDecider({super.key});

  @override
  State<RootDecider> createState() => _RootDeciderState();
}

class _RootDeciderState extends State<RootDecider> {
  bool _loading = true;
  bool _configured = false;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final cfg = await AppConfig.load();
    if (cfg != null) {
      await initSupabase(cfg.$1, cfg.$2);
      _configured = true;
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (!_configured) {
      return SetupScreen(onDone: () async {
        setState(() => _loading = true);
        await _init();
      });
    }
    return const AuthGate();
  }
}
