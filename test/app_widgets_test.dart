import 'package:fitness_game_app/theme/app_theme.dart';
import 'package:fitness_game_app/widgets/app_widgets.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

Widget _app(Widget child) {
  return ShadApp.custom(
    themeMode: ThemeMode.dark,
    darkTheme: AppShadTheme.dark(),
    appBuilder: (context) => MaterialApp(
      theme: AppTheme.dark(),
      builder: (context, child) => ShadAppBuilder(child: child!),
      home: Scaffold(body: Center(child: child)),
    ),
  );
}

void main() {
  setUpAll(() => GoogleFonts.config.allowRuntimeFetching = false);

  testWidgets('buttons are shadcn buttons and respect loading and disabled', (
    tester,
  ) async {
    var taps = 0;
    await tester.pumpWidget(
      _app(
        Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 300,
              child: PrimaryButton(label: 'Go', onPressed: () => taps++),
            ),
            const SizedBox(
              width: 300,
              child: SignatureButton(label: 'Start', onPressed: null),
            ),
            SizedBox(
              width: 300,
              child: DestructiveButton(
                label: 'Stop',
                loading: true,
                onPressed: () => taps += 10,
              ),
            ),
          ],
        ),
      ),
    );

    expect(find.byType(ShadButton), findsNWidgets(3));
    await tester.tap(find.text('Go'));
    await tester.tap(find.text('Start'), warnIfMissed: false);
    await tester.tap(find.byType(CircularProgressIndicator));
    expect(taps, 1);
  });

  testWidgets('segmented control reports the tapped segment', (tester) async {
    var index = 0;
    await tester.pumpWidget(
      _app(
        StatefulBuilder(
          builder: (context, setState) => SizedBox(
            width: 300,
            child: SegmentedPill(
              labels: const ['Friends', 'Everyone'],
              index: index,
              onChanged: (i) => setState(() => index = i),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Everyone'));
    await tester.pump();
    expect(index, 1);
  });

  testWidgets('text field validates through a Form', (tester) async {
    final key = GlobalKey<FormState>();
    final controller = TextEditingController();
    await tester.pumpWidget(
      _app(
        SizedBox(
          width: 300,
          child: Form(
            key: key,
            child: AppTextField(
              controller: controller,
              label: 'Email',
              hint: 'Enter your email',
              validator: (v) => (v ?? '').isEmpty ? 'Required' : null,
            ),
          ),
        ),
      ),
    );

    expect(key.currentState!.validate(), isFalse);
    await tester.pump();
    expect(find.text('Required'), findsOneWidget);

    await tester.enterText(find.byType(EditableText), 'a@b.co');
    expect(controller.text, 'a@b.co');
    expect(key.currentState!.validate(), isTrue);
  });

  testWidgets('chip, avatar, banner, progress and toast render', (
    tester,
  ) async {
    await tester.pumpWidget(
      _app(
        SizedBox(
          width: 300,
          child: Builder(
            builder: (context) => Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const AppChip('You', color: AppColors.signature),
                const Avatar(name: 'asha'),
                const ErrorBanner('Something failed'),
                const AppProgressBar(value: 0.4),
                const AppCard(child: Text('Card')),
                GestureDetector(
                  onTap: () => showAppToast(context, 'Loop claimed · 3,240 m²'),
                  child: const Text('toast'),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    expect(find.text('You'), findsOneWidget);
    expect(find.text('A'), findsOneWidget);
    expect(find.text('Something failed'), findsOneWidget);
    expect(find.byType(ShadProgress), findsOneWidget);
    expect(find.byType(ShadCard), findsOneWidget);

    await tester.tap(find.text('toast'));
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Loop claimed · 3,240 m²'), findsOneWidget);
    await tester.pump(const Duration(seconds: 6));
    await tester.pumpAndSettle();
  });
}
