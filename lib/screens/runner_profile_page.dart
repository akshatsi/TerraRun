import 'package:flutter/material.dart';
import '../services/social_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/app_widgets.dart';
import 'run_detail_page.dart';

/// Another runner's stats and latest runs, with a follow button.
class RunnerProfilePage extends StatefulWidget {
  final int userId;
  final String name;

  const RunnerProfilePage({super.key, required this.userId, this.name = ''});

  @override
  State<RunnerProfilePage> createState() => _RunnerProfilePageState();
}

class _RunnerProfilePageState extends State<RunnerProfilePage> {
  bool _isLoading = true;
  String? _error;
  Map<String, dynamic>? _user;
  List<Map<String, dynamic>> _runs = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    final result = await SocialService.getUser(widget.userId);
    if (!mounted) return;

    if (result['success'] == true && result['data'] is Map) {
      final data = Map<String, dynamic>.from(result['data'] as Map);
      final runs = data['recent_runs'];
      setState(() {
        _user = data;
        _runs = runs is List
            ? runs
                  .whereType<Map>()
                  .map((e) => Map<String, dynamic>.from(e))
                  .toList()
            : [];
        _isLoading = false;
      });
    } else {
      setState(() {
        _error = result['message']?.toString() ?? 'Failed to load runner';
        _isLoading = false;
      });
    }
  }

  Future<void> _toggleFollow() async {
    final user = _user;
    if (user == null) return;

    final wasFollowing = user['is_following'] == true;
    final followers = (user['followers_count'] ?? 0) as num;
    setState(() {
      user['is_following'] = !wasFollowing;
      user['followers_count'] = followers + (wasFollowing ? -1 : 1);
    });

    final result = wasFollowing
        ? await SocialService.unfollow(widget.userId)
        : await SocialService.follow(widget.userId);

    if (!mounted) return;

    if (result['success'] == true && result['data'] is Map) {
      // Take the server's counts.
      setState(() => user.addAll(Map<String, dynamic>.from(result['data'])));
    } else {
      setState(() {
        user['is_following'] = wasFollowing;
        user['followers_count'] = followers;
      });
      showAppToast(context, result['message']?.toString() ?? 'Failed');
    }
  }

  Widget _stats(Map<String, dynamic> user) {
    final km = ((user['total_distance_km'] ?? 0) as num).toDouble();
    final area = ((user['territory_area_sq_m'] ?? 0) as num).toDouble();
    final parts = Fmt.area(area);

    return AppCard(
      child: Column(
        children: [
          StatRow(
            children: [
              StatBlock(
                value: km.toStringAsFixed(2),
                unit: 'km',
                label: 'Distance',
              ),
              StatBlock(value: '${user['total_runs'] ?? 0}', label: 'Runs'),
              StatBlock(
                value: area > 0 ? parts.value : '—',
                unit: area > 0 ? parts.unit : null,
                label: 'Territory',
              ),
            ],
          ),
          const SizedBox(height: 16),
          const AppDivider(),
          const SizedBox(height: 16),
          StatRow(
            children: [
              StatBlock(
                value: '${user['followers_count'] ?? 0}',
                label: 'Followers',
              ),
              StatBlock(
                value: '${user['following_count'] ?? 0}',
                label: 'Following',
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _runTile(Map<String, dynamic> run) {
    final id = (run['run_id'] as num?)?.toInt();
    return Column(
      children: [
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: id == null
              ? null
              : () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => RunDetailPage(runId: id)),
                ),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: Row(
              children: [
                const Icon(
                  Icons.directions_run_rounded,
                  color: AppColors.textSecondary,
                  size: 20,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    Fmt.runSummary(run),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.body,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  Fmt.timeAgoFrom(run['created_at']?.toString()),
                  style: AppText.caption,
                ),
              ],
            ),
          ),
        ),
        const AppDivider(),
      ],
    );
  }

  Widget _content() {
    if (_isLoading) {
      return const Padding(
        padding: EdgeInsets.only(top: 80),
        child: Center(child: AppLoader(size: 28)),
      );
    }
    final user = _user;
    if (_error != null || user == null) {
      return Padding(
        padding: const EdgeInsets.only(top: 80),
        child: MessageView(_error ?? 'Failed to load runner'),
      );
    }

    final name = user['name']?.toString() ?? widget.name;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Avatar(name: name, size: 64),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppText.title,
                  ),
                  if (user['follows_you'] == true) ...[
                    const SizedBox(height: 4),
                    Text('Follows you', style: AppText.caption),
                  ],
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        user['is_following'] == true
            ? SecondaryButton(label: 'Following', onPressed: _toggleFollow)
            : PrimaryButton(label: 'Follow', onPressed: _toggleFollow),
        const SizedBox(height: 20),
        _stats(user),
        const SizedBox(height: 26),
        const SectionTitle('Recent runs'),
        const SizedBox(height: 12),
        if (_runs.isEmpty)
          Text('No runs yet.', style: AppText.bodySecondary)
        else
          ..._runs.map(_runTile),
      ],
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
              title: widget.name.isNotEmpty ? widget.name : 'Runner',
              leading: AppIconButton(
                icon: Icons.arrow_back_rounded,
                onTap: () => Navigator.of(context).pop(),
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _load,
                color: AppColors.text,
                backgroundColor: AppColors.surfaceHigh,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
                  child: _content(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
