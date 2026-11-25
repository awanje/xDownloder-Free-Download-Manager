import 'package:flutter/material.dart';

import '../config.dart';
import '../supabase_client.dart';

class SetupScreen extends StatefulWidget {
  final VoidCallback onDone;
  const SetupScreen({super.key, required this.onDone});

  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> {
  final _urlCtrl = TextEditingController();
  final _keyCtrl = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _save() async {
    final url = _urlCtrl.text.trim();
    final key = _keyCtrl.text.trim();
    if (url.isEmpty || key.isEmpty) {
      setState(() => _error = 'Enter both the project URL and anon key.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await AppConfig.save(url, key);
      await initSupabase(url, key);
      widget.onDone();
    } catch (e) {
      setState(() {
        _error = e.toString();
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Icon(Icons.cloud_sync_rounded, size: 64, color: Theme.of(context).colorScheme.primary),
              const SizedBox(height: 16),
              Text('Connect X Downloader', style: Theme.of(context).textTheme.headlineSmall,
                  textAlign: TextAlign.center),
              const SizedBox(height: 8),
              const Text(
                'Paste the same Supabase project URL and anon key you set up '
                'in the desktop app\'s Settings → Cloud Sync tab.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              TextField(
                controller: _urlCtrl,
                decoration: const InputDecoration(labelText: 'Project URL', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _keyCtrl,
                decoration: const InputDecoration(labelText: 'Anon key', border: OutlineInputBorder()),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!, style: const TextStyle(color: Colors.red)),
              ],
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _save,
                child: _busy
                    ? const SizedBox(
                        height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Continue'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
