#!/usr/bin/env bash
# Builds packaging/Output/ConvoHub-mac-arm64.dmg on a Mac with Apple Silicon (GitHub Actions runs this too):
#   1) icon        -> build/ConvoHub.icns            (tools/make_icon.py, pure Python)
#   2) PyInstaller -> dist/ConvoHub.app              (packaging/convohub-mac.spec)
#   3) codesign    -> ad-hoc signature, then verified (Apple Silicon refuses to run unsigned code)
#   4) hdiutil     -> the DMG: ConvoHub.app + a link to /Applications (drag to install)
# Needs: uv, and the Xcode command line tools (codesign, hdiutil and lipo ship with macOS / xcode-select --install).
# Run from anywhere:  bash packaging/build_mac.sh
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script builds the macOS app and must run on a Mac." >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "The macOS build is for Apple Silicon (arm64) only; this Mac is $(uname -m)." >&2
  exit 1
fi
command -v uv >/dev/null || { echo "uv is not installed: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2; exit 1; }

VERSION="$(sed -n 's/^version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' pyproject.toml | head -n 1)"
[[ -n "$VERSION" ]] || { echo "Could not read the version from pyproject.toml" >&2; exit 1; }
echo "ConvoHub $VERSION (macOS arm64)"

export UV_PYTHON="${UV_PYTHON:-3.14}"            # same Python as the Windows build
export PYINSTALLER_STRICT_BUNDLE_CODESIGN_ERROR=1 # fail instead of warning if PyInstaller can't sign the bundle
export PYINSTALLER_VERIFY_BUNDLE_SIGNATURE=1      # and let it check its own signature

APP="dist/ConvoHub.app"
ICNS="build/ConvoHub.icns"
DMG="packaging/Output/ConvoHub-mac-arm64.dmg"

echo "1/4 Icon..."
if [[ ! -f "$ICNS" ]]; then
  uv run --no-dev python tools/make_icon.py --icns "$ICNS"
fi

echo "2/4 PyInstaller..."
rm -rf "$APP" dist/ConvoHub
uv run --group build pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/convohub-mac.spec
for exe in ConvoHub convohub-mcp; do
  [[ -x "$APP/Contents/MacOS/$exe" ]] || { echo "Missing $APP/Contents/MacOS/$exe" >&2; exit 1; }
  lipo -archs "$APP/Contents/MacOS/$exe" | grep -qw arm64 || { echo "$exe is not an arm64 program" >&2; exit 1; }
done
plutil -lint "$APP/Contents/Info.plist"
plist_version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"
[[ "$plist_version" == "$VERSION" ]] || { echo "Info.plist has version $plist_version, expected $VERSION" >&2; exit 1; }
[[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP/Contents/Info.plist")" == "ConvoHub" ]] \
  || { echo "CFBundleExecutable is not ConvoHub" >&2; exit 1; }

echo "3/4 Signing (ad-hoc)..."
# Extended attributes (Finder info, quarantine) make codesign fail with "detritus not allowed".
xattr -cr "$APP"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

echo "4/4 DMG..."
STAGE="build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE" "$(dirname "$DMG")"
ditto "$APP" "$STAGE/ConvoHub.app"  # ditto keeps the symlinks and signatures inside the bundle intact
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
# hdiutil occasionally fails with "Resource busy" on CI machines; try a few times.
for attempt in 1 2 3; do
  if hdiutil create -volname ConvoHub -srcfolder "$STAGE" -ov -format UDZO "$DMG"; then
    break
  fi
  if [[ "$attempt" == 3 ]]; then
    echo "hdiutil create failed" >&2
    exit 1
  fi
  echo "hdiutil create failed (attempt $attempt), retrying..." >&2
  sleep 5
done
hdiutil verify "$DMG"
rm -rf "$STAGE"

size="$(du -h "$DMG" | cut -f1)"
echo "Done: $ROOT/$DMG ($size)"
