// -----------------------------------------------
// TerraRun – Data Models: Run & GpsPoint
// -----------------------------------------------

class GpsPoint {
  final double lat;
  final double lng;
  final double? altitude;
  final DateTime timestamp;

  const GpsPoint({
    required this.lat,
    required this.lng,
    this.altitude,
    required this.timestamp,
  });

  Map<String, dynamic> toJson() => {
        'lat': lat,
        'lng': lng,
        if (altitude != null) 'altitude': altitude,
        'timestamp': timestamp.toUtc().toIso8601String(),
      };
}

class RunModel {
  final String id;
  final String userId;
  final DateTime startedAt;
  final DateTime? endedAt;
  final double distanceM;
  final int durationS;
  final double? avgPace;
  final String status;
  final DateTime createdAt;

  const RunModel({
    required this.id,
    required this.userId,
    required this.startedAt,
    this.endedAt,
    this.distanceM = 0,
    this.durationS = 0,
    this.avgPace,
    this.status = 'completed',
    required this.createdAt,
  });

  factory RunModel.fromJson(Map<String, dynamic> json) {
    return RunModel(
      id: json['id'] as String,
      userId: json['user_id'] as String,
      startedAt: DateTime.parse(json['started_at'] as String),
      endedAt: json['ended_at'] != null
          ? DateTime.parse(json['ended_at'] as String)
          : null,
      distanceM: (json['distance_m'] as num?)?.toDouble() ?? 0,
      durationS: (json['duration_s'] as num?)?.toInt() ?? 0,
      avgPace: (json['avg_pace'] as num?)?.toDouble(),
      status: json['status'] as String? ?? 'completed',
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  /// Distance in km
  double get distanceKm => distanceM / 1000;

  /// Duration as a formatted string (e.g. "12:34")
  String get durationFormatted {
    final mins = durationS ~/ 60;
    final secs = durationS % 60;
    return '${mins.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}';
  }

  /// Pace as "X:XX /km" string
  String get paceFormatted {
    if (avgPace == null || avgPace! <= 0) return '--:--';
    final totalSecs = avgPace!.toInt();
    final m = totalSecs ~/ 60;
    final s = totalSecs % 60;
    return '$m:${s.toString().padLeft(2, '0')} /km';
  }
}
