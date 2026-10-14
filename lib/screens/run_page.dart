import 'dart:async';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../data/run_data.dart';
import '../services/location_service.dart';
import '../services/run_service.dart';
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
  Position? lastPosition;

  final List<RunPoint> runPath = [];

  LatLng get currentLatLng => LatLng(
    RunDataStore.currentLatitude ?? 28.6139,
    RunDataStore.currentLongitude ?? 77.2090,
  );

  List<LatLng> get latestPathPoints {
    return runPath.map((p) => LatLng(p.latitude, p.longitude)).toList();
  }

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
          ? 'GPS acquired'
          : (LocationService.hint ?? 'Waiting for GPS…');
    }
    if (statusText != _readyText) return statusText;
    return LocationService.hint ?? _readyText;
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

  bool _isLoopClosed(List<RunPoint> path) {
    if (path.length < 4) return false;

    final start = path.first;
    final end = path.last;

    const threshold = 0.0003;

    final latDiff = (start.latitude - end.latitude).abs();
    final lngDiff = (start.longitude - end.longitude).abs();

    return latDiff < threshold && lngDiff < threshold;
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

    if (!mounted) return;
    setState(() {
      isRunning = true;
      statusText = 'GPS tracking live';
      runPath.clear();
      RunDataStore.latestRunPath = [];
      RunDataStore.isRunActive = true;
      lastPosition = null;
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

    final point = RunPoint(
      latitude: position.latitude,
      longitude: position.longitude,
    );

    double addedKm = 0.0;

    if (lastPosition != null) {
      final meters = Geolocator.distanceBetween(
        lastPosition!.latitude,
        lastPosition!.longitude,
        position.latitude,
        position.longitude,
      );

      // Ignore clearly bad GPS jumps and tiny noise
      if (meters >= 2 && meters <= 50) {
        addedKm = meters / 1000;
      }
    }

    lastPosition = position;

    setState(() {
      runPath.add(point);
      RunDataStore.latestRunPath = List.from(runPath);

      distanceKm += addedKm;
      _recalculateAvgSpeed();
    });

    // Publishing also moves the map when it is following.
    if (publish) LocationService.publish(position);
  }

  Future<void> stopRun() async {
    if (isSavingRun) return;

    timer?.cancel();
    await positionStream?.cancel();

    final closedLoop = _isLoopClosed(runPath);

    if (closedLoop) {
      RunDataStore.capturedAreas.insert(
        0,
        CapturedArea(
          name:
              'My Loop ${RunDataStore.capturedAreas.where((a) => a.isMine).length + 1}',
          points: List.from(runPath),
          progress: 100,
          isMine: true,
        ),
      );
    }

    if (!mounted) return;
    setState(() {
      isRunning = false;
      RunDataStore.isRunActive = false;
      isSavingRun = true;
      statusText = 'Saving run...';
    });

    // Convert tracked GPS points to [[lat, lng], …] for territory capture
    final List<List<double>> routeCoords = runPath
        .map((p) => [p.latitude, p.longitude])
        .toList();

    final result = await RunService.saveRun(
      distanceKm: distanceKm,
      durationSeconds: secondsElapsed,
      avgSpeed: avgSpeed,
      routeCoordinates: routeCoords.length >= 2 ? routeCoords : null,
    );

    if (!mounted) return;

    final hasTerritoryData =
        result['success'] == true &&
        result['data'] is Map &&
        result['data']['territory_geojson'] != null;

    setState(() {
      isSavingRun = false;
      statusText = result['success'] == true
          ? (hasTerritoryData
                ? 'Territory claimed! Run saved'
                : closedLoop
                ? 'Loop captured and run saved'
                : 'Run saved')
          : 'Run stopped, but save failed';
    });

    final message = result['success'] == true
        ? (hasTerritoryData
              ? 'Run saved — territory captured!'
              : 'Run saved successfully')
        : (result['message']?.toString() ?? 'Failed to save run');

    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
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
      lastPosition = null;
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
        color: AppColors.surface.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(detail == null ? 999 : 26),
        border: Border.all(
          color: tracking
              ? AppColors.pink.withValues(alpha: 0.6)
              : problem
              ? AppColors.gold.withValues(alpha: 0.5)
              : AppColors.border,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: tracking
                  ? AppColors.pink.withValues(alpha: 0.18)
                  : Colors.white.withValues(alpha: 0.08),
              shape: BoxShape.circle,
            ),
            child: Icon(
              tracking
                  ? Icons.gps_fixed
                  : problem
                  ? Icons.location_off_rounded
                  : Icons.location_searching,
              color: tracking
                  ? AppColors.pink
                  : problem
                  ? AppColors.gold
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
                  style: AppText.subtitle.copyWith(
                    color: tracking ? AppColors.pink : Colors.white,
                  ),
                ),
                if (detail != null) ...[
                  const SizedBox(height: 2),
                  Text(detail, style: AppText.caption.copyWith(height: 1.3)),
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
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
        border: Border.all(color: AppColors.border),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(20),
              ),
            ),
            const SizedBox(height: 20),
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
                    unit: 'KM',
                    label: 'Distance',
                    valueSize: 44,
                    accent: true,
                    align: CrossAxisAlignment.center,
                  ),
                ),
                Expanded(
                  child: StatBlock(
                    value: avgSpeed.toStringAsFixed(1),
                    unit: 'KM/H',
                    label: 'Avg speed',
                    valueSize: 20,
                    align: CrossAxisAlignment.end,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 22),
            GradientButton(
              label: isRunning ? 'Stop run' : 'Start run',
              icon: isRunning ? Icons.stop_rounded : Icons.play_arrow_rounded,
              gradient: isRunning
                  ? AppColors.dangerGradient
                  : AppColors.brandGradient,
              loading: isSavingRun,
              onPressed: isSavingRun ? null : (isRunning ? stopRun : startRun),
            ),
            if (!isRunning && !isSavingRun) ...[
              const SizedBox(height: 6),
              TextButton(
                onPressed: resetRun,
                child: Text(
                  'Reset',
                  style: AppText.caption.copyWith(fontWeight: FontWeight.w700),
                ),
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
              if (latestPathPoints.length >= 2)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: latestPathPoints,
                      strokeWidth: 5,
                      color: AppColors.pink,
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
                          color: AppColors.pink,
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 3),
                          boxShadow: [
                            BoxShadow(
                              color: AppColors.pink.withValues(alpha: 0.55),
                              blurRadius: 14,
                            ),
                          ],
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
