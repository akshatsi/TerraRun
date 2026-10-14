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
}
