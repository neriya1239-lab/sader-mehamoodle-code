#!/bin/bash
# "סדר מהמודל" – builds the Safari extension (iPad, iPhone, Mac) as an Xcode project. Maintainer only; double-click on a Mac.
# Takes בנייה/safari-extension + מערכת/moodle_download.js, makes the project with Apple's converter in ~/SaderSafari
# (outside iCloud), sets the signing team, checks that it builds, and opens it in Xcode.
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"; TOP="$(dirname "$HERE")"
[ -f "$(dirname "$0")/signing.local.sh" ] && . "$(dirname "$0")/signing.local.sh"   # TEAM_ID=XXXXXXXXXX (Apple Developer Team ID, not in git)
TEAM="${SADER_TEAM_ID:-${TEAM_ID:-}}"
[ -n "$TEAM" ] || { echo "חסר Team ID של Apple: צרו בתיקייה בנייה קובץ signing.local.sh עם השורה TEAM_ID=XXXXXXXXXX"; exit 1; }
BUNDLE="il.neriya.moodlesorter"; NAME="MoodleSorter"
OUT="$HOME/SaderSafari"; LOG="$OUT/build.log"
mkdir -p "$OUT"; : > "$LOG"
say() { echo "$@"; echo "$@" >> "$LOG"; }
fail() { say ""; say "❌ $1"; say "יומן מלא: $LOG"; read -t 600 -n 1 -s -r -p "אפשר לסגור את החלון."; echo ""; exit 1; }

say "== סדר מהמודל: בניית תוסף Safari ($(date)) =="
xcrun --find safari-web-extension-converter >/dev/null 2>&1 \
  || fail "צריך את Xcode המלא (מה-App Store, חינם), ולפתוח אותו פעם אחת כדי שיסיים להתקין רכיבים. אחר כך להריץ שוב."

# 1. the extension's files, with the downloader itself
EXT="$OUT/extension"; rm -rf "$EXT"; mkdir -p "$EXT"
cp -R "$HERE/safari-extension/." "$EXT/" || fail "לא נמצאה התיקייה בנייה/safari-extension."
cp "$TOP/מערכת/moodle_download.js" "$EXT/" || fail "לא נמצא מערכת/moodle_download.js."
rm -f "$EXT/icon1024.png"                                         # (the App Store icon, not part of the extension)

# 2. the Xcode project (made again each time; nothing of yours lives in it)
rm -rf "$OUT/$NAME"
xcrun safari-web-extension-converter "$EXT" --project-location "$OUT" --app-name "$NAME" --bundle-identifier "$BUNDLE" \
  --swift --copy-resources --no-open --no-prompt --force >> "$LOG" 2>&1 || fail "ההמרה של Apple נכשלה."
PROJ="$(find "$OUT/$NAME" -maxdepth 1 -name '*.xcodeproj' | head -1)"
[ -n "$PROJ" ] || fail "לא נוצר פרויקט Xcode."

# 3. signing team + the name people see under the icon
PBX="$PROJ/project.pbxproj"; [ -f "$PBX" ] || PBX="$PROJ/project.xcproj"   # Xcode 27 calls it project.xcproj
if LC_ALL=C grep -q "buildSettings = {" "$PBX" 2>/dev/null; then
  LC_ALL=C sed -i '' '/DEVELOPMENT_TEAM = /d' "$PBX"
  LC_ALL=C sed -i '' 's/TARGETED_DEVICE_FAMILY = "1,2";/TARGETED_DEVICE_FAMILY = 2;/g' "$PBX"     # iPad only (no iPhone screenshots needed)
  LC_ALL=C sed -i '' "s/buildSettings = {/buildSettings = {\\
				DEVELOPMENT_TEAM = $TEAM;/g" "$PBX"
else
  say "הערה: לא רשמתי את חשבון המפתח בקובץ הפרויקט. ההעלאה ל-App Store לא מושפעת (היא קובעת אותו בעצמה); בהרצה מ-Xcode בוחרים אותו ידנית."
fi
find "$OUT/$NAME" -name Info.plist -not -path '*/build/*' | while read -r P; do
  /usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName סדר מהמודל" "$P" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string סדר מהמודל" "$P" 2>/dev/null
done
# the app's own screen: Hebrew instructions (instead of the converter's English sample page)
find "$OUT/$NAME" -name Main.html -path '*Resources*' | while read -r M; do cp "$HERE/safari-app.html" "$M"; done
# no encryption beyond the system's own (HTTPS): saves the export-compliance question on every upload
find "$OUT/$NAME" -name Info.plist -path '*iOS (App)*' | while read -r P; do
  /usr/libexec/PlistBuddy -c "Add :ITSAppUsesNonExemptEncryption bool false" "$P" 2>/dev/null
done
# the App Store icon: 1024px without transparency (Apple rejects it otherwise)
ICON="$(find "$OUT/$NAME" -path '*AppIcon.appiconset' -type d | head -1)"
if [ -n "$ICON" ] && [ -f "$HERE/safari-extension/icon1024.png" ]; then
  sips -s format jpeg "$HERE/safari-extension/icon1024.png" --out "$OUT/icon.jpg" >/dev/null 2>&1
  for d in $(find "$OUT/$NAME" -path '*AppIcon.appiconset' -type d); do
    sips -s format png "$OUT/icon.jpg" --out "$d/icon1024.png" >/dev/null 2>&1
    python3 - "$d" <<'PY' 2>/dev/null
import json, sys, os
d = sys.argv[1]; p = os.path.join(d, "Contents.json"); c = json.load(open(p))
for im in c.get("images", []):
    if im.get("size") in ("1024x1024", None) or im.get("idiom") in ("universal", "ios-marketing"):
        im["filename"] = "icon1024.png"
json.dump(c, open(p, "w"), indent=2)
PY
  done
fi

# 4. does it build? (without signing, just to catch problems)
SCHEMES="$(xcodebuild -list -project "$PROJ" 2>/dev/null | sed -n '/Schemes:/,$p' | tail -n +2 | sed 's/^ *//')"
IOS="$(echo "$SCHEMES" | grep -i 'ios' | head -1)"; [ -n "$IOS" ] || IOS="$NAME (iOS)"
say "בונה לבדיקה: $IOS"
xcodebuild -project "$PROJ" -scheme "$IOS" -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build >> "$LOG" 2>&1 \
  || fail "הבנייה ל-iPad נכשלה (הפרטים ביומן)."

say ""
say "✅ הפרויקט מוכן ונבנה בלי שגיאות: $PROJ"
say "עכשיו Xcode נפתח. כדי לנסות על ה-iPad:"
say "  1. מחברים את ה-iPad בכבל למק (ובאייפד: 'לסמוך על המחשב הזה').";
say "  2. למעלה ב-Xcode: בוחרים את '$IOS', ולידו את ה-iPad שלך."
say "  3. לוחצים ▶ (Run). בפעם הראשונה: באייפד הגדרות ← כללי ← VPN וניהול מכשירים ← לאשר את המפתח."
say "  4. באייפד: הגדרות ← Apps ← Safari ← הרחבות ← סדר מהמודל ← להפעיל, ולאפשר ל-moodlearn.ariel.ac.il."
open "$PROJ"
read -t 600 -n 1 -s -r -p "אפשר לסגור את החלון."; echo ""
