import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:geolocator/geolocator.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../data/run_data.dart';
import '../gps/run_fix.dart';
import '../gps/track_filter.dart';
import '../services/location_service.dart';
import '../services/run_service.dart';
import '../services/run_store.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';
import '../widgets/map_tiles.dart';

class RunPage extends StatefulWidget {
  const RunPage({super.key});

  @override
  State<RunPage> createState() => _RunPageState();
}

class _RunPageState extends State<RunPage> {
  final MapController mapController = MapController();

  bool isRunning = false;
  bool isSavingRun = false;
  int secondsElapsed = 0;
  double distanceKm = 0.0;
  double avgSpeed = 0.0;
  static const _readyText = 'Ready to run';
  String statusText = _readyText;

  bool _mapReady = false;
  bool _centred = RunDataStore.currentLatitude != null;

  // The map follows the user until they drag it; the target button resumes.
  bool _following = true;

  Timer? timer;
  StreamSubscription<Position>? positionStream;

  // Every fix of the run goes to the recorder; the filter only decides what
  // counts toward the live distance and route.
  TrackFilter _filter = TrackFilter();
  RunRecorder? _recorder;

  // Accepted points, flat; used for loop detection.
  final List<RunPoint> runPath = [];

  LatLng get currentLatLng => LatLng(
    RunDataStore.currentLatitude ?? 28.6139,
    RunDataStore.currentLongitude ?? 77.2090,
  );

  /// One line per segment, so none is drawn across a GPS gap.
  List<List<LatLng>> get _routeLines => [
    for (final segment in _filter.segments)
      if (segment.length >= 2) [for (final f in segment) LatLng(f.lat, f.lng)],
  ];

  @override
  void initState() {
    super.initState();
    LocationService.latest.addListener(_onLocationChanged);
    LocationService.status.addListener(_onLocationChanged);
    LocationService.error.addListener(_onLocationChanged);
  }

  void _onLocationChanged() {
    if (!mounted) return;
    _followLatest();
    setState(() {});
  }

  /// Keeps the map on the user's latest position while following.
  void _followLatest() {
    final position = LocationService.latest.value;
    if (position == null || !_mapReady || !_following) return;

    // Zoom in on the first fix, then keep whatever zoom the user chose.
    final zoom = _centred ? mapController.camera.zoom : 17.0;
    _centred = true;
    mapController.move(LatLng(position.latitude, position.longitude), zoom);
  }

  bool get _hasFix => RunDataStore.currentLatitude != null;

  /// A position is known and nothing is wrong with location.
  bool get _gpsOk => _hasFix && LocationService.hint == null;

  String get _bannerText {
    if (isRunning) {
      return _gpsOk
          ? (_loopHint ?? 'GPS acquired')
          : (LocationService.hint ?? 'Waiting for GPS…');
    }
    if (statusText != _readyText) return statusText;
    return LocationService.hint ?? _readyText;
  }

  /// Shown once the path is long enough for a loop and the runner is near
  /// the start.
  String? get _loopHint {
    if (!isRunning || !_filter.loopLongEnough) return null;
    final d = _filter.startDistanceM;
    if (d == null) return null;
    if (_filter.isLoopClosed) {
      return 'Loop closed — stop now to claim the enclosed area';
    }
    if (d <= _filter.config.loopHintRadiusM) {
      return 'Start point ${d.round()} m away — close the loop to claim the area';
    }
    return null;
  }

  String? get _bannerDetail {
    if (isRunning && _gpsOk) return null;
    if (!isRunning && statusText != _readyText) return null;
    return LocationService.hintDetail;
  }

  void _onRunLocationError(Object error) {
    LocationService.report(error);
  }

  void _findMe() {
    setState(() => _following = true);

    if (_hasFix) {
      mapController.move(currentLatLng, 17);
    } else {
      LocationService.requestFix();
    }
  }

  void _recalculateAvgSpeed() {
    if (secondsElapsed < 15 || distanceKm < 0.03) {
      avgSpeed = 0.0;
      return;
    }

    final hours = secondsElapsed / 3600;
    avgSpeed = hours > 0 ? distanceKm / hours : 0.0;
  }

