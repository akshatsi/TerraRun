import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';

/// Turns light OpenStreetMap tiles into a muted, near-monochrome dark map:
/// luminance, inverted, so territory colours stand out.
const _mutedDarkMatrix = <double>[
  -0.191, -0.644, -0.065, 0, 242, //R
  -0.191, -0.644, -0.065, 0, 242, //G
  -0.191, -0.644, -0.065, 0, 250, //B
  0, 0, 0, 1, 0, //A
];

Widget _mutedDarkTile(BuildContext context, Widget tileWidget, TileImage tile) {
  return ColorFiltered(
    colorFilter: const ColorFilter.matrix(_mutedDarkMatrix),
    child: tileWidget,
  );
}

/// Base map shared by the Map and Run screens.
///
/// OpenStreetMap tiles need no API key. OSM's tile servers are meant for
/// light use, so a production build should point `urlTemplate` at a keyed
/// provider (Carto, Stadia, MapTiler) instead.
TileLayer buildBaseTileLayer() {
  return TileLayer(
    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    userAgentPackageName: 'com.terrarun.app',
    tileBuilder: _mutedDarkTile,
  );
}
