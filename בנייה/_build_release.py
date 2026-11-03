# _build_release.py — for the kit's maintainer only (not included in the ZIPs).
# Builds, from מערכת/moodle_download.js, _guide.txt and the launcher templates below:
#   - the kit folder's own layout: "התחל כאן.html", Windows/*.bat, Mac/*.command, מערכת/SHA256SUMS.txt
#     and מערכת/תוסף Chrome (the extension, from בנייה/extension + moodle_download.js) for installing it by hand
#   - two ZIPs for sharing: "לשיתוף/סדר מהמודל v<N> - Windows.zip" and "... - Mac.zip" (launchers at the top, one OS each).
#     They include the no-Python program when it was built: מערכת/bin-win (build_windows.py), מערכת/bin-mac (בניית גרסת Mac).
import hashlib, html, os, re, sys, urllib.parse, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent         # the "בנייה" folder (maintainer only)
TOP = HERE.parent                              # the folder the user sees
KIT = TOP / "מערכת"
EXT = HERE / "extension"
VERSION = re.search(r'VERSION = "?([\d.]+)"?', (KIT / "sort_downloads.py").read_text(encoding="utf-8")).group(1)
SYSTEM = ["מערכת/sort_downloads.py", "מערכת/moodle_download.js", "מערכת/CHANGELOG.md"]   # shipped as is; no personal files
LAUNCHERS = {
    "התקנת סידור אוטומטי": ("--install", "מתקין סידור אוטומטי שפועל ברקע ומתחיל עם המחשב"),
    "הסרת סידור אוטומטי": ("--uninstall", "מסיר את הסידור האוטומטי"),
    "הגדרות": ("--setup", "משנה הגדרות: לאן לשים, איך לסדר, שמות קבצים"),
    "סדר הורדות": ("--ask", "סידור ידני: מראה מה יעבור לאן ושואל לפני שמזיז"),
    "ביטול סידור אחרון": ("--undo", "מחזיר את הסידור האחרון לתיקיית ההורדות (שואל קודם)"),
}

# ---------------- launchers ----------------
# The Windows console shows Hebrew reversed, so a .bat never echoes Hebrew itself: messages go through a Windows message box.
MSG = ("powershell -NoProfile -Command \"Add-Type -AssemblyName PresentationFramework; "
       "$r=[System.Windows.MessageBox]::Show(({text}) -join [char]10, 'סדר מהמודל', '{buttons}', '{icon}', 'Yes', 'RtlReading'); "
       "if ($r -eq 'Yes') {{ exit 1 }} else {{ exit 0 }}\"")
BAT = r'''@echo off
chcp 65001 >nul
rem "סדר מהמודל" v{version} - {desc}
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0{rel}"
if not exist "bin-win\MoodleSorter.exe" goto python
rem the program itself - no Python needed
bin-win\MoodleSorter.exe {flag}
echo.
pause
exit /b

:python
set PY=
where py >nul 2>nul && py -3 -c "import sys" >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && python -c "import sys" >nul 2>nul && set PY=python
if not defined PY goto nopython
%PY% sort_downloads.py {flag}
echo.
pause
exit /b

:nopython
{ask}
if errorlevel 1 goto winget
exit /b

:winget
echo Installing Python (winget)...
winget install -e --id Python.Python.3.12 --scope user
{done}
'''
ASK = MSG.format(text="'Python לא מותקן במחשב, והכלי צריך אותו.', '', 'להתקין אותו עכשיו? (לוקח כמה דקות, בלי הרשאות מנהל)', '', "
                      "'אפשר גם להתקין לבד מ-python.org - ובהתקנה לסמן Add python.exe to PATH.'", buttons="YesNo", icon="Question")
DONE = MSG.format(text="'אם ההתקנה הצליחה: לחצו שוב לחיצה כפולה על אותו קובץ.', '', 'אם לא: התקינו מ-python.org ולחצו שוב.'",
                  buttons="OK", icon="Information")
CMD = '''#!/bin/bash
# "סדר מהמודל" v{version} - {desc}
cd "$(dirname "$0")/{rel}" || exit 1
P=bin-mac/MoodleSorter.app/Contents/MacOS/MoodleSorter
if [ -x "$P" ] && "$P" --version >/dev/null 2>&1; then
  "$P" {flag}                                   # the program itself, no Python needed
elif command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then
  python3 sort_downloads.py {flag}
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
'''


def bat(flag, desc, rel):
    return BAT.format(version=VERSION, desc=desc, rel=rel, flag=flag, ask=ASK, done=DONE).replace("\n", "\r\n").encode("utf-8")


def command(flag, desc, rel):
    return CMD.format(version=VERSION, desc=desc, rel=rel, flag=flag).encode("utf-8")


