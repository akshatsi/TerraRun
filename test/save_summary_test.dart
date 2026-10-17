import 'package:fitness_game_app/services/run_service.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _response(Map<String, dynamic>? territory) => {
  'distance_km': 4.71,
  'processing': {'gap_count': 1, 'quality': 'poor'},
  'territory': ?territory,
};

void main() {
  test('loop shows the awarded area', () {
    final text = RunService.saveSummary(
      _response({'kind': 'loop', 'awarded_area_sq_m': 3240.0}),
    );
    expect(
      text,
      'Loop claimed · 3,240 m² · 1 GPS gap not counted · poor GPS quality',
    );
  });

  test('route shows the awarded area', () {
    final text = RunService.saveSummary(
      _response({'kind': 'route', 'awarded_area_sq_m': 840.4}),
    );
    expect(text, startsWith('Route claimed · 840 m²'));
  });

  test('none keeps the usual message', () {
    final text = RunService.saveSummary(
      _response({'kind': 'none', 'awarded_area_sq_m': 0.0}),
    );
    expect(text, startsWith('Saved 4.71 km'));
  });

  test('an older server without kind keeps the usual message', () {
    final text = RunService.saveSummary(
      _response({'awarded_area_sq_m': 500.0}),
    );
    expect(text, startsWith('Saved 4.71 km'));
    expect(
      RunService.saveSummary(_response(null)),
      startsWith('Saved 4.71 km'),
    );
  });
}
