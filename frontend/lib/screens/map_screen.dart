// -----------------------------------------------
// TerraRun – Screen: Map
// -----------------------------------------------
// Full‑screen flutter_map with dark CartoDB tiles,
// centred on Jaipur. On map move, fetches territory
// polygons for the visible bounding box and renders
// them as coloured polygon layers.
//
// TERRITORY RENDERING LOGIC IS HEAVILY COMMENTED.
// -----------------------------------------------

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/constants.dart';
import '../models/territory.dart';
import '../providers/territory_provider.dart';
import '../providers/user_provider.dart';

class MapScreen extends ConsumerStatefulWidget {
  const MapScreen({super.key});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen> {
  final MapController _mapController = MapController();

  /// The current bounding box used to fetch territories.
  BBox? _currentBBox;

  /// Cached territories from the latest fetch.
  List<TerritoryModel> _territories = [];

  /// Currently selected territory (for bottom sheet).
  TerritoryModel? _selectedTerritory;

  @override
  void initState() {
    super.initState();
    // Fetch initial territories after the map is ready
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _onMapMoved();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // No appBar — full‑screen map
      body: Stack(
        children: [
          // ── Map ──
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: kDefaultMapCenter,
              initialZoom: kDefaultMapZoom,
              minZoom: 4,
              maxZoom: 18,
              // Fire when the user stops panning / zooming
              onPositionChanged: (position, hasGesture) {
                if (hasGesture) {
                  _onMapMoved();
                }
              },
            ),
            children: [
              // ── Tile layer (CartoDB Dark Matter) ──
              TileLayer(
                urlTemplate: kTileUrlTemplate,
                maxZoom: 19,
                userAgentPackageName: 'com.terrarun.app',
              ),

              // ── Territory polygon layer ──
              // See _buildTerritoryPolygons() for detailed comments.
              PolygonLayer(polygons: _buildTerritoryPolygons()),
            ],
          ),

          // ── Top gradient overlay for status bar ──
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: Container(
              height: MediaQuery.of(context).padding.top + 20,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.scaffoldBg.withValues(alpha: 0.8),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),

          // ── Floating legend ──
          Positioned(
            top: MediaQuery.of(context).padding.top + 12,
            right: 16,
            child: _buildLegend(context),
          ),

          // ── Bottom sheet for selected territory ──
          if (_selectedTerritory != null)
            Positioned(
              bottom: 0,
              left: 0,
              right: 0,
              child: _buildTerritorySheet(context, _selectedTerritory!),
            ),
        ],
      ),
    );
  }

  // ─────────────────────────────────────────────────
  // TERRITORY POLYGON RENDERING (HEAVILY COMMENTED)
  // ─────────────────────────────────────────────────
  //
  // This method converts the list of TerritoryModel
  // objects (fetched from GET /territory/map) into
  // flutter_map Polygon widgets.
  //
  // For each territory:
  //   1. Call territory.parsedPolygons to get the list
  //      of polygon rings (List<List<LatLng>>).
  //      See models/territory.dart for the GeoJSON
  //      parsing logic.
  //
  //   2. Determine the fill colour:
  //      - If the territory belongs to the logged‑in
  //        user → bright teal (0xFF1D9E75) at 30% opacity
  //      - Otherwise → semi‑transparent grey
  //
  //   3. Create a flutter_map Polygon for each ring.
  //      We set borderStrokeWidth and borderColor
  //      for a subtle outline effect.
  //
  //   4. We also attach an onTap handler via a
  //      GestureDetector wrapping approach — but since
  //      flutter_map Polygon can't directly handle taps,
  //      we use hitValue and the map's onTap instead.
  //      (In practice we use the label property.)
  // ─────────────────────────────────────────────────

  List<Polygon> _buildTerritoryPolygons() {
    final user = ref.read(userProvider).valueOrNull;
    final currentUserId = user?.id;

    final List<Polygon> polygons = [];

    for (final territory in _territories) {
      // 1. Parse GeoJSON into LatLng rings
      final rings = territory.parsedPolygons;
      if (rings.isEmpty) continue;

      // 2. Determine colours based on ownership
      final isOwn = territory.userId == currentUserId;
      final fillColor = isOwn
          ? AppColors.ownTerritory.withValues(alpha: 0.30)
          : AppColors.otherTerritory;
      final borderColor = isOwn
          ? AppColors.ownTerritory.withValues(alpha: 0.7)
          : Colors.grey.withValues(alpha: 0.3);

      // 3. Create a Polygon for each ring
      for (final ring in rings) {
        if (ring.length < 3) continue; // need at least a triangle

        polygons.add(
          Polygon(
            points: ring,
            color: fillColor,
            borderColor: borderColor,
            borderStrokeWidth: 1.5,
            // Label to identify which territory was tapped
            label: territory.username,
          ),
        );
      }
    }

    return polygons;
  }

  /// Called whenever the map viewport changes.
  /// Computes the new bounding box and fetches territories.
  void _onMapMoved() {
    try {
      final bounds = _mapController.camera.visibleBounds;
      final bbox = BBox(
        bounds.south,
        bounds.west,
        bounds.north,
        bounds.east,
      );

      // Skip if the bbox hasn't changed significantly
      if (_currentBBox == bbox) return;
      _currentBBox = bbox;

      // Fetch territories for the new viewport
      ref.read(territoryMapProvider(bbox).future).then((territories) {
        if (mounted) {
          setState(() {
            _territories = territories;
          });
        }
      }).catchError((_) {
        // Silently ignore fetch errors during panning
      });
    } catch (_) {
      // Map not ready yet — ignore
    }
  }

  Widget _buildLegend(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.cardBg.withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.cardBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          _legendDot(AppColors.ownTerritory, 'Your Territory'),
          const SizedBox(height: 4),
          _legendDot(Colors.grey, 'Others'),
        ],
      ),
    );
  }

  Widget _legendDot(Color color, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(label,
            style: const TextStyle(color: AppColors.textSecondary, fontSize: 11)),
      ],
    );
  }

  Widget _buildTerritorySheet(BuildContext context, TerritoryModel t) {
    return GestureDetector(
      onTap: () => setState(() => _selectedTerritory = null),
      child: Container(
        padding: EdgeInsets.fromLTRB(
            20, 16, 20, MediaQuery.of(context).padding.bottom + 16),
        decoration: const BoxDecoration(
          color: AppColors.cardBg,
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          border: Border(
            top: BorderSide(color: AppColors.primary, width: 2),
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: AppColors.primary.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.person, color: AppColors.primary),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(t.username,
                      style: Theme.of(context).textTheme.titleMedium),
                  Text(
                    '${t.areaKm2.toStringAsFixed(4)} km² captured',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
            IconButton(
              icon: const Icon(Icons.close, color: AppColors.textMuted),
              onPressed: () => setState(() => _selectedTerritory = null),
            ),
          ],
        ),
      ),
    );
  }
}