# ---------------- the guide ("התחל כאן") ----------------
def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r'<code dir="auto">\1</code>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"\[(.+?)\]\(#([\w-]+)\)", r'<a href="#\2">\1</a>', t)          # [text](#id): a link inside the page
    return re.sub(r"(https?://[^\s<)]+)", r'<a href="\1">\1</a>', t)


def guide(os_name):
    src = (HERE / "_guide.txt").read_text(encoding="utf-8")
    for tag in ("win", "mac", "both"):
        src = re.sub(r"\{%s\}(.*?)\{/%s\}" % (tag, tag), (lambda m: m.group(1)) if tag == os_name else "", src, flags=re.S)
    out, lst, table, pre = [], None, False, None
    def close():
        nonlocal lst, table
        if lst: out.append(f"</{lst}>"); lst = None
        if table: out.append("</table>"); table = False
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("```"):                     # a picture made of text (a folder tree): shown as is
            if pre is None:
                close(); pre = []
            else:
                out.append('<pre class="tree">' + html.escape("\n".join(pre)) + "</pre>"); pre = None
            continue
        if pre is not None:
            pre.append(line.rstrip()); continue
        if s.startswith(":::"):                     # ":::פתיחה כותרת" ... ":::" = a section that opens on a click
            close()
            out.append(f'<details id="appendix"><summary>{inline(s[3:].strip())}</summary>' if s[3:].strip() else "</details>")
            continue
        if not s:
            close(); continue
        if s.startswith("|"):
            if re.fullmatch(r"\|[-| ]+\|", s):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if lst: out.append(f"</{lst}>"); lst = None
            tag = "th" if not table else "td"
            if not table: out.append("<table>"); table = True
            out.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>"); continue
        m = re.match(r"(#{1,3}) (.*)", s)
        if m:
            close(); n = len(m.group(1)); title = m.group(2)
            hid = re.search(r"\s*\{#([\w-]+)\}$", title)              # "## כותרת {#id}" = a target for the table of contents
            if hid:
                title = title[:hid.start()]
            out.append(f"<h{n}" + (f' id="{hid.group(1)}"' if hid else "") + f">{inline(title)}</h{n}>"); continue
        m = re.match(r"(\d+\.|-) (.*)", s)
        if m:
            kind = "ol" if m.group(1)[0].isdigit() else "ul"
            if table: out.append("</table>"); table = False
            if lst != kind:
                if lst: out.append(f"</{lst}>")
                start = m.group(1)[:-1] if kind == "ol" else ""      # a numbered list interrupted by notes continues its count
                out.append(f'<ol start="{start}">' if start else f"<{kind}>"); lst = kind
            out.append(f"<li>{inline(m.group(2))}</li>"); continue
        close(); out.append(f"<p>{inline(s)}</p>")
    close()
    body = "\n".join(out).replace("<h2>English</h2>", '</div><div dir="ltr" lang="en" class="en"><h2>English</h2>')
    label = {"win": " (Windows)", "mac": " (Mac)", "both": ""}[os_name]
    return f"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><title>סדר מהמודל – התחל כאן{label}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font:17px Arial,sans-serif;max-width:760px;margin:28px auto;padding:0 16px;line-height:1.65;color:#111;background:#fff}}
