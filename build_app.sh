#!/bin/bash
# Builds "YuE2 Studio.app" (WKWebView + local Python backend).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="YuE2 Studio"
BUNDLE="$ROOT/build/$APP_NAME.app"
DEST="${1:-$HOME/Applications}"

echo "== compiling =="
rm -rf "$ROOT/build"
mkdir -p "$BUNDLE/Contents/MacOS" "$BUNDLE/Contents/Resources"
swiftc -O -target arm64-apple-macos14.0 \
  -framework Cocoa -framework WebKit \
  "$ROOT/app/main.swift" -o "$BUNDLE/Contents/MacOS/YuE2Studio"

echo "== Info.plist =="
cat > "$BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleExecutable</key><string>YuE2Studio</string>
  <key>CFBundleIdentifier</key><string>studio.yue2.app</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSApplicationCategoryType</key><string>public.app-category.music</string>
  <key>StudioDir</key><string>$ROOT</string>
  <key>StudioPort</key><string>8787</string>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PLIST

echo "== signing (ad-hoc) =="
codesign --force --deep --sign - "$BUNDLE" >/dev/null 2>&1 || echo "  (codesign failed, continuing anyway)"

mkdir -p "$DEST"
echo "== installing into $DEST =="
rm -rf "$DEST/$APP_NAME.app"
cp -R "$BUNDLE" "$DEST/"
xattr -dr com.apple.quarantine "$DEST/$APP_NAME.app" 2>/dev/null || true

echo "done: $DEST/$APP_NAME.app"
echo "open it with: open \"$DEST/$APP_NAME.app\""
