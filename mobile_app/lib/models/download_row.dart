class DownloadRow {
  final String id;
  final String source;
  final String? deviceName;
  final String url;
  final String filename;
  final String kind;
  final String status;
  final double progress;
  final int totalSize;
  final int downloadedBytes;
  final double speedBps;
  final String error;
  final DateTime createdAt;
  final DateTime updatedAt;

  DownloadRow({
    required this.id,
    required this.source,
    this.deviceName,
    required this.url,
    required this.filename,
    required this.kind,
    required this.status,
    required this.progress,
    required this.totalSize,
    required this.downloadedBytes,
    required this.speedBps,
    required this.error,
    required this.createdAt,
    required this.updatedAt,
  });

  factory DownloadRow.fromMap(Map<String, dynamic> m) => DownloadRow(
        id: m['id'] as String,
        source: m['source'] as String? ?? 'desktop',
        deviceName: m['device_name'] as String?,
        url: m['url'] as String? ?? '',
        filename: m['filename'] as String? ?? '',
        kind: m['kind'] as String? ?? 'http',
        status: m['status'] as String? ?? 'Pending',
        progress: (m['progress'] as num?)?.toDouble() ?? 0,
        totalSize: (m['total_size'] as num?)?.toInt() ?? -1,
        downloadedBytes: (m['downloaded_bytes'] as num?)?.toInt() ?? 0,
        speedBps: (m['speed_bps'] as num?)?.toDouble() ?? 0,
        error: m['error'] as String? ?? '',
        createdAt: DateTime.tryParse(m['created_at'] as String? ?? '') ?? DateTime.now(),
        updatedAt: DateTime.tryParse(m['updated_at'] as String? ?? '') ?? DateTime.now(),
      );
}
