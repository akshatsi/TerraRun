import 'package:flutter_test/flutter_test.dart';

import 'package:fitness_game_app/config.dart';

void main() {
  test('API base URL has no trailing slash', () {
    expect(Config.baseUrl.endsWith('/'), isFalse);
  });
}
