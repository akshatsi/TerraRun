// -----------------------------------------------
// TerraRun – Data Models: User
// -----------------------------------------------

class UserModel {
  final String id;
  final String email;
  final String username;
  final String? avatarUrl;
  final String? city;
  final double totalDistanceM;
  final double territoryAreaM2;
  final int streakDays;
  final DateTime? lastRunDate;
  final DateTime createdAt;

  const UserModel({
    required this.id,
    required this.email,
    required this.username,
    this.avatarUrl,
    this.city,
    this.totalDistanceM = 0,
    this.territoryAreaM2 = 0,
    this.streakDays = 0,
    this.lastRunDate,
    required this.createdAt,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'] as String,
      email: json['email'] as String,
      username: json['username'] as String,
      avatarUrl: json['avatar_url'] as String?,
      city: json['city'] as String?,
      totalDistanceM: (json['total_distance_m'] as num?)?.toDouble() ?? 0,
      territoryAreaM2: (json['territory_area_m2'] as num?)?.toDouble() ?? 0,
      streakDays: (json['streak_days'] as num?)?.toInt() ?? 0,
      lastRunDate: json['last_run_date'] != null
          ? DateTime.parse(json['last_run_date'] as String)
          : null,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  /// Distance in kilometres, rounded to 2 decimals.
  double get distanceKm => totalDistanceM / 1000;

  /// Territory area in km², rounded to 4 decimals.
  double get areaKm2 => territoryAreaM2 / 1e6;
}
