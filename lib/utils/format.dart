class Fmt {
  Fmt._();

  /// Splits an area in square metres into a display value and unit.
  /// From 10,000 m² up it reads in km² (530,000 m² is 0.53 KM²).
  static ({String value, String unit}) area(double sqm) {
    if (sqm >= 10000) {
      return (value: (sqm / 1000000).toStringAsFixed(2), unit: 'KM²');
    }
    return (value: sqm.toStringAsFixed(0), unit: 'M²');
  }

  static String areaText(double sqm) {
    final a = area(sqm);
    return '${a.value} ${a.unit}';
  }

  static String duration(int totalSeconds) {
    final hours = totalSeconds ~/ 3600;
    final minutes = (totalSeconds % 3600) ~/ 60;
    final seconds = totalSeconds % 60;

    String two(int n) => n.toString().padLeft(2, '0');

    if (hours > 0) {
      return '${two(hours)}:${two(minutes)}:${two(seconds)}';
    }
    return '${two(minutes)}:${two(seconds)}';
  }

  static String dateKey(DateTime d) {
    return '${d.year.toString().padLeft(4, '0')}-'
        '${d.month.toString().padLeft(2, '0')}-'
        '${d.day.toString().padLeft(2, '0')}';
  }

  /// "just now", "5m ago", "2h ago", "3d ago", then a date.
  static String timeAgo(DateTime then, {DateTime? now}) {
    final diff = (now ?? DateTime.now()).difference(then);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return dateKey(then.toLocal());
  }

  /// [timeAgo] for an ISO 8601 string; empty if it does not parse.
  static String timeAgoFrom(String? iso, {DateTime? now}) {
    final then = DateTime.tryParse(iso ?? '');
    return then == null ? '' : timeAgo(then, now: now);
  }

  static String _grouped(int n) {
    final digits = n.toString();
    final out = StringBuffer();
    for (var i = 0; i < digits.length; i++) {
      if (i > 0 && (digits.length - i) % 3 == 0) out.write(',');
      out.write(digits[i]);
    }
    return out.toString();
  }

  /// "4.71 km · Loop +3,240 m²" for a run from the feed or a profile.
  static String runSummary(Map<String, dynamic> run) {
    final km = ((run['distance_km'] ?? 0) as num).toDouble();
    final awarded = ((run['awarded_area_sq_m'] ?? 0) as num).toDouble();
    final kind = (run['territory_kind'] ?? '').toString();

    final text = StringBuffer('${km.toStringAsFixed(2)} km');
    if (awarded >= 1) {
      final label = kind.isEmpty
          ? ''
          : '${kind[0].toUpperCase()}${kind.substring(1)} ';
      final area = awarded >= 10000
          ? '${(awarded / 1000000).toStringAsFixed(2)} km²'
          : '${_grouped(awarded.round())} m²';
      text.write(' · $label+$area');
    }
    return text.toString();
  }

  /// Pace as "m:ss" from seconds per km ("6:22"). "—" when unknown.
  static String pace(num? secondsPerKm) {
    if (secondsPerKm == null || secondsPerKm <= 0 || !secondsPerKm.isFinite) {
      return '—';
    }
    final total = secondsPerKm.round();
    return '${total ~/ 60}:${(total % 60).toString().padLeft(2, '0')}';
  }

  /// [duration] for fractional seconds, rounded to the nearest second.
  static String durationFrom(num seconds) {
    return duration(seconds.isFinite && seconds > 0 ? seconds.round() : 0);
  }

  /// A whole number of square metres with thousands commas ("2,720").
  static String squareMetres(double sqm) => _grouped(sqm.round());

  /// "Follow me on TerraRun — Akshat · 25.5 km run · 2,720 m² territory".
  /// Leaves out the territory part when there is none.
  static String shareText({
    required String name,
    required double distanceKm,
    required double territorySqM,
  }) {
    final parts = <String>[name, '${distanceKm.toStringAsFixed(1)} km run'];
    if (territorySqM >= 1) {
      final area = territorySqM >= 10000
          ? '${(territorySqM / 1000000).toStringAsFixed(2)} km²'
          : '${squareMetres(territorySqM)} m²';
      parts.add('$area territory');
    }
    return 'Follow me on TerraRun — ${parts.join(' · ')}';
  }
}
