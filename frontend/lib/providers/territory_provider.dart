// -----------------------------------------------
// TerraRun – Providers: Territory
// -----------------------------------------------

import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/territory.dart';
import 'auth_provider.dart';

// Bounding box parameter for the territory map query.
class BBox {
  final double minLat, minLng, maxLat, maxLng;
  const BBox(this.minLat, this.minLng, this.maxLat, this.maxLng);

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is BBox &&
          minLat == other.minLat &&
          minLng == other.minLng &&
          maxLat == other.maxLat &&
          maxLng == other.maxLng;

  @override
  int get hashCode => Object.hash(minLat, minLng, maxLat, maxLng);
}

// Family provider: fetches territories for a given bounding box.
final territoryMapProvider =
    FutureProvider.family<List<TerritoryModel>, BBox>((ref, bbox) async {
  final api = ref.watch(apiServiceProvider);
  return api.getTerritoryMap(
    minLat: bbox.minLat,
    minLng: bbox.minLng,
    maxLat: bbox.maxLat,
    maxLng: bbox.maxLng,
  );
});

// Current user's own territory.
final myTerritoryProvider = FutureProvider<TerritoryModel>((ref) async {
  final api = ref.watch(apiServiceProvider);
  return api.getMyTerritory();
});
