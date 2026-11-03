#!/bin/bash
# "סדר מהמודל" v6.4 - משנה הגדרות: לאן לשים, איך לסדר, שמות קבצים
cd "$(dirname "$0")/../מערכת" || exit 1
P=bin-mac/MoodleSorter.app/Contents/MacOS/MoodleSorter
if [ -x "$P" ] && "$P" --version >/dev/null 2>&1; then
  "$P" --setup                                   # the program itself, no Python needed
elif command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then
  python3 sort_downloads.py --setup
else
  echo ""
  echo "Python לא מותקן במק, והכלי צריך אותו."
  echo "1. אם קפץ חלון שמציע להתקין 'כלי שורת פקודה' (Command Line Tools) - ללחוץ 'התקן'."
  echo "   או להוריד Python מ-https://www.python.org/downloads/"
  echo "2. אחרי ההתקנה ללחוץ שוב לחיצה כפולה על הקובץ הזה."
fi
echo ""
read -t 120 -n 1 -s -r -p "אפשר לסגור את החלון (או ללחוץ על מקש כלשהו)."
echo ""
