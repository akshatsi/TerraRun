import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../data/run_data.dart';
import '../services/auth_service.dart';
import '../services/location_service.dart';
import '../services/stats_service.dart';
import '../services/territory_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';
import '../widgets/map_tiles.dart';
import 'friends_page.dart';

class MapPage extends StatefulWidget {
  const MapPage({super.key});

  @override
  State<MapPage> createState() => _MapPageState();
}

class _MapPageState extends State<MapPage> {
  final MapController mapController = MapController();
  Timer? followTimer;

  bool _isLoadingStats = true;
  String? _statsError;

  double _totalDistance = 0.0;
  int _totalRuns = 0;

  bool _mapReady = false;
  bool _centred = RunDataStore.currentLatitude != null;

  // The map follows the user until they drag it; the target button resumes.
  bool _following = true;

  // Index into TerritoryService.scopes: all players, friends, mine.
  int _scopeIndex = 0;
  int? _myUserId;

  // --- Territory data ---
  List<Map<String, dynamic>> _territories = [];
  double _myTerritoryArea = 0.0;

  bool get hasLiveLocation =>
      RunDataStore.currentLatitude != null &&
      RunDataStore.currentLongitude != null;

  LatLng get currentLatLng => LatLng(
    RunDataStore.currentLatitude ?? 28.6139,
    RunDataStore.currentLongitude ?? 77.2090,
  );

  List<LatLng> get latestPathPoints {
    return RunDataStore.latestRunPath
        .map((p) => LatLng(p.latitude, p.longitude))
        .toList();
  }

  /// Keeps the map on the user's latest position while following.
  void _followLatest() {
    final position = LocationService.latest.value;
    if (position == null || !_mapReady || !_following) return;

    // Zoom in on the first fix, then keep whatever zoom the user chose.
    final zoom = _centred ? mapController.camera.zoom : 16.0;
    _centred = true;
    mapController.move(LatLng(position.latitude, position.longitude), zoom);
  }

