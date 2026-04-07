// -----------------------------------------------
// TerraRun – Data Models: Leaderboard
// -----------------------------------------------

class LeaderboardEntry {
  final int rank;
  final String userId;
  final String username;
  final String? avatarUrl;
  final double territoryAreaM2;
  final double totalDistanceM;

  const LeaderboardEntry({
    required this.rank,
    required this.userId,
    required this.username,
    this.avatarUrl,
    this.territoryAreaM2 = 0,
    this.totalDistanceM = 0,
  });

  factory LeaderboardEntry.fromJson(Map<String, dynamic> json) {
    return LeaderboardEntry(
      rank: (json['rank'] as num).toInt(),
      userId: json['user_id'] as String,
      username: json['username'] as String,
      avatarUrl: json['avatar_url'] as String?,
      territoryAreaM2:
          (json['territory_area_m2'] as num?)?.toDouble() ?? 0,
      totalDistanceM:
          (json['total_distance_m'] as num?)?.toDouble() ?? 0,
    );
  }

  double get areaKm2 => territoryAreaM2 / 1e6;
  double get distanceKm => totalDistanceM / 1000;
}