h1{{color:#0b4f8a}} h2{{background:#eef4fa;border-radius:8px;padding:6px 12px;margin-top:34px}} h3{{margin:22px 0 4px}}
table{{border-collapse:collapse;width:100%;margin:8px 0}} td,th{{border:1px solid #ccd;padding:5px 8px;vertical-align:top;text-align:start}} th{{background:#f4f6f8}}
code{{background:#f2f2f2;border-radius:4px;padding:1px 5px;font-size:15px}} .en{{text-align:left;margin-top:40px;border-top:2px solid #ddd}}
.ver{{color:#777;font-size:13px;margin-top:40px}}
pre.tree{{background:#f7f9fb;border:1px solid #dde;border-radius:8px;padding:10px 14px;font:15px/1.5 Consolas,Menlo,monospace;direction:rtl;text-align:right;white-space:pre;overflow-x:auto}}
details{{border:1px solid #dde;border-radius:8px;padding:6px 12px;margin:14px 0}} summary{{cursor:pointer;font-weight:bold;font-size:18px}}
.step{{background:#fffbe8;border-right:4px solid #e0b000;padding:6px 10px;border-radius:4px}}
@media (max-width:600px){{body{{font-size:16px;margin:12px auto}} h2{{font-size:20px}} td,th{{padding:4px 5px}}}}
</style></head><body><div>
{body}
</div><p class="ver">סדר מהמודל {VERSION}{label}</p></body></html>
""".encode("utf-8")


# ---------------- the iPad / iPhone page (a bookmark in Safari: one ZIP of the new files, already in folders) ----------------
def ipad_page():
    code = (KIT / "moodle_download.js").read_text(encoding="utf-8")
    small = "\n".join(l for l in (x.lstrip() for x in code.splitlines()) if l and not l.startswith("//"))   # shorter bookmark
    mark = "javascript:" + urllib.parse.quote(small, safe="()*!'-._~:/?=&,;[]{}<>+$@")
    assert urllib.parse.unquote(mark)[len("javascript:"):] == small
    page = f"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><title>סדר מהמודל ל-iPad</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font:18px -apple-system,Arial,sans-serif;max-width:680px;margin:20px auto;padding:0 16px;line-height:1.6;color:#111;background:#fff}}
h1{{color:#0b4f8a;font-size:26px}} h2{{background:#eef4fa;border-radius:8px;padding:6px 12px;font-size:20px;margin-top:28px}}
button{{font-size:20px;font-weight:bold;background:#0b4f8a;color:#fff;border:0;border-radius:12px;padding:14px 22px;width:100%}}
textarea{{width:100%;height:90px;font:12px monospace;direction:ltr;margin-top:10px}} .ok{{color:#127a2e;font-weight:bold}} .muted{{color:#666;font-size:15px}}
li{{margin:6px 0}}
</style></head><body>
<h1>סדר מהמודל ל-iPad ו-iPhone</h1>
<p>כפתור אחד ב-Safari: בתוך המודל לוחצים עליו, ומקבלים <b>קובץ ZIP אחד</b> עם כל הקבצים <b>החדשים</b>, כבר מסודרים בתיקיות לפי קורס וסוג (הרצאות, תרגולים, שיעורי בית, מבחנים). קבצים שכבר ירדו לא יורדים שוב.</p>
<h2>התקנה (פעם אחת, 2 דקות)</h2>
<ol>
<li><button id="copy">העתקת הכפתור</button><div id="msg" class="ok"></div>
<textarea id="code" readonly>{html.escape(mark)}</textarea>
<div class="muted"><b>הכפתור הכחול לא עובד?</b> (כך קורה כשהדף נפתח מתוך אפליקציית קבצים) פותחים באותה תיקייה את הקובץ <b>"הכפתור ל-iPad.txt"</b> ← לחיצה ארוכה על הטקסט ← <b>בחר הכל</b> ← <b>העתק</b>.</div></li>
<li>ב-Safari לוחצים על <b>שיתוף</b> (הריבוע עם החץ) ← <b>הוספת סימנייה</b> ← <b>שמירה</b>.</li>
<li>לוחצים על <b>סימניות</b> (📖) ← <b>עריכה</b> ← לוחצים על הסימנייה החדשה.</li>
<li>בשם כותבים <b>הורד מהמודל</b>. בכתובת: מוחקים הכל ← לחיצה ארוכה ← <b>הדבק</b> ← <b>סיום</b>.</li>
</ol>
<h2>שימוש</h2>
<ol>
<li>נכנסים למודל ב-Safari ומתחברים.</li>
<li>לוחצים על <b>סימניות</b> (📖) ← <b>הורד מהמודל</b>.</li>
<li>בוחרים קורסים ← <b>המשך</b> ← בוחרים קבצים ← <b>הורד</b>. Safari שואל אם להוריד: <b>הורדה</b>.</li>
<li>פותחים את <b>קבצים</b> ← <b>הורדות</b> ← לוחצים על <b>"מודל - קבצים חדשים…zip"</b>. נוצרת תיקייה עם הקבצים, מסודרים לפי קורס וסוג.</li>
</ol>
<p class="muted">הכפתור עובד רק בתוך המודל, דרך ההתחברות שלכם: לא רואה ולא שומר סיסמאות, לא משנה כלום במודל ולא פונה לשום אתר אחר. סרטונים לא יורדים כברירת מחדל (⚙ בחלון). גרסה {VERSION}.</p>
<script>
document.getElementById('copy').onclick = async () => {{
  const t = document.getElementById('code'), m = document.getElementById('msg');
  try {{ await navigator.clipboard.writeText(t.value); m.textContent = '✅ הועתק. עכשיו שלב 2.'; }}
  catch (e) {{ t.focus(); t.select(); m.textContent = 'סמנו את הטקסט בתיבה והעתיקו.'; }}
}};
</script>
</body></html>
""".encode("utf-8")
    return page, mark


# ---------------- layouts ----------------
def program_files(folder, prefix):
    """The no-Python program folder, file by file: {path: (bytes, mode, symlink target or None)}."""
    out = {}
    if folder and folder.is_dir():
        for f in sorted(folder.rglob("*")):
            rel = f"{prefix}/{f.relative_to(folder).as_posix()}"
            if f.is_symlink():
                out[rel] = (b"", 0o120777, os.readlink(f))
            elif f.is_file():
                out[rel] = (f.read_bytes(), 0o100755 if os.access(f, os.X_OK) and sys.platform != "win32" or f.name == "MoodleSorter" else 0o100644, None)
    return out


MAC_BIN = Path(os.environ["SADER_MAC_BIN"]) if os.environ.get("SADER_MAC_BIN") else (KIT / "bin-mac" if sys.platform == "darwin" else None)


def layout(kind):
    """kind: 'win' / 'mac' (a ZIP: launchers at the top) or 'both' (the kit folder: launchers in Windows/ and Mac/).
    Values: (bytes, mode, symlink target or None)."""
    reg = lambda b, x=False: (b, 0o100755 if x else 0o100644, None)
    files = {"התחל כאן.html": reg(guide(kind))}
    for name, (flag, desc) in LAUNCHERS.items():
        if kind in ("win", "both"):
            files[("Windows/" if kind == "both" else "") + name + ".bat"] = reg(bat(flag, desc, "..\מערכת" if kind == "both" else "מערכת"))
        if kind in ("mac", "both"):
            files[("Mac/" if kind == "both" else "") + name + ".command"] = reg(command(flag, desc, "../מערכת" if kind == "both" else "מערכת"), True)
    for f in SYSTEM:
        files[f] = reg((TOP / f).read_bytes())
    for f in sorted(EXT.rglob("*")):                                  # the Chrome extension, for installing it by hand
        if f.is_file():
            files[f"מערכת/תוסף Chrome/{f.relative_to(EXT).as_posix()}"] = reg(f.read_bytes())
    files["מערכת/תוסף Chrome/moodle_download.js"] = reg((KIT / "moodle_download.js").read_bytes())
    if kind in ("win", "both"):
        files.update(program_files(KIT / "bin-win", "מערכת/bin-win"))
    if kind == "mac":
        files.update(program_files(MAC_BIN, "מערכת/bin-mac"))
    files["מערכת/SHA256SUMS.txt"] = reg("".join(f"{hashlib.sha256(b).hexdigest()}  {p}\n" for p, (b, m, link) in files.items()
                                                if link is None).encode("utf-8"))
    return files


own = layout("both")
for stale in ("התקנת כפתור.html",):                                # replaced by the extension in v6.3
    if (TOP / stale).exists():
        (TOP / stale).unlink()
for p, (b, m, link) in own.items():
    if p not in SYSTEM and not p.startswith("מערכת/bin-"):
        (TOP / p).parent.mkdir(parents=True, exist_ok=True)
        (TOP / p).write_bytes(b)

out_dir = TOP / "לשיתוף"; out_dir.mkdir(exist_ok=True)
ipad_len = len(ipad_page()[1])                                       # (the bookmark still builds; iPad users get the Safari extension)
for stale in ("סדר מהמודל ל-iPad.html", "הכפתור ל-iPad.txt"):
    if (out_dir / stale).exists():
        (out_dir / stale).unlink()
keep = set()
for kind, label in (("win", "Windows"), ("mac", "Mac")):
    zip_path = out_dir / f"סדר מהמודל v{VERSION} - {label}.zip"
    if kind == "mac" and MAC_BIN is None:          # the Mac ZIP is built only on the Mac (with its program), never here
        print("Mac ZIP: not built here (run 'בניית גרסת Mac' on a Mac)"); continue
    files = layout(kind)
    for old in out_dir.glob(f"סדר מהמודל v* - {label}.zip"):
        old.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p, (b, mode, link) in files.items():
            info = zipfile.ZipInfo(f"סדר מהמודל/{p}", date_time=(2026, 10, 26, 0, 0, 0))
            info.external_attr = mode << 16                                                 # keeps +x and symlinks for the Mac
            info.flag_bits |= 0x800                                                          # UTF-8 (Hebrew) file names
            info.compress_type = zipfile.ZIP_STORED if link else zipfile.ZIP_DEFLATED
            z.writestr(info, link.encode("utf-8") if link else b)
    print(f"built {zip_path.name} ({len(files)} files, {zip_path.stat().st_size / 1e6:.1f} MB)")
for old in out_dir.glob("סדר מהמודל v*.zip"):
    if f"v{VERSION} - " not in old.name and old not in keep:
        old.unlink()
print(f"v{VERSION}: own layout {len(own)} files; iPad bookmark {ipad_len} chars")