  @override
  void initState() {
    super.initState();
    LocationService.latest.addListener(_followLatest);
    _loadRuns();
    _loadTerritories();
    AuthService.getUserId().then((id) {
      if (mounted) setState(() => _myUserId = id);
    });

    followTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;

      setState(() {});
    });
  }

  Future<void> _loadRuns() async {
    setState(() {
      _isLoadingStats = true;
      _statsError = null;
    });

    final result = await StatsService.getAllRuns();

    if (!mounted) return;

    if (result['success'] == true) {
      final runs = result['data'] as List<dynamic>;

      double totalDistance = 0.0;

      for (final run in runs) {
        totalDistance += ((run['distance_km'] ?? 0) as num).toDouble();
      }

      setState(() {
        _totalRuns = runs.length;
        _totalDistance = totalDistance;
        _isLoadingStats = false;
      });
    } else {
      setState(() {
        _statsError = result['message']?.toString() ?? 'Failed to load stats';
        _isLoadingStats = false;
      });
    }
  }

  Future<void> _loadTerritories() async {
    final scope = TerritoryService.scopes[_scopeIndex];
    final result = await TerritoryService.getAllTerritories(scope: scope);

    if (!mounted || scope != TerritoryService.scopes[_scopeIndex]) return;

    if (result['success'] == true) {
      final data = result['data'] as Map<String, dynamic>;
      final list = data['territories'] as List<dynamic>? ?? [];

      setState(() {
        _territories = list.cast<Map<String, dynamic>>();
      });
    } else {
      setState(() => _territories = []);
    }

    // Also fetch my territory area
    final myResult = await TerritoryService.getMyTerritory();
    if (!mounted) return;

    if (myResult['success'] == true) {
      final data = myResult['data'] as Map<String, dynamic>;
      setState(() {
        _myTerritoryArea = ((data['area_sq_m'] ?? 0) as num).toDouble();
      });
    }
  }

  /// Parse a GeoJSON geometry into a list of polygon point-lists.
  List<List<LatLng>> _parseGeoJsonPolygons(Map<String, dynamic>? geojson) {
    if (geojson == null) return [];

    final type = geojson['type'] as String? ?? '';
    final List<List<LatLng>> polygons = [];

    if (type == 'Polygon') {
      final coords = geojson['coordinates'] as List<dynamic>;
      if (coords.isNotEmpty) {
        final ring = coords[0] as List<dynamic>;
        polygons.add(
          ring
              .map(
                (c) =>
                    LatLng((c[1] as num).toDouble(), (c[0] as num).toDouble()),
              )
              .toList(),
        );
      }
    } else if (type == 'MultiPolygon') {
      final polys = geojson['coordinates'] as List<dynamic>;
      for (final poly in polys) {
        final ring = (poly as List<dynamic>)[0] as List<dynamic>;
        polygons.add(
          ring
              .map(
                (c) =>
                    LatLng((c[1] as num).toDouble(), (c[0] as num).toDouble()),
              )
              .toList(),
        );
      }
    }

    return polygons;
  }

  /// A colour for a user: near-white for you, a muted palette hue for rivals.
  Color _colorForUser(int userId, bool isMe) {
    if (isMe) return AppColors.mine;
    const palette = AppColors.rivalPalette;
    return palette[userId % palette.length];
  }

  @override
  void dispose() {
    LocationService.latest.removeListener(_followLatest);
    followTimer?.cancel();
    super.dispose();
  }

  Future<void> _openSearch() async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const FriendsPage(focusSearch: true)),
    );
    if (!mounted) return;
    _loadTerritories();
  }

  Future<void> _openFriends() async {
    await Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => const FriendsPage()));
    if (!mounted) return;
    _loadTerritories();
  }

  @override
  Widget build(BuildContext context) {
    // Build territory polygon layers
    final List<Polygon> territoryPolygons = [];

    for (final t in _territories) {
      final geojson = t['geojson'] as Map<String, dynamic>?;
      final userId = (t['user_id'] as num?)?.toInt() ?? 0;
      final isMe = _scopeIndex == 2 || userId == _myUserId;

      final color = _colorForUser(userId, isMe);
      final polyPoints = _parseGeoJsonPolygons(geojson);

      for (final points in polyPoints) {
        if (points.length >= 3) {
          territoryPolygons.add(
            Polygon(
              points: points,
              color: color.withValues(
                alpha: isMe ? AppColors.mineFillOpacity : 0.25,
              ),
              borderColor: color,
              borderStrokeWidth: 2,
            ),
          );
        }
      }
    }

    final statusText = _statsError != null
        ? _statsError!
        : RunDataStore.isRunActive
        ? 'Live run tracking active'
        : _totalRuns == 0
        ? 'No runs saved yet'
        : _myTerritoryArea > 0
        ? 'Your territory'
        : 'Runs completed';

    final subText = _totalRuns == 0
        ? 'Start your first run to claim territory'
        : _myTerritoryArea > 0
        ? '${_territories.length} ${_territories.length == 1 ? 'player' : 'players'} on the map'
        : 'Total distance covered: ${_totalDistance.toStringAsFixed(2)} km';

    final area = Fmt.area(_myTerritoryArea);

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Stack(
        children: [
          FlutterMap(
            mapController: mapController,
            options: MapOptions(
              backgroundColor: AppColors.bg,
              initialCenter: currentLatLng,
              initialZoom: hasLiveLocation ? 16 : 14,
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
              // --- Territory polygons ---
              if (territoryPolygons.isNotEmpty)
                PolygonLayer(polygons: territoryPolygons),
              if (latestPathPoints.length >= 2)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: latestPathPoints,
                      strokeWidth: 4,
                      color: AppColors.mine,
                    ),
                  ],
                ),
              MarkerLayer(
                markers: [
                  if (hasLiveLocation)
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
              children: [
                // Search sits alone in the top-left corner, above the filter,
                // so the three filter labels keep the full width at 360 px.
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                    child: IconCircleButton(
                      icon: Icons.search_rounded,
                      onTap: _openSearch,
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                  child: SegmentedPill(
                    background: AppColors.surface,
                    labels: const ['All players', 'Friends', 'My territory'],
                    index: _scopeIndex,
                    onChanged: (i) {
                      if (i == _scopeIndex) return;
                      setState(() {
                        _scopeIndex = i;
                        _territories = [];
                      });
                      _loadTerritories();
                    },
                  ),
                ),
                if (!hasLiveLocation && LocationService.hint != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 10,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(AppRadius.card),
                        border: Border.all(
                          color: AppColors.warning.withValues(alpha: 0.5),
                        ),
                      ),
                      child: Row(
                        children: [
                          const Icon(
                            Icons.location_off_rounded,
                            color: AppColors.warning,
                            size: 18,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              LocationService.hint!,
                              style: AppText.label.copyWith(
                                color: AppColors.text,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
                    child: Align(
                      alignment: Alignment.bottomRight,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconCircleButton(
                            icon: Icons.group_rounded,
                            onTap: _openFriends,
                          ),
                          const SizedBox(height: 10),
                          IconCircleButton(
                            icon: Icons.my_location_rounded,
                            active: _following && hasLiveLocation,
                            onTap: () {
                              setState(() => _following = true);

                              if (hasLiveLocation) {
                                mapController.move(currentLatLng, 17);
                              } else {
                                LocationService.requestFix();
                              }
                            },
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                ShadCard(
                  width: double.infinity,
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
                  backgroundColor: AppColors.surface,
                  radius: const BorderRadius.vertical(
                    top: Radius.circular(AppRadius.card),
                  ),
                  child: SafeArea(
                    top: false,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(statusText, style: AppText.headline),
                        const SizedBox(height: 3),
                        Text(subText, style: AppText.bodySecondary),
                        const SizedBox(height: 16),
                        const AppDivider(),
                        const SizedBox(height: 16),
                        if (_isLoadingStats)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 8),
                            child: AppLoader(),
                          )
                        else
                          StatRow(
                            children: [
                              StatBlock(
                                value: _totalDistance.toStringAsFixed(2),
                                unit: 'km',
                                label: 'Distance',
                              ),
                              StatBlock(
                                value: _totalRuns.toString(),
                                label: 'Runs',
                              ),
                              _myTerritoryArea > 0
                                  ? StatBlock(
                                      value: area.value,
                                      unit: area.unit,
                                      label: 'Terra area',
                                      valueColor: AppColors.signature,
                                    )
                                  : const StatBlock(
                                      value: '—',
                                      label: 'Terra area',
                                    ),
                            ],
                          ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
