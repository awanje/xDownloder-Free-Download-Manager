# X Downloader

A fast, resumable download manager for Windows, with a browser extension and an Android companion app that show your downloads (and live progress) on every device you're signed in on.

## Features

- **Multi-connection downloads** - files are split into segments and fetched in parallel, with pause and resume.
- **Streams** - HLS (`.m3u8`) and DASH (`.mpd`) videos are downloaded and muxed with ffmpeg.
- **YouTube and other video sites** - powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp), with a quality picker.
- **Browser extension** (Chrome / Edge) - takes over browser downloads, adds a *Download with X Downloader* right-click item, and puts a download button on videos it detects.
- **Cross-device sync** - sign in on the desktop app and the Android app to see every download and its progress on both. Paste a link on your phone and your PC downloads it (app stores don't allow downloading video directly on mobile).

## Install

Grab the latest files from the [**Releases**](../../releases/latest) page.

### Windows app

1. Download `X-Downloader-Setup-<version>.exe` and run it. It installs for your user account, no admin rights needed.
2. Windows SmartScreen may say *"Windows protected your PC"* because the installer isn't code-signed. Click **More info -> Run anyway**.
3. Prefer no installer? Download the `...-windows-portable.zip`, unzip it anywhere, and run `X Downloader.exe`.

ffmpeg (needed for streams) is downloaded automatically the first time it's required.

### Browser extension

Chrome and Edge don't allow installing extensions from outside their store without developer mode, so:

1. Open `chrome://extensions` (or `edge://extensions`) and switch on **Developer mode**.
2. Click **Load unpacked** and choose the extension folder. If you used the installer, open the Start Menu shortcut **X Downloader browser extension folder** to find it; otherwise unzip `X-Downloader-Extension-<version>.zip` from the release.

The X Downloader desktop app must be running for the extension to hand downloads over. If it isn't running, the browser keeps handling the download itself, so nothing is lost.

### Android app

1. Download `X-Downloader-<version>-android.apk` on your phone.
2. Allow *Install unknown apps* for your browser or file manager when Android asks, then open the APK.

### iOS

The iOS project files are in `mobile_app/ios`, but there is no prebuilt iOS app. It hasn't been built or tested because that needs a Mac with Xcode.

## Accounts and cloud sync

Sync uses a hosted [Supabase](https://supabase.com) backend. The apps ship pointing at the project's default backend, so you only need to create an account (email + password) on the sign-in screen. Row-level security means each account can only see its own downloads. The API key inside the apps is a *publishable* key, which is designed to be public.

### Run your own backend instead

1. Create a free Supabase project.
2. Open **SQL Editor** and run [`supabase_schema.sql`](supabase_schema.sql).
3. In **Authentication -> Sign In / Providers**, turn off **Confirm email** (the apps have no web page to send confirmation links to).
4. Desktop app: **Settings -> Cloud Sync**, paste your project URL and publishable key.
5. Android app: change `defaultUrl` / `defaultKey` in [`mobile_app/lib/config.dart`](mobile_app/lib/config.dart) and rebuild. Do the same for the defaults in [`app/storage.py`](app/storage.py) if you want your own desktop builds to use it out of the box.

## Run from source

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python main.py
```

Build the Windows installer yourself (needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer; the portable zip works without it):

```powershell
powershell -ExecutionPolicy Bypass -File build_windows.ps1 -Version 1.0.0
```

Build the Android app (needs the [Flutter SDK](https://flutter.dev), 3.35+):

```bash
cd mobile_app
flutter pub get
flutter build apk --release
```

### Publishing a release

Push a version tag and GitHub Actions builds the installer, portable zip, extension zip and Android APK, then attaches them to a new release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow is [`.github/workflows/release.yml`](.github/workflows/release.yml).

## Project layout

| Path | What it is |
| --- | --- |
| `app/` | Download engine, manager, local bridge server for the extension, cloud sync |
| `ui/` | PySide6 desktop interface |
| `extension/` | Chrome / Edge extension (Manifest V3) |
| `mobile_app/` | Flutter app (Android; iOS source only) |
| `installer/` | Inno Setup script for the Windows installer |
| `supabase_schema.sql` | Database schema for cloud sync |

## Responsible use

Only download content you have the right to download. DRM-protected streams aren't supported, and downloading from some sites may be against their terms of service. You're responsible for how you use this tool.