  Future<void> startRun() async {
    if (isRunning) return;

    final access = await LocationService.ensurePermission();

    if (access != LocationStatus.ready) {
      if (!mounted) return;
      setState(() {
        statusText = switch (access) {
          LocationStatus.serviceOff => 'Enable location services',
          LocationStatus.deniedForever => 'Allow location from settings',
          _ => 'Location permission denied',
        };
      });
      return;
    }

    // Permission may have just been granted; make sure the map follows too.
    LocationService.startPassive();

    timer?.cancel();
    await positionStream?.cancel();

    final recorder = await RunRecorder.start();

    if (!mounted) return;
    setState(() {
      isRunning = true;
      statusText = 'GPS tracking live';
      runPath.clear();
      RunDataStore.latestRunPath = [];
      RunDataStore.isRunActive = true;
      _filter = TrackFilter();
      _recorder = recorder;
      secondsElapsed = 0;
      distanceKm = 0.0;
      avgSpeed = 0.0;
    });

    timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;

      setState(() {
        secondsElapsed++;
        _recalculateAvgSpeed();
      });
    });

    positionStream = Geolocator.getPositionStream(
      locationSettings: LocationService.runSettings(),
    ).listen(_onRunPosition, onError: _onRunLocationError);

    // Start from the position the app already has. A device that is not
    // moving may not report again, and the run should not wait on it.
    final start = LocationService.latest.value;
    if (start != null) _onRunPosition(start, publish: false);
  }

  void _onRunPosition(Position position, {bool publish = true}) {
    if (!mounted) return;

    final fix = RunFix.fromPosition(position);
    _recorder?.add(fix);
    final decision = _filter.add(fix);

    setState(() {
      if (decision.accepted) {
        runPath.add(RunPoint(latitude: fix.lat, longitude: fix.lng));
        RunDataStore.latestRunPath = List.from(runPath);
      }

      distanceKm = _filter.distanceKm;
      _recalculateAvgSpeed();
    });

    // Publishing also moves the map when it is following.
    if (publish) LocationService.publish(position);
  }

  Future<void> stopRun() async {
    if (isSavingRun) return;

    timer?.cancel();
    await positionStream?.cancel();

    if (!mounted) return;
    setState(() {
      isRunning = false;
      RunDataStore.isRunActive = false;
      isSavingRun = true;
      statusText = 'Saving run...';
    });

    final recorder = _recorder;
    String? summary;
    var hasTerritoryData = false;
    var uploaded = false;
    var queued = false;

    if (recorder != null) {
      final endedAt = DateTime.now().toUtc();
      await recorder.flush();
      await RunQueue.enqueue(
        buildRunPayload(
          clientRunId: recorder.clientRunId,
          startedAt: recorder.startedAt,
          endedAt: endedAt,
          durationSeconds: secondsElapsed,
          clientDistanceKm: _filter.distanceKm,
          fixes: recorder.fixes,
        ),
      );
      await recorder.discard();
      _recorder = null;
      queued = true;

      // Sends this run and any earlier one still waiting.
      await RunQueue.flush();
      final data = RunQueue.saved.remove(recorder.clientRunId);
      uploaded =
          data != null || !await RunQueue.isPending(recorder.clientRunId);
      summary = RunService.saveSummary(data);

      final server = data is Map ? data : null;
      final serverKm = (server?['distance_km'] as num?)?.toDouble();
      final serverSpeed = (server?['avg_speed'] as num?)?.toDouble();
      if (serverKm != null && mounted) {
        setState(() {
          distanceKm = serverKm;
          if (serverSpeed != null) avgSpeed = serverSpeed;
        });
      }
      if (server != null) {
        hasTerritoryData = server['territory_geojson'] != null;
      }
    }

    if (!mounted) return;

    setState(() {
      isSavingRun = false;
      statusText = uploaded
          ? (hasTerritoryData ? 'Territory claimed! Run saved' : 'Run saved')
          : queued
          ? 'Run kept on this phone, will upload later'
          : 'Run stopped, but save failed';
    });

    final message = uploaded
        ? (summary ??
              (hasTerritoryData
                  ? 'Run saved — territory captured!'
                  : 'Run saved successfully'))
        : queued
        ? 'No connection. Your run is saved on this phone and will upload later.'
        : 'Failed to save run';

    showAppToast(context, message);
  }

  Future<void> resetRun() async {
    timer?.cancel();
    await positionStream?.cancel();

    if (!mounted) return;
    setState(() {
      isRunning = false;
      RunDataStore.isRunActive = false;
      secondsElapsed = 0;
      distanceKm = 0.0;
      avgSpeed = 0.0;
      statusText = _readyText;
      _filter = TrackFilter();
      runPath.clear();
      RunDataStore.latestRunPath = [];
    });
  }

  String formatTime(int totalSeconds) => Fmt.duration(totalSeconds);

  Widget buildTopBanner() {
    final tracking = isRunning && _gpsOk;
    final problem = !tracking && LocationService.hint != null;
    final detail = _bannerDetail;

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 10, 16, 0),
      padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.card),
        border: Border.all(
          color: problem
              ? AppColors.warning.withValues(alpha: 0.6)
              : AppColors.line,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: AppColors.surfaceHigh,
              borderRadius: BorderRadius.circular(AppRadius.control),
            ),
            child: Icon(
              tracking
                  ? Icons.gps_fixed
                  : problem
                  ? Icons.location_off_rounded
                  : Icons.location_searching,
              color: tracking
                  ? AppColors.positive
                  : problem
                  ? AppColors.warning
                  : AppColors.textSecondary,
              size: 18,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _bannerText,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: AppText.body.copyWith(fontWeight: FontWeight.w500),
                ),
                if (detail != null) ...[
                  const SizedBox(height: 2),
                  Text(detail, style: AppText.caption),
                ],
              ],
            ),
          ),
          IconCircleButton(
            icon: Icons.my_location_rounded,
            size: 36,
            active: _following && _hasFix,
            onTap: _findMe,
          ),
        ],
      ),
    );
  }

  Widget buildBottomPanel() {
    return ShadCard(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
      backgroundColor: AppColors.surface,
      radius: const BorderRadius.vertical(top: Radius.circular(AppRadius.card)),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: StatBlock(
                    value: formatTime(secondsElapsed),
                    label: 'Duration',
                    valueSize: 20,
                  ),
                ),
                Expanded(
                  flex: 2,
                  child: StatBlock(
                    value: distanceKm.toStringAsFixed(2),
                    unit: 'km',
                    label: 'Distance',
                    valueSize: 44,
                    hero: true,
                    align: CrossAxisAlignment.center,
                  ),
                ),
                Expanded(
                  child: StatBlock(
                    value: avgSpeed.toStringAsFixed(1),
                    unit: 'km/h',
                    label: 'Avg speed',
                    valueSize: 20,
                    align: CrossAxisAlignment.end,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 22),
            if (isRunning)
              DestructiveButton(
                label: 'Stop run',
                icon: Icons.stop_rounded,
                loading: isSavingRun,
                onPressed: isSavingRun ? null : stopRun,
              )
            else
              SignatureButton(
                label: 'Start run',
                icon: Icons.play_arrow_rounded,
                loading: isSavingRun,
                onPressed: isSavingRun ? null : startRun,
              ),
            if (!isRunning && !isSavingRun) ...[
              const SizedBox(height: 6),
              ShadButton.ghost(
                onPressed: resetRun,
                foregroundColor: AppColors.textSecondary,
                textStyle: AppText.label,
                child: const Text('Reset'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    LocationService.latest.removeListener(_onLocationChanged);
    LocationService.status.removeListener(_onLocationChanged);
    LocationService.error.removeListener(_onLocationChanged);
    timer?.cancel();
    positionStream?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hasLocation =
        RunDataStore.currentLatitude != null &&
        RunDataStore.currentLongitude != null;

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Stack(
        children: [
          FlutterMap(
            mapController: mapController,
            options: MapOptions(
              backgroundColor: AppColors.bg,
              initialCenter: currentLatLng,
              initialZoom: hasLocation ? 17 : 15,
              onMapReady: () {
                _mapReady = true;
                _followLatest();
              },
              onPositionChanged: (camera, hasGesture) {
                if (hasGesture && _following) {
                  setState(() => _following = false);
                }
              },
            ),
            children: [
              buildBaseTileLayer(),
              PolylineLayer(
                polylines: [
                  for (final line in _routeLines)
                    Polyline(
                      points: line,
                      strokeWidth: 4,
                      color: AppColors.mine,
                    ),
                ],
              ),
              MarkerLayer(
                markers: [
                  if (_hasFix)
                    Marker(
                      point: currentLatLng,
                      width: 28,
                      height: 28,
                      child: Container(
                        decoration: BoxDecoration(
                          color: AppColors.text,
                          shape: BoxShape.circle,
                          border: Border.all(color: AppColors.bg, width: 4),
                        ),
                      ),
                    ),
                ],
              ),
            ],
          ),
          SafeArea(
            child: Column(
              children: [buildTopBanner(), const Spacer(), buildBottomPanel()],
            ),
          ),
        ],
      ),
    );
  }
}
