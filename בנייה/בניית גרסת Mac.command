#!/bin/bash
# "סדר מהמודל" – building the Mac program (for the kit's maintainer only; not in the ZIPs). Double-click on a Mac.
# Builds מערכת/bin-mac/MoodleSorter.app (shown as "סדר מהמודל", universal2 = Apple silicon + Intel, no Python needed) with PyInstaller inside a temporary venv outside iCloud, signs and notarizes it
# when a "Developer ID Application" certificate and the keychain profile "sader-notary" exist (otherwise builds unsigned),
# then rebuilds "לשיתוף/סדר מהמודל v<N> - Mac.zip". Never asks for, prints or stores a password.
# Since v6.4.1 it also builds the 5 launchers as small signed + notarized apps ("התקנת סידור אוטומטי.app" ...; the code is in
# בנייה/mac-launcher), which replace the .command files that Gatekeeper blocked. They go to Mac/ and to the top of the Mac ZIP.
# Without signing + notarization the launchers stay .command files, as before.
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

# ---- the 5 launchers (small apps that open the program in Terminal; see בנייה/mac-launcher/launcher.c) ----
LAUNCH="$WORK/launchers"; LAUNCHERS_OK=""
if bash "$HERE/mac-launcher/build_launchers.sh" "$LAUNCH" "$VERSION"; then
  LAUNCHERS_OK="built"
else
  NOTES+="⚠ בניית אפליקציות ההפעלה נכשלה (ראו ביומן), ולכן נשארים קבצי .command.\n"
fi

# ---- signing and notarization (only if the certificate exists) ----
IDENT="$(security find-identity -v -p codesigning 2>/dev/null | grep "Developer ID Application" | head -1 | sed -E 's/.*"(.*)".*/\1/')"
if [ -n "$IDENT" ]; then
  echo "חותם עם: $IDENT"
  find "$APP/Contents" -type f \( -name "*.dylib" -o -name "*.so" -o -perm -u+x \) ! -path "$PROG" -print0 |
    while IFS= read -r -d '' f; do codesign --force --options runtime --timestamp --sign "$IDENT" "$f" || echo "SIGNFAIL $f"; done
  if [ -n "$LAUNCHERS_OK" ]; then
    for L in "$LAUNCH"/*.app; do
      codesign --force --options runtime --timestamp --sign "$IDENT" "$L" && codesign --verify --strict "$L" \
        || { LAUNCHERS_OK=""; NOTES+="⚠ החתימה של $(basename "$L") נכשלה, ולכן נשארים קבצי .command.\n"; break; }
    done
    [ -n "$LAUNCHERS_OK" ] && LAUNCHERS_OK="signed"
  fi
  if codesign --force --deep --options runtime --timestamp --sign "$IDENT" "$APP" && codesign --verify --deep --strict "$APP" \
     && "$PROG" --version | grep -q MoodleSorter; then
    SIGNED="כן ($IDENT)"
    if xcrun notarytool history --keychain-profile "sader-notary" >/dev/null 2>&1; then
      # one submission for the program and the launchers together (a folder of copies; the ticket covers each of them)
      mkdir -p "$WORK/notarize/סדר מהמודל" && ditto "$APP" "$WORK/notarize/סדר מהמודל/MoodleSorter.app"
      [ "$LAUNCHERS_OK" = "signed" ] && for L in "$LAUNCH"/*.app; do ditto "$L" "$WORK/notarize/סדר מהמודל/$(basename "$L")"; done
      ditto -c -k --keepParent "$WORK/notarize/סדר מהמודל" "$WORK/notarize.zip"
      if xcrun notarytool submit "$WORK/notarize.zip" --keychain-profile "sader-notary" --wait | tee "$WORK/notary.txt" | grep -q "status: Accepted"; then
        NOTARIZED="כן"
        xcrun stapler staple "$APP" && NOTES+="האישור של Apple הוצמד לאפליקציה (staple).\n"
        if [ "$LAUNCHERS_OK" = "signed" ]; then
          LAUNCHERS_OK="notarized"
          for L in "$LAUNCH"/*.app; do
            xcrun stapler staple "$L" >/dev/null && spctl -a -t exec "$L" 2>/dev/null \
              || { LAUNCHERS_OK=""; NOTES+="⚠ האישור של Apple לא הוצמד ל-$(basename "$L"), ולכן נשארים קבצי .command.\n"; break; }
          done
          [ -n "$LAUNCHERS_OK" ] && NOTES+="5 אפליקציות ההפעלה חתומות, מאושרות (notarized) ועם staple.\n"
        fi
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
LAUNCH_ENV=""; DONE_LAUNCHERS="קבצי .command"
if [ "$LAUNCHERS_OK" = "notarized" ]; then        # the launcher apps go to Mac/ (the old .command files are removed by _build_release.py)
  for L in "$LAUNCH"/*.app; do
    N="$(basename "$L")"
    rm -rf "$TOP/Mac/$N.new" && ditto "$L" "$TOP/Mac/$N.new" && rm -rf "$TOP/Mac/$N" && mv "$TOP/Mac/$N.new" "$TOP/Mac/$N" \
      || finish "❌ נבנה, אבל העתקת $N לתיקייה Mac נכשלה."
  done
  LAUNCH_ENV="$LAUNCH"; DONE_LAUNCHERS="5 אפליקציות הפעלה חתומות ומאושרות"
fi
SADER_MAC_BIN="$WORK/bin-mac" SADER_MAC_LAUNCHERS="$LAUNCH_ENV" python3 "$HERE/_build_release.py" \
  || finish "⚠ התוכנה נבנתה ונמצאת ב-מערכת/bin-mac, אבל בניית ה-ZIP נכשלה."
if [ -f "$HERE/release/sader-mac-$VERSION.zip" ]; then   # v6.5: the self-update. Publishing is manual, only after checking.
  NOTES+="קבצי העדכון האוטומטי מוכנים בתיקייה בנייה/release (לא פורסמו). לפרסום, אחרי בדיקה ובאישור:\n"
  NOTES+="  gh release create v$VERSION \"$HERE/release/sader-mac-$VERSION.zip\" \"$HERE/release/update.json\" --repo neriya1239-lab/sader-mehamoodle-code --title \"סדר מהמודל $VERSION\" --notes \"ראו CHANGELOG\"\n"
fi
SIZE="$(du -sh "$APP" | cut -f1)"
finish "✅ נבנתה גרסת Mac $VERSION ($ARCHS, $SIZE) בשם 'סדר מהמודל' ונשמרה ב-מערכת/bin-mac, עם $DONE_LAUNCHERS, וה-ZIP למק בתיקייה לשיתוף עודכן."
