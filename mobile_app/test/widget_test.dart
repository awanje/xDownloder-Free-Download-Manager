import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:xdownloader_mobile/screens/setup_screen.dart';

void main() {
  testWidgets('Setup screen shows the connect prompt', (WidgetTester tester) async {
    await tester.pumpWidget(MaterialApp(home: SetupScreen(onDone: () {})));
    expect(find.text('Connect X Downloader'), findsOneWidget);
    expect(find.text('Project URL'), findsOneWidget);
  });
}
