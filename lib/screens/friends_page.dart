import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import '../services/social_service.dart';
import '../theme/app_theme.dart';
import '../widgets/app_widgets.dart';
import 'runner_profile_page.dart';

/// Search for runners, follow them, and see who follows you.
class FriendsPage extends StatefulWidget {
  /// Opens with the search field focused, for the map's search button.
  final bool focusSearch;

  const FriendsPage({super.key, this.focusSearch = false});

  @override
  State<FriendsPage> createState() => _FriendsPageState();
}

class _FriendsPageState extends State<FriendsPage> {
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  Timer? _debounce;

  // 0 = following, 1 = followers
  int _tab = 0;

  bool _listLoading = true;
  String? _listError;
  List<Map<String, dynamic>> _following = [];
  List<Map<String, dynamic>> _followers = [];

  String _query = '';
  bool _searching = false;
  String? _searchError;
  List<Map<String, dynamic>> _results = [];

  @override
  void initState() {
    super.initState();
    _loadLists();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  List<Map<String, dynamic>> _cards(dynamic data) {
    if (data is! List) return [];
    return data
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
  }

  Future<void> _loadLists({bool quiet = false}) async {
    if (!quiet) {
      setState(() {
        _listLoading = true;
        _listError = null;
      });
    }

    final results = await Future.wait([
      SocialService.following(),
      SocialService.followers(),
    ]);

    if (!mounted) return;

    final a = results[0];
    final b = results[1];
    setState(() {
      _listLoading = false;
      if (a['success'] == true && b['success'] == true) {
        _following = _cards(a['data']);
        _followers = _cards(b['data']);
        _listError = null;
      } else if (!quiet) {
        _listError = (a['message'] ?? b['message'] ?? 'Failed to load')
            .toString();
      }
    });
  }

  void _onQueryChanged(String value) {
    _debounce?.cancel();
    final q = value.trim();
    setState(() => _query = q);

    if (q.length < 2) {
      setState(() {
        _results = [];
        _searching = false;
        _searchError = null;
      });
      return;
    }

    _debounce = Timer(const Duration(milliseconds: 350), () => _search(q));
  }

  Future<void> _search(String q) async {
    setState(() {
      _searching = true;
      _searchError = null;
    });

    final result = await SocialService.search(q);

    // Ignore an answer to a query the user has since changed.
    if (!mounted || q != _query) return;

    setState(() {
      _searching = false;
      if (result['success'] == true) {
        _results = _cards(result['data']);
      } else {
        _results = [];
        _searchError = result['message']?.toString() ?? 'Search failed';
      }
    });
  }

  /// Flips the follow state at once and undoes it if the server refuses.
  Future<void> _toggle(Map<String, dynamic> user) async {
    final id = (user['id'] as num).toInt();
    final wasFollowing = user['is_following'] == true;

    setState(() => user['is_following'] = !wasFollowing);

    final result = wasFollowing
        ? await SocialService.unfollow(id)
        : await SocialService.follow(id);

    if (!mounted) return;

    if (result['success'] == true) {
      _loadLists(quiet: true);
    } else {
      setState(() => user['is_following'] = wasFollowing);
      showAppToast(context, result['message']?.toString() ?? 'Failed');
    }
  }

  Future<void> _openProfile(Map<String, dynamic> user) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => RunnerProfilePage(
          userId: (user['id'] as num).toInt(),
          name: user['name']?.toString() ?? '',
        ),
      ),
    );
    if (mounted) _loadLists(quiet: true);
  }

  Widget _runnerRow(Map<String, dynamic> user) {
    final name = user['name']?.toString() ?? '';
    final km = ((user['total_distance_km'] ?? 0) as num).toDouble();
    final runs = user['total_runs'] ?? 0;
    final followsYou = user['follows_you'] == true;

    return Column(
      children: [
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => _openProfile(user),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Row(
              children: [
                Avatar(name: name),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppText.body.copyWith(
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        '${km.toStringAsFixed(1)} km • $runs runs'
                        '${followsYou ? ' • Follows you' : ''}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppText.caption,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                FollowButton(
                  following: user['is_following'] == true,
                  onTap: () => _toggle(user),
                ),
              ],
            ),
          ),
        ),
        const AppDivider(),
      ],
    );
  }

  Widget _searchField() {
    return ShadInput(
      controller: _searchController,
      focusNode: _searchFocus,
      autofocus: widget.focusSearch,
      onChanged: _onQueryChanged,
      textInputAction: TextInputAction.search,
      placeholder: const Text('Search runners by name or email'),
      leading: const Icon(
        Icons.search_rounded,
        color: AppColors.textMuted,
        size: 20,
      ),
      trailing: _searchController.text.isEmpty
          ? null
          : ShadIconButton.ghost(
              width: 32,
              height: 32,
              padding: EdgeInsets.zero,
              iconSize: 18,
              foregroundColor: AppColors.textMuted,
              icon: const Icon(Icons.close_rounded),
              onPressed: () {
                _searchController.clear();
                _onQueryChanged('');
              },
            ),
    );
  }

  List<Widget> _searchResults() {
    if (_query.length < 2) {
      return const [];
    }
    if (_searching && _results.isEmpty) {
      return const [
        Padding(
          padding: EdgeInsets.symmetric(vertical: 24),
          child: Center(child: AppLoader()),
        ),
      ];
    }
    if (_searchError != null) {
      return [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: ErrorBanner(_searchError!),
        ),
      ];
    }
    if (_results.isEmpty) {
      return [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 24),
          child: Text(
            'No runners found for "$_query". Try another name or email.',
            textAlign: TextAlign.center,
            style: AppText.bodySecondary,
          ),
        ),
      ];
    }
    return _results.map(_runnerRow).toList();
  }

  Widget _tabContent() {
    if (_listLoading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 40),
        child: Center(child: AppLoader(size: 28)),
      );
    }
    if (_listError != null) {
      return Padding(
        padding: const EdgeInsets.only(top: 24),
        child: ErrorBanner(_listError!),
      );
    }

    final list = _tab == 0 ? _following : _followers;
    if (list.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 32),
        child: MessageViewInline(
          icon: _tab == 0
              ? Icons.person_add_alt_1_rounded
              : Icons.people_outline_rounded,
          text: _tab == 0
              ? 'You are not following anyone yet. Search above to find '
                    'runners, then tap Follow to see their territory and runs.'
              : 'No followers yet. When runners follow you, they show up here.',
        ),
      );
    }
    return Column(children: list.map(_runnerRow).toList());
  }

  @override
  Widget build(BuildContext context) {
    final searching = _query.length >= 2;

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: SafeArea(
        child: Column(
          children: [
            ScreenHeader(
              title: 'Friends',
              leading: AppIconButton(
                icon: Icons.arrow_back_rounded,
                onTap: () => Navigator.of(context).pop(),
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: _loadLists,
                color: AppColors.text,
                backgroundColor: AppColors.surfaceHigh,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  keyboardDismissBehavior:
                      ScrollViewKeyboardDismissBehavior.onDrag,
                  padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _searchField(),
                      const SizedBox(height: 16),
                      if (searching) ...[
                        ..._searchResults(),
                        const SizedBox(height: 16),
                      ],
                      SegmentedPill(
                        labels: [
                          'Following · ${_following.length}',
                          'Followers · ${_followers.length}',
                        ],
                        index: _tab,
                        onChanged: (i) => setState(() => _tab = i),
                      ),
                      const SizedBox(height: 16),
                      _tabContent(),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Icon over a short explanation, for empty lists inside a scroll view.
class MessageViewInline extends StatelessWidget {
  final IconData icon;
  final String text;

  const MessageViewInline({super.key, required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Icon(icon, color: AppColors.textMuted, size: 32),
        const SizedBox(height: 12),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Text(
            text,
            textAlign: TextAlign.center,
            style: AppText.bodySecondary,
          ),
        ),
      ],
    );
  }
}
