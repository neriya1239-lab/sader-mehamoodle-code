#!/bin/bash
# "סדר מהמודל" – builds the 5 Mac launcher apps (for the kit's maintainer; called by "בניית גרסת Mac.command").
# Usage: bash build_launchers.sh <output folder> <version>
# Makes "<output>/<name>.app" for each launcher: one universal (Apple silicon + Intel) program, launcher.c, and an
# Info.plist with the flag. Signing and notarization are done by the caller. The names and flags must match LAUNCHERS
# in _build_release.py.
set -u
SRC="$(cd "$(dirname "$0")" && pwd)"
OUT="$1"; VERSION="$2"
mkdir -p "$OUT" || exit 1
BIN="$OUT/.SaderLauncher"
clang -arch arm64 -arch x86_64 -mmacosx-version-min=11.0 -O2 -Wall -Werror -o "$BIN" "$SRC/launcher.c" \
  -framework CoreFoundation || { echo "LAUNCHER: compile failed"; exit 1; }

make_app() {   # $1 = name (Hebrew, as people see it), $2 = flag, $3 = short id
  local app="$OUT/$1.app"
  rm -rf "$app"
  mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources" || return 1
  cp "$BIN" "$app/Contents/MacOS/SaderLauncher" || return 1
  /usr/libexec/PlistBuddy -c "Add :CFBundleDevelopmentRegion string he" \
    -c "Add :CFBundleExecutable string SaderLauncher" \
    -c "Add :CFBundleIdentifier string il.neriya.moodlesorter.launcher.$3" \
    -c "Add :CFBundleInfoDictionaryVersion string 6.0" \
    -c "Add :CFBundleName string $1" \
    -c "Add :CFBundleDisplayName string $1" \
    -c "Add :CFBundlePackageType string APPL" \
    -c "Add :CFBundleShortVersionString string $VERSION" \
    -c "Add :CFBundleVersion string $VERSION" \
    -c "Add :LSMinimumSystemVersion string 11.0" \
    -c "Add :LSUIElement bool true" \
    -c "Add :NSHumanReadableCopyright string Free to use and share" \
    -c "Add :SaderFlag string $2" \
    "$app/Contents/Info.plist" >/dev/null || return 1
  printf 'APPL????' > "$app/Contents/PkgInfo"
  # the icon: the same as the program's, if it has one
  local icns
  icns="$(ls "$SRC/icon.icns" 2>/dev/null | head -1)"
  if [ -n "$icns" ]; then
    cp "$icns" "$app/Contents/Resources/icon.icns" && /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string icon" "$app/Contents/Info.plist"
  fi
  "$app/Contents/MacOS/SaderLauncher" --version >/dev/null 2>&1   # (kit not found here = exit 2; only checks that it runs)
  [ $? -le 2 ] || { echo "LAUNCHER: $1 does not run"; return 1; }
  echo "LAUNCHER: built $1.app ($2)"
}

make_app "התקנת סידור אוטומטי" --install install &&
make_app "הסרת סידור אוטומטי" --uninstall uninstall &&
make_app "הגדרות" --setup setup &&
make_app "סדר הורדות" --ask ask &&
make_app "ביטול סידור אחרון" --undo undo || exit 1
rm -f "$BIN"
exit 0
