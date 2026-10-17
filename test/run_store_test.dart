import 'package:fitness_game_app/gps/run_fix.dart';
import 'package:fitness_game_app/services/run_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> payload(String id) => buildRunPayload(
  clientRunId: id,
  startedAt: DateTime.utc(2026),
  endedAt: DateTime.utc(2026, 1, 1, 0, 1),
  durationSeconds: 60,
  clientDistanceKm: 0.1,
  fixes: [RunFix(lat: 1, lng: 2, t: DateTime.utc(2026))],
);

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    RunQueue.saved.clear();
  });

  test('client run id is 32 hex characters', () {
    expect(newClientRunId(), matches(RegExp(r'^[0-9a-f]{32}$')));
    expect(newClientRunId(), isNot(newClientRunId()));
  });

  test('failed upload stays queued with the same id, success removes it', () async {
    final seen = <String>[];
    var online = false;
    RunQueue.uploader = (p) async {
      seen.add(p['client_run_id'] as String);
      return online
          ? {'success': true, 'data': {'distance_km': 1.0}}
          : {'success': false, 'network': true};
    };

    await RunQueue.enqueue(payload('a'));
    await RunQueue.flush();
    expect(await RunQueue.isPending('a'), isTrue);

    online = true;
    await RunQueue.flush();
    expect(seen, ['a', 'a']);
    expect(await RunQueue.pending(), isEmpty);
    expect(RunQueue.saved['a'], {'distance_km': 1.0});
  });

  test('a server error keeps the run but tries the next one', () async {
    RunQueue.uploader = (p) async => p['client_run_id'] == 'a'
        ? {'success': false, 'message': 'bad'}
        : {'success': true, 'data': {}};
    await RunQueue.enqueue(payload('a'));
    await RunQueue.enqueue(payload('b'));
    await RunQueue.flush();
    expect((await RunQueue.pending()).map((r) => r['client_run_id']), ['a']);
  });

  test('the queue keeps only the newest runs', () async {
    for (var i = 0; i < RunQueue.maxRuns + 3; i++) {
      await RunQueue.enqueue(payload('r$i'));
    }
    final ids = (await RunQueue.pending()).map((r) => r['client_run_id']);
    expect(ids.length, RunQueue.maxRuns);
    expect(ids.first, 'r3');
  });

  test('an unfinished run is saved, reloaded and queued as finished', () async {
    final recorder = await RunRecorder.start(
      startedAt: DateTime.utc(2026, 10, 17, 6),
    );
    for (var i = 0; i < 300; i++) {
      recorder.add(
        RunFix(
          lat: 10 + i * 0.00003,
          lng: 20,
          t: DateTime.utc(2026, 10, 17, 6).add(Duration(seconds: i)),
          accuracyM: 5,
        ),
      );
    }
    await recorder.flush();

    final loaded = await RunRecorder.load();
    expect(loaded!.clientRunId, recorder.clientRunId);
    expect(loaded.fixes.length, 300);

    expect(await RunQueue.recoverUnfinished(), isTrue);
    final queued = (await RunQueue.pending()).single;
    expect(queued['client_run_id'], recorder.clientRunId);
    expect(queued['ended_at'], '2026-10-17T06:04:59.000Z');
    expect((queued['fixes'] as List).length, 300);
    expect(await RunRecorder.load(), isNull);
  });
}
