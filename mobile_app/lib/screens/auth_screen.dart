import 'package:flutter/material.dart';

import '../supabase_client.dart';

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _emailCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  bool _busy = false;
  String? _error;
  String? _info;

  Future<void> _signIn() async {
    setState(() {
      _busy = true;
      _error = null;
      _info = null;
    });
    try {
      await supabase.auth
          .signInWithPassword(email: _emailCtrl.text.trim(), password: _passCtrl.text);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _signUp() async {
    setState(() {
      _busy = true;
      _error = null;
      _info = null;
    });
    try {
      await supabase.auth.signUp(email: _emailCtrl.text.trim(), password: _passCtrl.text);
      setState(() => _info = 'Account created. If email confirmation is required, '
          'check your inbox, then sign in.');
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
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
              Icon(Icons.download_rounded, size: 64, color: Theme.of(context).colorScheme.primary),
              const SizedBox(height: 16),
              Text('X Downloader', style: Theme.of(context).textTheme.headlineMedium,
                  textAlign: TextAlign.center),
              const SizedBox(height: 4),
              const Text('Sign in to see downloads across your devices', textAlign: TextAlign.center),
              const SizedBox(height: 24),
              TextField(
                controller: _emailCtrl,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(labelText: 'Email', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _passCtrl,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Password', border: OutlineInputBorder()),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!, style: const TextStyle(color: Colors.red)),
              ],
              if (_info != null) ...[
                const SizedBox(height: 12),
                Text(_info!, style: const TextStyle(color: Colors.green)),
              ],
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _busy ? null : _signIn,
                child: _busy
                    ? const SizedBox(
                        height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Sign In'),
              ),
              const SizedBox(height: 8),
              OutlinedButton(
                onPressed: _busy ? null : _signUp,
                child: const Text('Create Account'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
