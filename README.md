# סדר מהמודל

כלי שמוריד את קובצי הקורסים מהמודל ומסדר אותם במחשב בתיקיות לפי קורס וסוג (הרצאות, תרגולים, מבחנים...).
נבנה באוניברסיטת אריאל, ועובד בכל אוניברסיטה ומכללה שיש בה Moodle (ראו "אוניברסיטאות ומכללות"). English below.

## איך זה עובד, בקצרה
1. **תוסף Chrome** (`מערכת/תוסף Chrome/`): כל לילה הוא פותח את המודל בטאב ברקע, דרך ההתחברות שכבר קיימת ב-Chrome, ומוריד רק קבצים חדשים מהקורסים שבחרתם. לחיצה על סמל התוסף בתוך המודל פותחת חלון שבו בוחרים קורסים.
2. **הסדרן** (`מערכת/sort_downloads.py`): רץ ברקע במחשב, מזהה את הקבצים שהתוסף הוריד ומעביר אותם מתיקיית ההורדות לתיקיית הקורס המתאים.
3. **תוסף Safari** (`בנייה/safari-extension/`), לאייפד, לאייפון ולמק: לחיצה אחת בתוך המודל, וכל הקבצים החדשים יורדים כקובץ ZIP אחד שכבר מסודר בתיקיות.

## פרטיות ובטיחות
- התוסף לא רואה, לא מקליד ולא שומר סיסמאות. הוא משתמש בהתחברות הקיימת של הדפדפן.
- הוא קורא רק מאתר המודל ולא שולח מידע לשום אתר אחר.
- הסדרן עובד בלי אינטרנט ובלי הרשאות מנהל. הוא מזיז רק קבצים שהתוסף רשם, ורק לתוך תיקיית הקורסים, ולעולם לא דורס קובץ. כל ריצה נרשמת ביומן, ואפשר לבטל אותה (`--undo`).

## אוניברסיטאות ומכללות
- **בהתקנה** נפתח דף ההגדרות של התוסף, ובוחרים בו את המוסד. ברשימה (נבדקה ב-3.11.2026): אריאל, בן-גוריון, בר-אילן, הטכניון, האוניברסיטה הפתוחה, המרכז האקדמי לב (JCT), עזריאלי, SCE, המכללה למינהל, אחוה, כנרת, רופין, גליל מערבי ולוינסקי-וינגייט. הרשימה נמצאת ב-`בנייה/extension/universities.js`.
- **לא ברשימה?** בוחרים "אחר" ומקלידים את כתובת המודל (גם בתת-תיקייה, למשל `https://moodle.example.ac.il/moodle`). Chrome מבקש הרשאה לאתר הזה בלבד.
- **אילו קורסים יורדים:** באריאל, לפי קוד הסמסטר בשם הקורס (`_תשפז_א`). בשאר המוסדות, הקורסים ש-Moodle מציג כ"בתהליך" (In progress). תמיד אפשר לבחור ידנית: לוחצים על סמל התוסף בתוך המודל.
- **ידני:** סמל התוסף עובד בכל אתר Moodle, גם בלי הגדרות.
- **רוצים להוסיף מוסד לרשימה?** מוסיפים שורה ל-`universities.js` (שם, כתובת, והדף שנפתח בלילה, בדרך כלל `/my/`).

## מבנה התיקיות
| תיקייה | מה יש בה |
|---|---|
| `מערכת/` | הליבה: `sort_downloads.py` (הסדרן), `moodle_download.js` (קוד ההורדה שרץ בדף המודל), `CHANGELOG.md`, ותוסף ה-Chrome בגרסה שנשלחת למשתמשים |
| `Windows/` | קיצורי `.bat`: סידור, הגדרות, התקנה והסרה של הסידור האוטומטי, ביטול הסידור האחרון |
| `Mac/` | אותם קיצורים כקובצי `.command` |
| `בנייה/extension/` | מקור תוסף Chrome |
| `בנייה/safari-extension/` | מקור תוסף Safari |
| `בנייה/` | סקריפטי בנייה: `_build_release.py`, `build_windows.py`, ובמק בניית האפליקציה, תוסף Safari, הגדרת החתימה של Apple והעלאה ל-App Store |
| `בנייה/לחנות Chrome/` | הטקסטים והסמל לדף התוסף בחנות |
| `התחל כאן.html` | המדריך למשתמשים (התקנה, הגדרות, כיבוי). נבנה מ-`בנייה/_guide.txt` |
| `בדיקות/` | בדיקות של גרסה 6.4: Moodle מדומה (`mock_moodle.py`) ו-Chrome בלי חלון (`test_js64.mjs`), התוסף (`test_bg64.mjs`, `test_opt64.mjs`) והאשף (`test_uni64.py`) |

## הרצה מהקוד
```
python מערכת/sort_downloads.py          # מראה מה היה זז, בלי להזיז כלום
python מערכת/sort_downloads.py --ask    # מראה את התוכנית ושואל לפני ביצוע
python מערכת/sort_downloads.py --setup  # אשף ההגדרות
```
כדי לטעון את התוסף מהקוד: ב-`chrome://extensions` מדליקים "מצב מפתח", לוחצים "טעינת פריט לא ארוז" ובוחרים את `בנייה/extension`.

## מה לא נמצא כאן
קבצים בנויים (exe, app, zip), הגדרות אישיות (`settings.json`), יומנים ואישורי חתימה. כל אלה נוצרים מחדש בבנייה או נשמרים רק במחשב.

## רישיון וקרדיט
הקוד פתוח לקריאה ולשימוש לפי [Apache License 2.0](LICENSE):
- מותר להשתמש, ללמוד, לשנות ולשתף.
- **חובה לתת קרדיט:** כל עותק או גרסה משונה חייבים לכלול את הקבצים `LICENSE` ו-`NOTICE`, ולציין מה שונה.
- **השם והסמל לא כלולים ברישיון:** גרסה משונה צריכה שם אחר, ואסור להציג אותה כאילו היא "סדר מהמודל" המקורי.
- אין אחריות: הקוד מסופק כמו שהוא (AS IS).

---

## English

**Sader Mehamoodle** ("tidy from Moodle") downloads new course files from Moodle every night and sorts them on your computer into folders by course and type (lectures, tutorials, homework, exams...).

- **Chrome extension** (`בנייה/extension/` + `מערכת/moodle_download.js`): every night it opens Moodle in a background tab with your existing sign-in (it never sees or stores passwords) and downloads only new files of the courses you chose. Click its icon inside Moodle to pick courses and files.
- **Sorter** (`מערכת/sort_downloads.py`, also built as a no-Python Windows/Mac program): moves the downloaded files from Downloads into `<courses folder>/<course>/<type>`. Offline, no admin rights, never overwrites, every run can be undone (`--undo`).
- **Safari extension** (`בנייה/safari-extension/`): iPad/iPhone/Mac, one click gives one ZIP already sorted into folders.

**Any university:** the settings page opens after installing the extension. Pick your institution (14 Israeli universities and colleges are listed in `universities.js`) or choose "אחר" (other) and type your Moodle address. Outside Ariel, the courses Moodle marks as *In progress* are downloaded by default.

**Run from source:** `python מערכת/sort_downloads.py --ask` (shows the plan, then asks). Load the extension unpacked from `בנייה/extension` in `chrome://extensions` (Developer mode); copy `מערכת/moodle_download.js` into it first.

**License:** [Apache License 2.0](LICENSE). Keep `LICENSE` and `NOTICE` (credit to the original project) in any copy, and mark your changes. The name "סדר מהמודל" / "Sader Mehamoodle" and its icon are not licensed: a modified version must use another name.
