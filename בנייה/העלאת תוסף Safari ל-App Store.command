#!/bin/bash
# "סדר מהמודל" – archives the Safari extension app (iPad/iPhone) and uploads it to App Store Connect. Maintainer only.
# Before the first run: the app must exist in App Store Connect with the bundle ID below, and Xcode must be signed in
# to the Apple account (Xcode > Settings > Accounts). Run "בניית תוסף Safari.command" first.
# Usage: double-click (or bash "<this file>" <build number>). Each upload needs a new build number (1, 2, 3...).
cd "$(dirname "$0")" || exit 1
[ -f "$(dirname "$0")/signing.local.sh" ] && . "$(dirname "$0")/signing.local.sh"   # TEAM_ID=XXXXXXXXXX (Apple Developer Team ID, not in git)
TEAM="${SADER_TEAM_ID:-${TEAM_ID:-}}"
[ -n "$TEAM" ] || { echo "חסר Team ID של Apple: צרו בתיקייה בנייה קובץ signing.local.sh עם השורה TEAM_ID=XXXXXXXXXX"; exit 1; }
NAME="MoodleSorter"; OUT="$HOME/SaderSafari"; LOG="$OUT/upload.log"
VER="$(grep -o '"version": *"[0-9.]*"' safari-extension/manifest.json | grep -o '[0-9][0-9.]*')"; VER="${VER:-1.0}"   # the App Store version = the extension's
PROJ="$OUT/$NAME/$NAME.xcodeproj"; ARCH="$OUT/$NAME.xcarchive"
: > "$LOG"
say() { echo "$@"; echo "$@" >> "$LOG"; }
fail() { say ""; say "❌ $1"; say "יומן מלא: $LOG"; read -t 600 -n 1 -s -r -p "אפשר לסגור את החלון."; echo ""; exit 1; }
[ -d "$PROJ" ] || fail "אין פרויקט. קודם להריץ את 'בניית תוסף Safari.command'."
BUILD="${1:-}"
if [ -z "$BUILD" ]; then
  LAST="$(cat "$OUT/last_build" 2>/dev/null || echo 0)"; BUILD=$((LAST + 1))
fi
say "== העלאה ל-App Store: גרסה $VER, build $BUILD ($(date)) =="
SCHEME="$NAME (iOS)"
say "1/2 בונה ארכיון..."
rm -rf "$ARCH"
xcodebuild -project "$PROJ" -scheme "$SCHEME" -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$ARCH" -allowProvisioningUpdates DEVELOPMENT_TEAM="$TEAM" CURRENT_PROJECT_VERSION="$BUILD" MARKETING_VERSION="$VER" TARGETED_DEVICE_FAMILY=2 \
  archive >> "$LOG" 2>&1 || fail "הארכיון נכשל (חתימה? אולי צריך להתחבר ב-Xcode ← Settings ← Accounts)."
cat > "$OUT/export.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>method</key><string>app-store-connect</string>
<key>destination</key><string>upload</string>
<key>teamID</key><string>$TEAM</string>
<key>signingStyle</key><string>automatic</string>
</dict></plist>
PL
say "2/2 מעלה ל-App Store Connect (כמה דקות)..."
xcodebuild -exportArchive -archivePath "$ARCH" -exportOptionsPlist "$OUT/export.plist" -exportPath "$OUT/export" \
  -allowProvisioningUpdates >> "$LOG" 2>&1 || fail "ההעלאה נכשלה. אם כתוב ביומן שהאפליקציה לא קיימת: צריך ליצור אותה קודם ב-App Store Connect."
echo "$BUILD" > "$OUT/last_build"
say ""
say "✅ הועלה (build $BUILD). בעוד 10–30 דקות הוא יופיע ב-App Store Connect, באפליקציה ← TestFlight / גרסה $VER ← Build."
read -t 600 -n 1 -s -r -p "אפשר לסגור את החלון."; echo ""
