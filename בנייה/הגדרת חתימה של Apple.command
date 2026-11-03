#!/bin/bash
# "סדר מהמודל" – one-time setup of Apple notarization (maintainer only; not in the ZIPs). Double-click on a Mac.
# Saves a keychain profile named "sader-notary". The app-specific password is typed ONLY into Apple's own notarytool
# prompt; this script never asks for it, prints it, logs it or stores it.
echo "== הגדרת חתימה של Apple עבור 'סדר מהמודל' =="
SUBJECT="$(security find-certificate -c "Developer ID Application" -p 2>/dev/null | openssl x509 -noout -subject 2>/dev/null)"
if [ -z "$SUBJECT" ]; then
  echo ""
  echo "קודם צריך ליצור תעודת Developer ID Application ב-Xcode"
  echo "(Xcode ← Settings ← Accounts ← Manage Certificates ← + ← Developer ID Application), ואז להריץ שוב."
  read -t 300 -n 1 -s -r -p "אפשר לסגור את החלון."; echo ""; exit 0
fi
TEAM="$(echo "$SUBJECT" | sed -nE 's/.*OU ?= ?([A-Z0-9]{10}).*/\1/p')"
if [ -z "$TEAM" ]; then
  echo "לא הצלחתי לזהות את ה-Team ID מהתעודה:"; echo "$SUBJECT"
  read -t 300 -n 1 -s -r -p "אפשר לסגור את החלון."; echo ""; exit 0
fi
echo "נמצאה תעודה. Team ID: $TEAM"
echo ""
read -r -p "מה כתובת המייל של ה-Apple ID שלך? " APPLEID
[ -z "$APPLEID" ] && { echo "לא הוקלד מייל. לא נעשה כלום."; exit 0; }
echo ""
echo "עכשיו Apple תבקש 'app-specific password' (סיסמה ייעודית שיוצרים ב-account.apple.com ← Sign-In and Security)."
echo "מקלידים אותה רק בשאלה של Apple שתופיע מיד. היא נשמרת במחזיק המפתחות של המק, לא בקובץ הזה."
echo ""
if xcrun notarytool store-credentials "sader-notary" --apple-id "$APPLEID" --team-id "$TEAM"; then
  echo ""; echo "✅ נשמר. מעכשיו 'בניית גרסת Mac.command' תחתום ותשלח לאישור של Apple לבד."
else
  echo ""; echo "❌ השמירה לא הצליחה. אפשר להריץ שוב."
fi
read -t 300 -n 1 -s -r -p "אפשר לסגור את החלון."; echo ""
