import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';

class LocationTestPage extends StatefulWidget {
  const LocationTestPage({super.key});

  @override
  State<LocationTestPage> createState() => _LocationTestPageState();
}

class _LocationTestPageState extends State<LocationTestPage> {
  String statusText = 'Location not fetched yet';
  String latitudeText = '--';
  String longitudeText = '--';

  Future<void> getCurrentLocation() async {
    bool serviceEnabled;
    LocationPermission permission;

    serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      setState(() {
        statusText = 'Location services are disabled. Please enable GPS.';
      });
      return;
    }

    permission = await Geolocator.checkPermission();

    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        setState(() {
          statusText = 'Location permission denied.';
        });
        return;
      }
    }

    if (permission == LocationPermission.deniedForever) {
      setState(() {
        statusText =
            'Location permission permanently denied. Change it from phone settings.';
      });
      return;
    }

    try {
      final Position position = await Geolocator.getCurrentPosition();

      setState(() {
        statusText = 'Location fetched successfully';
        latitudeText = position.latitude.toString();
        longitudeText = position.longitude.toString();
      });
    } catch (e) {
      setState(() {
        statusText = 'Error getting location: $e';
      });
    }
  }

  Widget buildInfoCard(String title, String value, IconData icon) {
    return AppCard(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: AppColors.pink.withValues(alpha: 0.16),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(icon, color: AppColors.pink, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: AppText.caption),
                const SizedBox(height: 4),
                Text(value, style: AppText.subtitle),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Column(
          children: [
            ScreenHeader(
              title: 'Location access',
              leading: IconCircleButton(
                icon: Icons.arrow_back_rounded,
                onTap: () => Navigator.pop(context),
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    HeroCard(
                      padding: const EdgeInsets.fromLTRB(22, 22, 22, 24),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'LIVE LOCATION TEST',
                            style: AppText.overline.copyWith(
                              color: Colors.white.withValues(alpha: 0.75),
                            ),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            'Fetch your current GPS coordinates from the phone.',
                            style: AppText.headline.copyWith(fontSize: 22),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    buildInfoCard('Status', statusText, Icons.info_outline_rounded),
                    buildInfoCard('Latitude', latitudeText, Icons.my_location_rounded),
                    buildInfoCard('Longitude', longitudeText, Icons.explore_rounded),
                    const SizedBox(height: 14),
                    GradientButton(
                      label: 'Get current location',
                      icon: Icons.near_me_rounded,
                      onPressed: getCurrentLocation,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
