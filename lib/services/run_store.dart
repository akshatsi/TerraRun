import 'dart:convert';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../gps/run_fix.dart';
import '../gps/track_filter.dart';
import 'run_service.dart';

/// A random 32-character hex id; the server uses it to ignore repeat uploads.
String newClientRunId() {
  final random = Random.secure();
  return List.generate(
    16,
    (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
  ).join();
}

/// The body of `POST /runs` (docs/gps-accuracy.md, section 1).
Map<String, dynamic> buildRunPayload({
  required String clientRunId,
  required DateTime startedAt,
  required DateTime endedAt,
  required int durationSeconds,
  required double clientDistanceKm,
  required List<RunFix> fixes,
}) {
  return {
    'client_run_id': clientRunId,
    'started_at': startedAt.toUtc().toIso8601String(),
    'ended_at': endedAt.toUtc().toIso8601String(),
    'duration_seconds': durationSeconds,
    'client_distance_km': double.parse(clientDistanceKm.toStringAsFixed(4)),
    'fixes': fixes.map((f) => f.toJson()).toList(),
  };
}

/// Saves the run in progress to the phone, so a killed app loses almost
/// nothing. Fixes go in chunks, so each save writes a small piece.
class RunRecorder {
  static const _metaKey = 'run.current.meta';
  static const _chunkPrefix = 'run.current.chunk.';
  static const chunkSize = 120;
  static const flushEvery = 10;

  final String clientRunId;
  final DateTime startedAt;

  final List<RunFix> _all = [];
  int _unsaved = 0;
  int _saved = 0;
  Future<void> _writing = Future.value();

  RunRecorder._(this.clientRunId, this.startedAt);

  List<RunFix> get fixes => List.unmodifiable(_all);

  /// Starts a new recording, replacing any earlier unfinished one.
  static Future<RunRecorder> start({
    String? clientRunId,
    DateTime? startedAt,
  }) async {
    final recorder = RunRecorder._(
      clientRunId ?? newClientRunId(),
      (startedAt ?? DateTime.now()).toUtc(),
    );
    await _clearStored();
    await recorder._write();
    return recorder;
  }

  void add(RunFix fix) {
    _all.add(fix);
    if (++_unsaved >= flushEvery) flush();
  }

  /// Writes what has not been saved yet. Safe to call often.
  Future<void> flush() {
    _unsaved = 0;
    _writing = _writing.then((_) => _write()).catchError((Object e) {
      debugPrint('Run save error: $e');
    });
    return _writing;
  }

  Future<void> _write() async {
    final prefs = await SharedPreferences.getInstance();
    final total = _all.length;
    final chunks = (total / chunkSize).ceil();
    // Only the chunk holding the first unsaved fix, and those after it.
    for (var i = _saved ~/ chunkSize; i < chunks; i++) {
      final part = _all.skip(i * chunkSize).take(chunkSize);
      await prefs.setString(
        '$_chunkPrefix$i',
        jsonEncode(part.map((f) => f.toJson()).toList()),
      );
    }
    _saved = total;
    await prefs.setString(
      _metaKey,
      jsonEncode({
        'client_run_id': clientRunId,
        'started_at': startedAt.toIso8601String(),
        'chunks': chunks,
      }),
    );
  }

  /// Drops the stored copy, after the run has moved to the upload queue.
  Future<void> discard() async {
    await _writing;
    await _clearStored();
  }

  /// Reads an unfinished run left by a killed app, or null.
  static Future<RunRecorder?> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_metaKey);
    if (raw == null) return null;
    try {
      final meta = jsonDecode(raw) as Map<String, dynamic>;
      final recorder = RunRecorder._(
        meta['client_run_id'] as String,
        DateTime.parse(meta['started_at'] as String),
      );
      for (var i = 0; i < (meta['chunks'] as int); i++) {
        final chunk = prefs.getString('$_chunkPrefix$i');
        if (chunk == null) continue;
        for (final item in jsonDecode(chunk) as List) {
          recorder._all.add(RunFix.fromJson(item as Map<String, dynamic>));
        }
      }
      recorder._saved = recorder._all.length;
      return recorder;
    } catch (e) {
      debugPrint('Unfinished run unreadable: $e');
      await _clearStored();
      return null;
    }
  }

  static Future<void> _clearStored() async {
    final prefs = await SharedPreferences.getInstance();
    for (final key in prefs.getKeys().toList()) {
      if (key == _metaKey || key.startsWith(_chunkPrefix)) {
        await prefs.remove(key);
      }
    }
  }
}

/// Finished runs waiting for the server. A run leaves the queue only when
/// the server answers 200; every retry sends the same `client_run_id`.
class RunQueue {
  RunQueue._();

  static const _key = 'run.queue';
  static const maxRuns = 10;

  /// Sends one payload. Tests replace this.
  static Future<Map<String, dynamic>> Function(Map<String, dynamic>) uploader =
      RunService.saveRun;

  /// Server answers from this session, by client_run_id.
  static final Map<String, dynamic> saved = {};

  static Future<void>? _flushing;

  static Future<List<Map<String, dynamic>>> pending() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null) return [];
    try {
      return (jsonDecode(raw) as List).cast<Map<String, dynamic>>();
    } catch (_) {
      return [];
    }
  }

  static Future<void> _store(List<Map<String, dynamic>> runs) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(runs));
  }

  static Future<bool> isPending(String clientRunId) async {
    final runs = await pending();
    return runs.any((r) => r['client_run_id'] == clientRunId);
  }

  /// Adds a run. The oldest runs go when there are more than [maxRuns].
  static Future<void> enqueue(Map<String, dynamic> payload) async {
    final runs = await pending();
    runs.removeWhere((r) => r['client_run_id'] == payload['client_run_id']);
    runs.add(payload);
    while (runs.length > maxRuns) {
      runs.removeAt(0);
    }
    await _store(runs);
  }

  /// Tries to upload every queued run. Calls overlap safely: a second call
  /// waits for the first.
  static Future<void> flush() {
    return _flushing ??= _flush().whenComplete(() => _flushing = null);
  }

  static Future<void> _flush() async {
    final tried = <String>{};
    while (true) {
      final runs = await pending();
      final next = runs.where((r) => !tried.contains(r['client_run_id']));
      if (next.isEmpty) return;

      final run = next.first;
      final id = run['client_run_id'] as String;
      tried.add(id);

      final result = await uploader(run);
      if (result['success'] == true) {
        saved[id] = result['data'];
        final left = (await pending())
          ..removeWhere((r) => r['client_run_id'] == id);
        await _store(left);
      } else if (result['network'] == true) {
        // No connection: the rest would fail too.
        return;
      }
    }
  }

  /// Turns an unfinished run from a killed app into a queued, finished one.
  /// Returns whether a run was queued.
  static Future<bool> recoverUnfinished() async {
    final recorder = await RunRecorder.load();
    if (recorder == null) return false;

    final fixes = recorder.fixes;
    if (fixes.length < 2) {
      await recorder.discard();
      return false;
    }

    final filter = TrackFilter();
    for (final fix in fixes) {
      filter.add(fix);
    }
    final endedAt = fixes.last.t;
    await enqueue(
      buildRunPayload(
        clientRunId: recorder.clientRunId,
        startedAt: recorder.startedAt,
        endedAt: endedAt,
        durationSeconds: max(0, endedAt.difference(recorder.startedAt).inSeconds),
        clientDistanceKm: filter.distanceKm,
        fixes: fixes,
      ),
    );
    await recorder.discard();
    return true;
  }
}
