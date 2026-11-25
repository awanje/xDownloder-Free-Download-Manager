import 'package:flutter/material.dart';

import '../models/download_row.dart';

class DownloadTile extends StatelessWidget {
  final DownloadRow row;
  const DownloadTile({super.key, required this.row});

  Color _statusColor(BuildContext context) {
    switch (row.status) {
      case 'Completed':
        return Colors.green;
      case 'Error':
        return Colors.red;
      case 'Cancelled':
        return Colors.grey;
      case 'Downloading':
      case 'Connecting':
        return Theme.of(context).colorScheme.primary;
      case 'Paused':
        return Colors.orange;
      case 'Select Quality':
        return Colors.purple;
      default:
        return Colors.blueGrey;
    }
  }

  String _formatSize(int bytes) {
    if (bytes < 0) return '';
    const units = ['B', 'KB', 'MB', 'GB'];
    double v = bytes.toDouble();
    int i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i++;
    }
    return '${v.toStringAsFixed(1)} ${units[i]}';
  }

  IconData get _sourceIcon => row.source == 'mobile' ? Icons.phone_iphone : Icons.desktop_windows;

  @override
  Widget build(BuildContext context) {
    final showProgress = row.status == 'Downloading' || row.status == 'Connecting';
    final color = _statusColor(context);
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(_sourceIcon, size: 16, color: Colors.grey),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    row.filename.isNotEmpty ? row.filename : row.url,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: color.withAlpha(38),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    row.status,
                    style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(width: 8),
                if (row.totalSize > 0)
                  Text(_formatSize(row.totalSize), style: const TextStyle(fontSize: 12, color: Colors.grey)),
                const Spacer(),
                if (row.deviceName != null && row.deviceName!.isNotEmpty)
                  Text(row.deviceName!, style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ],
            ),
            if (showProgress) ...[
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(value: row.progress.clamp(0, 1), minHeight: 6),
              ),
            ],
            if (row.error.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(row.error, style: const TextStyle(color: Colors.red, fontSize: 12),
                  maxLines: 2, overflow: TextOverflow.ellipsis),
            ],
          ],
        ),
      ),
    );
  }
}
