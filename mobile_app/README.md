# X Downloader - mobile app

Flutter companion app for [X Downloader](../README.md). It shows your downloads and their live progress, and lets you send a link to your PC to download. Cloud sync runs on Supabase (`lib/config.dart` holds the project URL and publishable key).

```bash
flutter pub get
flutter run                  # debug build on a connected device or emulator
flutter build apk --release  # installable APK
```

Android is the supported target. The `ios/` folder is generated source that hasn't been built or tested.
