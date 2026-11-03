#!/bin/bash
# "סדר מהמודל" – building the Mac program (for the kit's maintainer only; not in the ZIPs). Double-click on a Mac.
# Builds מערכת/bin-mac/MoodleSorter.app (shown as "סדר מהמודל", universal2 = Apple silicon + Intel, no Python needed) with PyInstaller inside a temporary venv outside iCloud, signs and notarizes it
# when a "Developer ID Application" certificate and the keychain profile "sader-notary" exist (otherwise builds unsigned),
# then rebuilds "לשיתוף/סדר מהמודל v<N> - Mac.zip". Never asks for, prints or stores a password.
HERE="$(cd "$(dirname "$0")" && pwd)"
TOP="$(dirname "$HERE")"
KIT="$TOP/מערכת"
LOGDIR="$HOME/Library/Logs/SaderMehamoodle"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/build_mac_$(date +%Y%m%d_%H%M%S).log"
RESULT="$HERE/תוצאת בנייה.txt"
WORK="$(mktemp -d /tmp/sader_build.XXXXXX)"
exec > >(tee -a "$LOG") 2>&1
SIGNED="לא"; NOTARIZED="לא"; NOTES=""

finish() {   # $1 = success line
  {
    echo "תוצאת בנייה – $(date '+%Y-%m-%d %H:%M')"
    echo "$1"
    echo "חתום: $SIGNED   ·   עבר notarization של Apple: $NOTARIZED"
    [ -n "$NOTES" ] && printf "%b" "$NOTES"
    echo "יומן מלא: $LOG"
  } > "$RESULT"
  cat "$RESULT"
  osascript -e 'display notification "הבנייה הסתיימה – הפרטים בקובץ תוצאת בנייה.txt" with title "סדר מהמודל"' >/dev/null 2>&1
  rm -rf "$WORK"
  exit 0
}

echo "== סדר מהמודל: בניית גרסת Mac ($(date)) =="
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c "import sys" >/dev/null 2>&1; then
  NOTES+="python3 חסר. אם קפץ חלון 'כלי שורת פקודה' – ללחוץ התקן ואז להריץ שוב.\n"
  finish "❌ לא נבנה: אין python3 במק."
fi
# Universal (Apple silicon + Intel) needs a universal2 Python. Apple's /usr/bin/python3 is one; Homebrew's is arm64 only.
PY=python3
for c in /usr/bin/python3 python3; do
  if "$c" -c "import sysconfig,sys; sys.exit(0 if 'universal2' in sysconfig.get_platform() else 1)" >/dev/null 2>&1; then PY="$c"; break; fi
done
"$PY" -m venv "$WORK/venv" || finish "❌ לא נבנה: לא הצלחתי ליצור סביבת בנייה."
"$WORK/venv/bin/pip" install -q --disable-pip-version-check pyinstaller || finish "❌ לא נבנה: התקנת PyInstaller נכשלה (אין אינטרנט?)."
cp "$KIT/sort_downloads.py" "$WORK/" && cd "$WORK" || finish "❌ לא נבנה: הקוד חסר."
VERSION="$(sed -nE 's/^VERSION = "([0-9.]+)".*/\1/p' sort_downloads.py)"
ARCH="$(uname -m)"
if "$WORK/venv/bin/python" -c "import sysconfig,sys; sys.exit(0 if 'universal2' in sysconfig.get_platform() else 1)"; then
  TARGET="universal2"
else
  TARGET="$ARCH"; NOTES+="⚠ נבנה רק ל-$ARCH: ה-Python שנמצא אינו universal2, אז זה לא ירוץ במק עם מעבד אינטל.\n"
