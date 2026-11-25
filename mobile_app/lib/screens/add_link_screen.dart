import 'package:flutter/material.dart';

import '../supabase_client.dart';

class AddLinkScreen extends StatefulWidget {
  const AddLinkScreen({super.key});

  @override
  State<AddLinkScreen> createState() => _AddLinkScreenState();
}

class _AddLinkScreenState extends State<AddLinkScreen> {
  final _urlCtrl = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _submit() async {
    final url = _urlCtrl.text.trim();
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      setState(() => _error = 'Enter a valid http:// or https:// link.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final uid = supabase.auth.currentUser!.id;
      await supabase.from('downloads').insert({
        'user_id': uid,
        'source': 'mobile',
        'url': url,
        'status': 'Pending',
      });
      if (mounted) Navigator.of(context).pop();
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
      appBar: AppBar(title: const Text('Add Link')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Paste a video or file link. It\'ll be picked up and downloaded by '
              'your PC next time X Downloader is running and you\'re signed in there '
              '(app stores don\'t allow downloading video directly on mobile).',
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _urlCtrl,
              decoration: const InputDecoration(labelText: 'Link', border: OutlineInputBorder()),
              autofocus: true,
              maxLines: 3,
              minLines: 1,
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: Colors.red)),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: _busy ? null : _submit,
              icon: _busy
                  ? const SizedBox(
                      height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.send),
              label: const Text('Send to my PC'),
            ),
          ],
        ),
      ),
    );
  }
}
