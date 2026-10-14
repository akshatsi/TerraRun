import 'dart:async';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../data/run_data.dart';
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
  String statusText = 'Ready to run';

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

    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      if (!mounted) return;
      setState(() {
        statusText = 'Enable location services';
      });
      return;
    }

    LocationPermission permission = await Geolocator.checkPermission();

    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        if (!mounted) return;
        setState(() {
          statusText = 'Location permission denied';
        });
        return;
      }
    }

    if (permission == LocationPermission.deniedForever) {
      if (!mounted) return;
      setState(() {
        statusText = 'Allow location from settings';
      });
      return;
    }

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
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.best,
        distanceFilter: 3,
      ),
    ).listen((Position position) {
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
        RunDataStore.currentLatitude = position.latitude;
        RunDataStore.currentLongitude = position.longitude;

        distanceKm += addedKm;
        _recalculateAvgSpeed();
      });

      mapController.move(
        LatLng(position.latitude, position.longitude),
        17,
      );
    });
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

    final hasTerritoryData = result['success'] == true &&
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

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
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
      statusText = 'Ready to run';
      lastPosition = null;
      runPath.clear();
      RunDataStore.latestRunPath = [];
    });
  }

  String formatTime(int totalSeconds) => Fmt.duration(totalSeconds);

  Widget buildTopBanner() {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 10, 16, 0),
      padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: isRunning
              ? AppColors.pink.withValues(alpha: 0.6)
              : AppColors.border,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: isRunning
                  ? AppColors.pink.withValues(alpha: 0.18)
                  : Colors.white.withValues(alpha: 0.08),
              shape: BoxShape.circle,
            ),
            child: Icon(
              isRunning ? Icons.gps_fixed : Icons.location_searching,
              color: isRunning ? AppColors.pink : AppColors.textSecondary,
              size: 18,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              isRunning ? 'GPS acquired' : statusText,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppText.subtitle.copyWith(
                color: isRunning ? AppColors.pink : Colors.white,
              ),
            ),
          ),
          IconCircleButton(
            icon: Icons.my_location_rounded,
            size: 36,
            onTap: () {
              mapController.move(currentLatLng, 17);
            },
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
    timer?.cancel();
    positionStream?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hasLocation = RunDataStore.currentLatitude != null &&
        RunDataStore.currentLongitude != null;

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Stack(
        children: [
          FlutterMap(
            mapController: mapController,
            options: MapOptions(
              initialCenter: currentLatLng,
              initialZoom: hasLocation ? 17 : 15,
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
              children: [
                buildTopBanner(),
                const Spacer(),
                buildBottomPanel(),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