fi
cat > MoodleSorter.spec <<SPEC
a = Analysis(['sort_downloads.py'], excludes=['tkinter', 'unittest', 'pydoc', 'doctest', 'test'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MoodleSorter', console=False, upx=False, strip=False, target_arch='$TARGET')
coll = COLLECT(exe, a.binaries, a.datas, upx=False, strip=False, name='MoodleSorter')
app = BUNDLE(coll, name='MoodleSorter.app', bundle_identifier='local.moodlesorter', version='$VERSION',
             info_plist={'CFBundleName': 'סדר מהמודל', 'CFBundleDisplayName': 'סדר מהמודל', 'LSUIElement': True,
                         'NSHumanReadableCopyright': 'Free to use and share'})
SPEC
"$WORK/venv/bin/pyinstaller" --noconfirm --clean --log-level WARN --distpath "$WORK/dist" --workpath "$WORK/build" MoodleSorter.spec \
  || finish "❌ הבנייה נכשלה (ראו ביומן)."
APP="$WORK/dist/MoodleSorter.app"
PROG="$APP/Contents/MacOS/MoodleSorter"
"$PROG" --version | grep -q MoodleSorter || finish "❌ התוכנה נבנתה אבל לא רצה (ראו ביומן)."
ARCHS="$(lipo -archs "$PROG" 2>/dev/null || echo "$ARCH")"
if [ "$TARGET" = "universal2" ]; then
  case "$ARCHS" in *x86_64*arm64*|*arm64*x86_64*) ;; *) finish "❌ ביקשתי גרסה לאינטל ול-Apple silicon, אבל יצא רק: $ARCHS (ראו ביומן).";; esac
  if arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
    arch -x86_64 "$PROG" --version | grep -q MoodleSorter && NOTES+="נבדק: החלק של אינטל רץ (דרך Rosetta).\n" \
      || finish "❌ החלק של אינטל נבנה אבל לא רץ (ראו ביומן)."
  else
    NOTES+="החלק של אינטל לא נבדק בהרצה: Rosetta לא מותקן במק הזה.\n"
  fi
fi

# ---- signing and notarization (only if the certificate exists) ----
IDENT="$(security find-identity -v -p codesigning 2>/dev/null | grep "Developer ID Application" | head -1 | sed -E 's/.*"(.*)".*/\1/')"
if [ -n "$IDENT" ]; then
  echo "חותם עם: $IDENT"
  find "$APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" -o -perm -u+x \) ! -path "$PROG" -print0 |
    while IFS= read -r -d '' f; do codesign --force --options runtime --timestamp --sign "$IDENT" "$f" || echo "SIGNFAIL $f"; done
  if codesign --force --deep --options runtime --timestamp --sign "$IDENT" "$APP" && codesign --verify --deep --strict "$APP" \
     && "$PROG" --version | grep -q MoodleSorter; then
    SIGNED="כן ($IDENT)"
    if xcrun notarytool history --keychain-profile "sader-notary" >/dev/null 2>&1; then
      ditto -c -k --keepParent "$APP" "$WORK/notarize.zip"
      if xcrun notarytool submit "$WORK/notarize.zip" --keychain-profile "sader-notary" --wait | tee "$WORK/notary.txt" | grep -q "status: Accepted"; then
        NOTARIZED="כן"
        xcrun stapler staple "$APP" && NOTES+="האישור של Apple הוצמד לאפליקציה (staple).\n"
      else
        NOTES+="ה-notarization לא אושר – הפרטים ביומן.\n"
      fi
    else
      NOTES+="דילגתי על notarization: אין פרופיל 'sader-notary'. להגדרה: 'הגדרת חתימה של Apple.command' בתיקייה הזו.\n"
    fi
    spctl -a -vv "$APP" 2>&1 | sed 's/^/spctl: /'
  else
    NOTES+="החתימה נכשלה – נבנתה גרסה לא חתומה (ראו ביומן).\n"; SIGNED="לא (נכשל)"
  fi
else
  NOTES+="דילגתי על חתימה: אין תעודת 'Developer ID Application' במחשב (אחרי אישור החשבון ב-Apple: ליצור אותה ב-Xcode ולהריץ שוב).\n"
fi

# ---- put it in the kit (מערכת/bin-mac/MoodleSorter.app) and rebuild the Mac ZIP ----
mkdir -p "$WORK/bin-mac" && ditto "$APP" "$WORK/bin-mac/MoodleSorter.app" || finish "❌ נבנה, אבל ההכנה להעתקה נכשלה."
rm -rf "$KIT/bin-mac.new" && ditto "$WORK/bin-mac" "$KIT/bin-mac.new" && rm -rf "$KIT/bin-mac" && mv "$KIT/bin-mac.new" "$KIT/bin-mac" \
  || finish "❌ נבנה, אבל ההעתקה לתיקייה מערכת נכשלה."
SADER_MAC_BIN="$WORK/bin-mac" python3 "$HERE/_build_release.py" || finish "⚠ התוכנה נבנתה ונמצאת ב-מערכת/bin-mac, אבל בניית ה-ZIP נכשלה."
SIZE="$(du -sh "$APP" | cut -f1)"
finish "✅ נבנתה גרסת Mac $VERSION ($ARCHS, $SIZE) בשם 'סדר מהמודל' ונשמרה ב-מערכת/bin-mac, וה-ZIP למק בתיקייה לשיתוף עודכן."
