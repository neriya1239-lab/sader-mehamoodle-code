# sort_downloads.py — "סדר מהמודל" (MoodleSorter). The version is VERSION below.
# Moves files downloaded with the "הורד מהמודל" button from Downloads into your course folders.
# The same code runs as Python and as the no-Python program (MoodleSorter.exe / MoodleSorter.app, built with PyInstaller).
#
# Safe by design:
#   - Moves ONLY files that are listed in a moodle_manifest file, and only into your courses folder.
#   - Every name from the manifest is cleaned, and any destination outside the courses folder is refused.
#   - Never overwrites (a different file with the same name gets " (2)"); never follows shortcuts/symlinks.
#   - Deletes only in Downloads, and only exact copies (same SHA-256) of a file already in the course folder.
#   - No internet access, no admin rights, no passwords, no telemetry.
#   - Every run is logged (in a local folder on this computer, see LOGS), and --undo puts the last run back.
#
# Usage (the launchers in the kit do this for you; or MoodleSorter.exe / python sort_downloads.py with the same flags):
#   python sort_downloads.py              -> shows what it would do (nothing moves)
#   python sort_downloads.py --ask        -> shows the plan, then asks "לבצע? (Enter = כן, ל = לא)"   (the "סדר הורדות" launcher)
#   python sort_downloads.py --apply      -> sorts without asking
#   python sort_downloads.py --undo       -> shows the last run and asks, then puts it back   (the "ביטול סידור אחרון" launcher)
#   python sort_downloads.py --setup      -> settings wizard (the "הגדרות" launcher)
#   python sort_downloads.py --install    -> automatic sorting in the background, also after restart
#   python sort_downloads.py --uninstall  -> removes the automatic sorting
#   python sort_downloads.py --watch      -> the background sorter itself (used by --install)
#   python sort_downloads.py --update     -> check now for a newer version (ZIP installs update themselves once a day)

import argparse, datetime, hashlib, json, os, platform, re, shutil, subprocess, sys, time, unicodedata, urllib.parse
from collections import Counter
from pathlib import Path

VERSION = "6.5.1"
FROZEN = getattr(sys, "frozen", False)             # True in the no-Python build (made with PyInstaller)
for _s in (sys.stdin, sys.stdout, sys.stderr):     # None when running hidden in the background
    if _s and sys.platform == "win32" and not _s.isatty():
        _s.reconfigure(encoding="utf-8")           # pipes and files: UTF-8 (the no-Python build ignores PYTHONUTF8)
if sys.stdout:
    sys.stdout.reconfigure(errors="replace")       # print "?" instead of crashing if the console can't show Hebrew


def _kit_dir():
    """The "מערכת" folder. The background copy of the program runs from a local folder and is told where the kit is."""
    if "--kit" in sys.argv[:-1]:
        return Path(sys.argv[sys.argv.index("--kit") + 1]).resolve()
    if not FROZEN:
        return Path(__file__).resolve().parent
    exe = Path(sys.executable).resolve()             # .../מערכת/bin-win/MoodleSorter.exe or .../bin-mac/MoodleSorter.app/...
    return next((a.parent for a in exe.parents if a.name in ("bin-win", "bin-mac")), exe.parent.parent)


KIT = _kit_dir()
TOP = KIT.parent if KIT.name == "מערכת" else KIT   # the folder the user sees (launchers, "התחל כאן")
BIN = KIT / ("bin-win" if sys.platform == "win32" else "bin-mac")   # the no-Python program, if this kit has one
APP_NAME = "סדר מהמודל"                             # the name people see; files and processes are called MoodleSorter
# inside a bin folder: the program for the launchers (console) and the one for the background (no window)
CLI_NAME, BG_NAME = (("MoodleSorter.exe", "MoodleSorterBg.exe") if sys.platform == "win32" else
                     ("MoodleSorter.app/Contents/MacOS/MoodleSorter",) * 2)


def _local_logs():
    """Logs live on THIS computer, not in the kit folder: the kit is often in iCloud/OneDrive, and writing a log into
    a syncing folder can fail (macOS: "Resource deadlock avoided") or be reverted. SADER_LOGS_DIR is only for tests."""
    if os.environ.get("SADER_LOGS_DIR"):
        return Path(os.environ["SADER_LOGS_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SaderMehamoodle" / "logs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "SaderMehamoodle"
    return Path.home() / ".local" / "state" / "SaderMehamoodle"


def _local_dir():
    """Where the background copy of the program runs from (outside iCloud, so updates can arrive while it runs)."""
    if os.environ.get("SADER_LOCAL_DIR"):
        return Path(os.environ["SADER_LOCAL_DIR"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "SaderMehamoodle"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SaderMehamoodle"
    return Path.home() / ".local" / "share" / "SaderMehamoodle"


LOGS = _local_logs()
LOCAL_BIN = _local_dir() / "bin"
SETTINGS_FILE = KIT / "settings.json"
LOCK_FILE = Path(os.environ.get("SADER_LOCK_FILE") or Path.home() / ".sader_mehamoodle.lock")  # one background sorter per user, even if the kit is copied twice
HOST = re.sub(r"[^A-Za-z0-9_-]", "", platform.node().split(".")[0] or os.environ.get("COMPUTERNAME", ""))[:30] or "pc"   # logs are per computer (iCloud shares the folder)


# ---------------- readable Hebrew on Windows ----------------
# The Windows console shows Hebrew letters left-to-right (reversed). When printing to a real Windows console we
# reorder each line for display; important results are also shown in a normal Windows message box.
def _visual(line):
    if not re.search(r"[֐-׿]", line):
        return line
    mirror = str.maketrans("()[]{}<>", ")(][}{><")
    rev = line[::-1].translate(mirror)
    return re.sub(r"[A-Za-z0-9][A-Za-z0-9_.:/\\\-+%@#=~ ]*[A-Za-z0-9]|[A-Za-z0-9]",
                  lambda m: m.group(0)[::-1].translate(mirror), rev)


class _BidiConsole:
    def __init__(self, stream):
        self.stream, self.buf = stream, ""

    def write(self, text):
        self.buf += text
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.stream.write(_visual(line) + "\n")
        return len(text)

    def flush(self):
        if self.buf:
            self.stream.write(_visual(self.buf)); self.buf = ""
        self.stream.flush()


if sys.platform == "win32" and sys.stdout and sys.stdout.isatty() and "--watch" not in sys.argv:
    sys.stdout = _BidiConsole(sys.stdout)


def msgbox(text, title="סדר מהמודל", yes_no=False):
    """Windows message box with right-to-left Hebrew. Returns True for "כן". Elsewhere: prints and returns None."""
    if sys.platform != "win32" or not isinstance(sys.stdout, _BidiConsole):   # only when shown in a real console window
        return None
    try:
        import ctypes
        flags = 0x00080000 | 0x00100000 | 0x00002000 | 0x00040000 | (0x24 if yes_no else 0x40)  # RIGHT, RTLREADING, TASKMODAL, TOPMOST, icon
        return ctypes.windll.user32.MessageBoxW(None, text, title, flags) == 6
    except Exception:
        return None

# ---------------- default settings (settings.json overrides them; the wizard writes settings.json) ----------------
DEFAULTS = {
    "dest_root": "",                    # "" = the folder "סמסטר א" next to this kit's folder, else ~/Documents/מודל
    "downloads": "",                    # "" = the normal Downloads folder
    "layout": "{course}/{category}",    # also: "{course}", "{semester}/{course}/{category}", "{course}/{section}"
    "filename_style": "original",       # or "clean"
    "find_existing": False,             # look on the computer for files from Moodle the user already has (asked in the wizard)
    "moodle_url": "",                   # the Moodle the installer opens in Chrome ("" = Ariel's student sign-in); question 6
    "auto_update": True,                # a kit from the ZIP updates itself once a day (see check_for_update); false = never
    "category_names": {"lectures": "הרצאות", "tutorials": "תרגולים", "homework": "שיעורי בית", "exams": "מבחנים",
                       "assignments": "מטלות", "syllabus": "סילבוס", "other": "אחר"},
    "course_folders": {},               # part of a Moodle course name -> folder name
    "ignore_for_duplicates": ["משנה שעברה"],
    "keywords": {                       # first match wins, in this order
        "exams": ["מבחן", "מבחנים", "בחינה", "בחינות", "מועד", "exam", "moed", "מרתון"],
        "syllabus": ["סילבוס", "syllabus", "סגל", "נוסחאות", "formula"],
        "assignments": ["מטלות", "מטלה", "assignment"],
        "homework": ["תרגיל בית", "שיעורי בית", "hw", "homework", "פתרון תרגיל"],
        "tutorials": ["תרגול", "תרגיל כיתה", "תרגילי כיתה", "class", "cw", "tutorial", "תרגיל"],
        "lectures": ["הרצאה", "הרצאות", "lecture", "מצגת", "פרק", "שיעור"],   # ("שיעורי בית" is caught earlier)
    },
}


def load_settings():
    s = json.loads(json.dumps(DEFAULTS))
    if SETTINGS_FILE.exists():
        try:
            user = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            for k, v in user.items():
                if k == "keywords" and isinstance(v, dict):
                    for cat, ws in v.items():                  # the user's words first, plus words a newer version added
                        if isinstance(ws, list):
                            s[k][cat] = ws + [w for w in s[k].get(cat, []) if w not in ws]
                elif isinstance(v, dict) and isinstance(s.get(k), dict):
                    s[k].update(v)
                elif k in s:
                    s[k] = v
        except Exception as e:
            print(f"⚠ settings.json פגום ({e}) - משתמש בברירות מחדל. אפשר לתקן בלחיצה על 'הגדרות'.")
    return s


def save_settings(s):
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_path(text):
    """Accept a path pasted from a Mac Terminal (backslash-escaped spaces) or with quotes around it."""
    text = (text or "").strip().strip('"').strip("'")
    if "\\ " in text and "/" in text:
        text = text.replace("\\ ", " ").replace("\\~", "~")
    return os.path.expanduser(text)


def known_folder(guid, fallback):
    """Windows: where Downloads/Documents really are (they can be moved to OneDrive or another drive). Else the fallback."""
    if sys.platform == "win32":
        try:
            import ctypes, uuid
            from ctypes import wintypes
            g = uuid.UUID(guid).bytes_le
            buf = (ctypes.c_ubyte * 16).from_buffer_copy(g)
            out = ctypes.c_wchar_p()
            f = ctypes.windll.shell32.SHGetKnownFolderPath
            f.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
            if f(ctypes.byref(buf), 0, None, ctypes.byref(out)) == 0 and out.value:
                path = Path(out.value)
                ctypes.windll.ole32.CoTaskMemFree(out)
                return path
        except Exception:
            pass
    return fallback


DOWNLOADS_GUID, DOCUMENTS_GUID = "374DE290-123F-4565-9164-39C4925E467B", "FDD39AD0-238F-46AF-ADB4-6C85480369C7"


def default_dest():
    docs = os.environ.get("SADER_DOCUMENTS_DIR")              # (only for tests)
    return (Path(docs) if docs else known_folder(DOCUMENTS_GUID, Path.home() / "Documents")) / "מודל"


def dest_root(s):
    """The courses folder. A relative path counts from the folder the user sees (where 'התחל כאן' is), so one shared
    settings.json (iCloud) works on both Windows and the Mac, e.g. "../סמסטר א"."""
    if s["dest_root"]:
        p = Path(clean_path(s["dest_root"]))
        return p if p.is_absolute() else (TOP / p).resolve()
    near = TOP.parent / "סמסטר א"                      # only settings from before v6.2 have an empty dest_root (the wizard
    return near if SETTINGS_FILE.exists() and near.is_dir() else default_dest()   # now always writes it): no guess for new users


def downloads_dir(s):
    return Path(clean_path(s["downloads"])) if s["downloads"] else known_folder(DOWNLOADS_GUID, Path.home() / "Downloads")


# ---------------- names: everything that comes from a manifest is untrusted ----------------
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(name, fallback="file"):
    """One safe file/folder name: no path parts, no reserved or control characters, not too long."""
    name = unicodedata.normalize("NFC", str(name or ""))
    name = re.sub("[‎‏‪-‮⁦-⁩﻿]", "", name)   # hidden direction marks
    name = re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]', " ", name)   # control chars and characters Windows forbids, incl. / and \
    name = re.sub(r"\.{2,}", " ", name)                      # no ".." tricks
    name = re.sub(r"\s+", " ", name).strip().strip(".").strip()
    if not name or name in {".", ".."}:
        name = fallback
    if name.split(".")[0].upper() in RESERVED:
        name = "_" + name
    if len(name) > 150:                                       # keep the extension when shortening
        stem, ext = os.path.splitext(name)
        name = stem[:150 - len(ext)].rstrip() + ext
    return name


def clean_file_name(name):
    """The optional 'clean' style: decode %xx, drop '+(0)', turn _ and + into spaces."""
    stem, ext = os.path.splitext(urllib.parse.unquote(name))
    stem = re.sub(r"\+?\(\d+\)$", "", stem).replace("_", " ").replace("+", " ")
    return re.sub(r"\s+", " ", stem).strip() + ext


def course_display(name):
    """Folder name from a Moodle course name: drop '(...)', and '-תרגיל' so lecture and tutorial share a folder."""
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(r"\s*-\s*(תרגיל|תרגול|tutorial)\s*$", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name).strip()


def inside(path, root):
    """True if path (after resolving) is inside root - protects against '..' tricks and symlinks."""
    try:
        Path(os.path.realpath(path)).relative_to(Path(os.path.realpath(root)))
        return True
    except ValueError:
        return False


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------- deciding where each file goes ----------------
def course_folder(info, dest, s):
    if info.get("folderName"):                                # chosen in the Moodle button panel
        return safe_name(info["folderName"], "קורס")
    full = str(info.get("courseName", ""))
    for key, folder in s["course_folders"].items():           # the settings list
        if key and key in full:
            return safe_name(folder, "קורס")
    existing = [d.name for d in dest.iterdir() if d.is_dir() and not d.is_symlink()] if dest.is_dir() else []
    for name in sorted(existing, key=len, reverse=True):      # an existing folder whose name is inside the Moodle name
        if len(name) > 2 and name in full:
            return name
    return safe_name(course_display(full), "קורס " + safe_name(str(info.get("courseId", "")), ""))


def _word_in(w, text):
    """English words as whole words ("exam", "exams", "exam2023" - not "examples"); other words anywhere (Hebrew has
    prefixes like ה/ו/ב/ל glued to the word)."""
    if re.fullmatch(r"[a-z]+", w):
        return re.search(rf"(^|[^a-z]){w}s?([^a-z]|$)", text) is not None
    return w in text


# Built-in rules, applied before the keywords of settings.json (v6.5, checked against real course files):
MATH_TESTS = re.compile(r"מבח(?:ן|ני)\s+(?:ה?שורש|ה?מנה|ה?השוואה(?:\s+הגבולי)?|ה?אינטגרל|לי?יבניץ|קושי|ד['׳]?א?למבר|ה?התכנסות)")
CLASS_WORK = ("תרגיל כיתה", "תרגילי כיתה", "דף תרגילים", "דפי תרגילים")
LESSON_SUMMARY = re.compile(r"סיכום\s+(?:ה?שיעור|ה?הרצא)")
# v6.5.1 (from a scan of the real course folders):
ALT_EXAM = ("הערכה חלופית",)                                   # "פתרון הערכה חלופית למילואים" = exams
FORMULA_WORDS = ("formulae", "נוסחא", "נוסחה")                 # go where the settings' "נוסחאות" goes (syllabus by default)
WORKSHEET = re.compile(r"(?<![א-ת])דף\s*\d{1,3}(?!\d)")        # "מערכות משוואות - דף 2 - תשובות" = homework
SEASON_YEAR = (re.compile(r"(?<![א-ת])(?:ה|ב)?(?:סתיו|אביב|חורף|קיץ)(?![א-ת])"), re.compile(r"(?<!\d)(?:19|20)\d\d(?!\d)"))


def category_key(entry, s):
    if entry.get("type") == "assign":
        return "assignments"
    # a convergence test of calculus ("מבחן השורש") is not an exam: it is taken out before the words are matched
    text = MATH_TESTS.sub(" ", " ".join(str(entry.get(k, "")) for k in ("title", "section", "fileName")).lower())
    own = MATH_TESTS.sub(" ", " ".join(str(entry.get(k, "")) for k in ("title", "fileName")).lower())   # without the section
    if any(w in own for w in CLASS_WORK):                     # "פתרון תרגיל כיתה 3", "דף תרגילים 2" = tutorials (not homework)
        return "tutorials"
    if LESSON_SUMMARY.search(own):                            # "סיכום שיעור 4", "סיכום הרצאה" = lectures
        return "lectures"
    if "סיכום" in own:                                        # another summary ("סיכום מור - אינדוקציה") = tutorials
        return "tutorials"
    if any(w in own for w in ALT_EXAM):                        # an alternative assessment is an exam
        return "exams"
    formula_key = next((k for k, ws in s["keywords"].items() if "נוסחאות" in ws), "syllabus")
    for key, words in s["keywords"].items():
        extra = FORMULA_WORDS if key == formula_key else ()
        if any(_word_in(w.lower(), text) for w in (*words, *extra)):
            return key
    if WORKSHEET.search(own):                                  # an exercise sheet ("דף 3"); "דף תרגילים" was caught above
        return "homework"
    # no word matched: a numbered series ("2 - Motion in 1D", "אינפי01") or the lecturer's board ("לוח") = lectures
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", str(entry.get("fileName", "")))
    if (re.match(r"\s*\d{1,2}\s*[-–_.]\s*\S", stem) or re.match(r"\s*\d{1,2}\s*[-–_.]\s*\S", str(entry.get("title", "")))
            or re.fullmatch(r"[^\d\s]{2,}\s?\d{1,3}", stem) or re.search(r"(^|\s)לוח(\s|$)", str(entry.get("section", "")))):
        return "lectures"
    if all(r.search(own) for r in SEASON_YEAR):                # last resort: a term and a year ("2009 סתיו") = an old exam
        return "exams"
    return "other"


def semester_of(info):
    m = re.search(r"(תשפ[א-ת])_([אבג])", str(info.get("courseShortName", "")))
    return f"{m.group(1)} סמסטר {'קיץ' if m.group(2) == 'ג' else m.group(2)}" if m else ""


def target_dir(info, entry, dest, s):
    """Build the folder from the layout template, one safe part at a time."""
    cat = category_key(entry, s)
    values = {"course": course_folder(info, dest, s), "category": s["category_names"].get(cat, cat),
              "section": entry.get("section") or "כללי", "semester": semester_of(info) or "סמסטר"}
    folder = dest
    for part in s["layout"].replace("\\", "/").split("/"):
        part = part.strip()
        if not part:
            continue
        for k, v in values.items():
            part = part.replace("{" + k + "}", str(v))
        folder = folder / safe_name(part, "אחר")
    return folder, cat


def course_root(info, dest, s):
    """The folder that holds one course: the layout up to and including {course} (e.g. <semester>/<course>)."""
    folder = dest
    for part in s["layout"].replace("\\", "/").split("/"):
        part = part.strip()
        if not part:
            continue
        has_course = "{course}" in part
        part = part.replace("{course}", course_folder(info, dest, s)).replace("{semester}", semester_of(info) or "סמסטר")
        if "{" in part:                                        # {category}/{section}: below the course folder
            break
        folder = folder / safe_name(part, "אחר")
        if has_course:
            break
    return folder


# ---------------- files the user already had (downloaded before, maybe renamed) ----------------
STUDY_EXT = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".pps", ".ppsx", ".xls", ".xlsx", ".odt", ".odp", ".rtf", ".txt",
             ".zip", ".rar", ".7z", ".m", ".py", ".c", ".cpp", ".h", ".java", ".ipynb", ".tex", ".csv", ".jpg", ".jpeg", ".png"}
SKIP_DIRS = {"appdata", "library", "node_modules", "$recycle.bin", "system volume information", "windows", "program files",
             "program files (x86)", ".git", ".trash", "applications"}
DESKTOP_GUID = "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"
INDEX_FILE = _local_dir() / "found_index.json"


def find_roots():
    """Where people keep files: Desktop, Documents, iCloud Drive, OneDrive. (SADER_FIND_ROOTS: tests only.)"""
    if os.environ.get("SADER_FIND_ROOTS") is not None:
        return [Path(p) for p in os.environ["SADER_FIND_ROOTS"].split(os.pathsep) if p]
    home = Path.home()
    roots = [known_folder(DESKTOP_GUID, home / "Desktop"), known_folder(DOCUMENTS_GUID, home / "Documents")]
    if sys.platform == "darwin":
        roots.append(home / "Library" / "Mobile Documents" / "com~apple~CloudDocs")
    else:
        roots += [home / "iCloudDrive", *[Path(os.environ[v]) for v in ("OneDrive", "OneDriveConsumer") if os.environ.get(v)]]
    out = []
    for r in roots:
        if r.is_dir() and not any(r == o or inside(r, o) for o in out):
            out.append(r)
    return out


def _cloud_only(st):
    """A file that is only in the cloud (iCloud/OneDrive placeholder): reading it would download it, so skip it."""
    return bool(getattr(st, "st_file_attributes", 0) & (0x1000 | 0x40000 | 0x400000))   # OFFLINE, RECALL_ON_OPEN/ON_DATA_ACCESS


def existing_index(dest, downloads, max_age=6 * 3600):
    """{sha256: path} of study files the user already has outside the courses folder. Kept in a small cache
    (path -> size, mtime, sha), so only new or changed files are read again. Never follows links; skips system folders."""
    try:
        cache = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if time.time() - cache.get("_time", 0) < max_age:
        return {v[2]: k for k, v in cache.get("files", {}).items() if Path(k).is_file()}
    old, new = cache.get("files", {}), {}
    skip = [dest, downloads, TOP, _local_dir()]
    for root in find_roots():
        for here, dirs, files in os.walk(root):
            hp = Path(here)
            if any(hp == x or inside(hp, x) for x in skip):
                dirs[:] = []; continue
            dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in SKIP_DIRS and not (hp / d).is_symlink()]
            for f in files:
                p = hp / f
                if p.suffix.lower() not in STUDY_EXT or f.startswith((".", "~$")):
                    continue
                try:
                    st = p.stat()
                    if p.is_symlink() or _cloud_only(st) or st.st_size == 0 or st.st_size > 300 * 1024 * 1024:
                        continue
                    k = str(p); o = old.get(k)
                    new[k] = o if o and o[0] == st.st_size and o[1] == int(st.st_mtime) else [st.st_size, int(st.st_mtime), sha256_of(p)]
                except OSError:
                    pass
                if len(new) >= 30000:
                    break
    try:
        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        INDEX_FILE.write_text(json.dumps({"_time": time.time(), "files": new}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return {v[2]: k for k, v in new.items()}


def build_plan(downloads, dest, s, only=None):
    """Read the manifests and decide, for every file, what to do. Moves nothing."""
    manifests = sorted(only) if only is not None else sorted(downloads.glob("moodle_manifest_*.json"))
    by_hash = {}                                              # fingerprint -> real file in Downloads (finds Chrome's "(1)" copies too)
    for f in downloads.iterdir():
        if f.is_file() and not f.is_symlink() and not f.name.startswith("moodle_manifest_"):
            try:
                by_hash.setdefault(sha256_of(f), f)
            except OSError:                                   # open in another program right now: skip it this time
                pass
    plan, good, found = [], [], None
    for m in manifests:
        try:
            info = json.loads(m.read_text(encoding="utf-8"))
            files = info["files"]
            assert isinstance(files, list)
        except Exception:
            print(f"⚠ קובץ manifest פגום, מדלג: {m.name}")
            continue
        good.append(m)
        course = course_folder(info, dest, s)
        course_dir = course_root(info, dest, s)
        existing = set()                                     # fingerprints already in this year's course folder
        if course_dir.is_dir() and inside(course_dir, dest):
            for f in course_dir.rglob("*"):
                try:
                    if f.is_file() and not f.is_symlink() and not any(p in s["ignore_for_duplicates"] for p in f.relative_to(course_dir).parts):
                        existing.add(sha256_of(f))
                except OSError:                               # a file that can't be read now (locked): just not counted
                    pass
        taken = set()
        for e in files:
            if not isinstance(e, dict):
                continue
            raw = safe_name(e.get("fileName", ""), "file")
            row = {"course": course, "root": str(course_dir), "file": raw, "manifest": str(m)}
            sha = str(e.get("sha256", ""))
            src = by_hash.get(sha) if re.fullmatch(r"[0-9a-f]{64}", sha) else None
            if src is None:
                row.update(action="missing", why="לא נמצא ב-Downloads"); plan.append(row); continue
            if sha in existing:
                row.update(action="skip", why="כבר קיים בתיקיית הקורס", src=str(src)); plan.append(row); continue
            folder, cat = target_dir(info, e, dest, s)
            name = safe_name(clean_file_name(raw), raw) if s["filename_style"] == "clean" else raw
            mine = None                                       # the same file, already on the computer (maybe renamed)
            if s.get("find_existing"):
                if found is None:
                    found = existing_index(dest, downloads)
                p = Path(found.get(sha, ""))
                try:
                    if found.get(sha) and p.is_file() and not p.is_symlink() and sha256_of(p) == sha:
                        mine = p
                except OSError:
                    pass
            if mine:                                          # move the user's own copy (with their name); the download
                row["dl"] = str(src)                          # is then an exact duplicate and is deleted from Downloads
                src, name = mine, safe_name(mine.name, raw)
            target = folder / name
            n = 2
            while target.exists() or str(target) in taken:      # never overwrite
                target = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"; n += 1
            if not inside(target, dest) or ".." in target.relative_to(dest).parts:
                row.update(action="refused", why="יעד מחוץ לתיקיית הקורסים - נחסם"); plan.append(row); continue
            taken.add(str(target)); existing.add(sha)
            row.update(action="move", folder=str(folder.relative_to(dest)), cat=cat, src=str(src), dst=str(target), sha=sha)
            plan.append(row)
    return good, plan


def show(plan, s):
    other = s["category_names"].get("other", "אחר")
    for course in dict.fromkeys(r["course"] for r in plan):
        rows = [r for r in plan if r["course"] == course]
        print(f"\n=== {course} ===")
        for r in rows:
            if r["action"] == "move":
                print(f"  להעביר:  {Path(r['dst']).name}  ->  {r['folder']}" + ("   ⚠ לא זוהה סוג" if r["cat"] == "other" else ""))
        for r in rows:
            if r["action"] != "move":
                print(f"  לדלג:    {r['file']}  ({r['why']})")
    moves = [r for r in plan if r["action"] == "move"]
    print("\nסיכום:")
    for folder, n in Counter(r["folder"] for r in moves).items():
        print(f"  {folder}: {n}")
    refused = sum(r["action"] == "refused" for r in plan)
    print(f"  להעביר: {len(moves)}   כפולים: {sum(r['action'] == 'skip' for r in plan)}   לא נמצאו: {sum(r['action'] == 'missing' for r in plan)}"
          + (f"   נחסמו: {refused}" if refused else ""))
    n_other = sum(r["cat"] == "other" for r in moves)
    if n_other:
        print(f"\n⚠ {n_other} קבצים לא זוהו ויעברו לתיקייה '{other}'. אפשר להוסיף מילים ב-settings.json (keywords).")
    return moves


def apply(plan, manifests, dest, keep_manifests=True):
    """Move the files and write a log that --undo can use."""
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    log = {"time": stamp, "version": VERSION, "moves": [], "manifests": [], "failed": []}
    for r in plan:
        if r["action"] != "move":
            continue
        src, dst = Path(r["src"]), Path(r["dst"])
        if src.is_symlink() or not src.is_file() or dst.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not inside(dst.parent, dest):                 # last check after the folders exist
                print(f"  נחסם (מחוץ לתיקיית הקורסים): {dst}"); continue
            shutil.move(str(src), str(dst))
        except OSError as e:                                  # e.g. open in another program, or the folder is read-only
            if dst.exists() and src.exists():                 # copied but the original couldn't be removed: undo the copy
                try:
                    dst.unlink()
                except OSError:
                    pass
            log["failed"].append({"file": src.name, "manifest": r["manifest"]})
            print(f"  לא הועבר: {src.name} ({e.strerror or e}). הוא נשאר ב-Downloads.")
            continue
        log["moves"].append({"src": str(src), "dst": str(dst), "sha": r["sha"]})
        if r.get("dl"):                                       # the user's own copy was moved: the download is an exact duplicate
            d = Path(r["dl"])
            try:
                if d.is_file() and not d.is_symlink() and sha256_of(d) == r["sha"]:
                    d.unlink()
            except OSError:
                pass
    unfinished = {f["manifest"] for f in log["failed"]}       # their manifest stays in Downloads, so a later run can retry
    for m in manifests:
        if str(m) in unfinished:
            continue
        if not keep_manifests:
            if m.exists():
                m.unlink()
            continue
        root = next((r["root"] for r in plan if r["manifest"] == str(m)), None)
        if root and m.exists() and inside(root, dest):
            target = Path(root) / safe_name(m.name, "manifest.json")
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target = target.with_name(f"{m.stem}_{stamp.replace(':', '')}{m.suffix}")
                shutil.move(str(m), str(target))
                log["manifests"].append({"src": str(m), "dst": str(target)})
            except OSError:
                pass
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        path = LOGS / f"sort_{HOST}_{stamp.replace(':', '').replace('-', '')}.json"
        path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        for old in LOGS.glob(f"sort_{HOST}_*.json"):                  # keep about 30 days
            if time.time() - old.stat().st_mtime > 30 * 86400:
                old.unlink()
        print(f"\nבוצע: הועברו {len(log['moves'])} קבצים. יומן: {path.name}  (לביטול: --undo)"
              + (f"\n⚠ {len(log['failed'])} קבצים לא הועברו (אולי פתוחים בתוכנה אחרת). אפשר לסגור אותם ולהריץ שוב." if log["failed"] else ""))
    except OSError as e:
        print(f"\nבוצע: הועברו {len(log['moves'])} קבצים. (לא הצלחתי לשמור יומן, אז אין --undo לריצה הזו: {e})")
    return log


def remove_duplicates(plan, downloads, log=None):
    """Delete Downloads copies of files that were skipped because an identical copy is already sorted, and extra copies
    the browser saved twice ("x (1).pdf") of a file that was just sorted. Only exact copies (same SHA-256)."""
    removed = 0
    for r in plan:
        if r["action"] == "skip" and r.get("src"):
            p = Path(r["src"])
            if p.is_file() and not p.is_symlink() and p.parent.resolve() == downloads.resolve():
                p.unlink(); removed += 1
    done = {mv["sha"]: Path(mv["dst"]) for mv in (log or {}).get("moves", []) if Path(mv["dst"]).is_file()}
    if done:
        sizes = {d.stat().st_size for d in done.values()}
        for f in downloads.iterdir():
            try:
                if (f.is_file() and not f.is_symlink() and not f.name.startswith("moodle_manifest_") and f.stat().st_size in sizes
                        and sha256_of(f) in done):
                    f.unlink(); removed += 1
            except OSError:
                pass
    if removed:
        print(f"נמחקו מ-Downloads {removed} עותקים כפולים (יש להם עותק זהה בתיקיית הקורס).")
    return removed


YES_WORDS = ("כ", "כן", "y", "yes", "f")          # "f" / "k" = the keys of כ / ל when the keyboard is on English
NO_WORDS = ("ל", "לא", "n", "no", "k")


def yes_no(answer, default=None):
    """True / False for a typed answer (Hebrew or English keyboard), `default` for Enter, None if not understood."""
    a = str(answer).strip().strip(".!").lower()
    if not a:
        return default
    return True if a in YES_WORDS else False if a in NO_WORDS else None


def confirm(question, summary="", enter_yes=True):
    """Yes/no. In a real Windows console window: a message box (Hebrew shows correctly there). Otherwise a typed answer:
    Enter = yes (enter_yes: sorting, which 'ביטול סידור אחרון' can undo) or Enter = no (the undo itself). An answer it
    does not know is asked again (up to 3 times), never taken as a silent "no"."""
    if isinstance(sys.stdout, _BidiConsole):
        return bool(msgbox(f"{summary}\n\n{question}".strip(), yes_no=True))
    hint = "(Enter = כן, ל = לא)" if enter_yes else "(כ = כן, Enter = לא)"
    try:
        for _ in range(3):
            print(f"\n{question} {hint}: ", end="", flush=True)
            r = yes_no(input(), default=enter_yes)
            if r is not None:
                return r
            print("לא הבנתי. כותבים כ (כן) או ל (לא) ולוחצים Enter.")
    except EOFError:
        pass
    return False


def undo(ask_first=True):
    """Put the files of the last sort back into Downloads. Shows what will move back and asks first (unless --yes)."""
    found = list(LOGS.glob(f"sort_{HOST}_*.json")) if LOGS.is_dir() else []
    logs = [p for p in sorted(found, key=lambda p: p.name) if not p.name.endswith(".undone.json")]
    logs = [p for p in logs if json.loads(p.read_text(encoding="utf-8")).get("moves")]
    if not logs:
        print("אין סידור לבטל.")
        if isinstance(sys.stdout, _BidiConsole):
            msgbox("אין סידור לבטל.")
        return
    last = logs[-1]
    log = json.loads(last.read_text(encoding="utf-8"))
    names = [Path(mv["dst"]).name for mv in log["moves"]]
    when = str(log.get("time", "")).replace("T", " ")[:16]
    summary = (f"הסידור האחרון ({when}) העביר {len(names)} קבצים:\n" + "\n".join(f"  {n}" for n in names[:15])
               + (f"\n  ...ועוד {len(names) - 15}" if len(names) > 15 else ""))
    print(summary)
    if ask_first and not confirm("להחזיר אותם לתיקיית ההורדות?", summary, enter_yes=False):
        print("לא בוצע כלום."); return
    back = kept = 0
    for mv in log["moves"]:
        dst, src = Path(mv["dst"]), Path(mv["src"])
        if dst.is_file() and not dst.is_symlink() and not src.exists() and sha256_of(dst) == mv["sha"]:
            shutil.move(str(dst), str(src)); back += 1
        else:
            kept += 1; print(f"  לא הוחזר (השתנה, נמחק או שיש קובץ במקום המקורי): {dst.name}")
    for mf in log.get("manifests", []):
        if Path(mf["dst"]).exists() and not Path(mf["src"]).exists():
            shutil.move(mf["dst"], mf["src"])
    last.rename(last.with_name(last.stem + ".undone.json"))
    text = f"בוטל: {back} קבצים חזרו ל-Downloads" + (f", {kept} לא הוחזרו" if kept else "") + f"  ({last.name})"
    print(text)
    if isinstance(sys.stdout, _BidiConsole):
        msgbox("✅ " + text)


# ---------------- settings wizard ----------------
def ask(question, default=""):
    try:
        print(f"{question} [{default}]: ", end="", flush=True)   # through print, so Windows shows the Hebrew correctly
        answer = input().strip()
    except EOFError:
        answer = ""
    return answer or default


def setup(s):
    print("\n=== הגדרות 'סדר מהמודל' (Enter = להשאיר את מה שבסוגריים) ===\n")
    legacy = SETTINGS_FILE.exists() and not s["dest_root"] and (TOP.parent / "סמסטר א").is_dir()   # settings from before v6.2: keep what it does now
    docs = dest_root(s) if legacy else default_dest()
    print("1. לאן לשים את הקורסים?")
    print(f"   1) {docs}" + ("   (כמו עכשיו)" if legacy else ""))
    print("   2) תיקייה אחרת (להקליד נתיב, או לגרור תיקייה לחלון)" + (f"   [עכשיו: {dest_root(s)}]" if s["dest_root"] else ""))
    c = ask("   בחירה", "2" if s["dest_root"] else "1")
    if c in ("2", "3"):                                        # ("3" = the same choice in older versions of this wizard)
        while True:
            p = clean_path(ask("   הנתיב", s["dest_root"]))
            try:
                if p:
                    q = dest_root(dict(s, dest_root=p))       # (a relative path counts from the kit folder)
                    q.mkdir(parents=True, exist_ok=True)
                    if q.is_dir():
                        s["dest_root"] = p; break
                print("   ⚠ צריך נתיב של תיקייה.")
            except OSError as e:
                print(f"   ⚠ לא אפשר ליצור את התיקייה ({e}). נסו נתיב אחר.")
    else:
        s["dest_root"] = "" if legacy else str(docs)
    dest_root(s).mkdir(parents=True, exist_ok=True)
    layouts = ["{course}/{category}", "{course}", "{semester}/{course}/{category}", "{course}/{section}"]
    print("\n2. איך לסדר בתוך התיקייה?")
    print("   1) קורס / סוג   (פיזיקה 1 / הרצאות)")
    print("   2) קורס בלבד")
    print("   3) סמסטר / קורס / סוג   (סמסטר א / פיזיקה 1 / הרצאות)")
    print("   4) קורס / הנושא במודל   (פיזיקה 1 / תנועה במימד אחד)")
    c = ask("   בחירה", str(layouts.index(s["layout"]) + 1) if s["layout"] in layouts else "1")
    if c in ("1", "2", "3", "4"):
        s["layout"] = layouts[int(c) - 1]
    if "{category}" in s["layout"] and yes_no(ask("\n3. לשנות את שמות תיקיות הסוג? (כ/ל)", "ל"), False):
        for k, v in list(s["category_names"].items()):
            s["category_names"][k] = safe_name(ask(f"   {v}", v), v)
    print("\n4. שמות הקבצים:  1) כמו במודל   2) מנוקים (בלי _ , %20 ו-(0))")
    s["filename_style"] = "clean" if ask("   בחירה", "2" if s["filename_style"] == "clean" else "1") == "2" else "original"
    print("\n5. קבצים מהמודל שכבר יש לך במחשב (גם אם שינית להם שם): לחפש אותם ולהעביר לתיקיית הקורס, במקום להוריד עותק?")
    print("   (בודק רק בשולחן העבודה, במסמכים וב-iCloud/OneDrive, רק קבצי לימוד, ושום דבר לא יוצא מהמחשב)")
    print("   1) כן   2) לא")
    first = not SETTINGS_FILE.exists()
    s["find_existing"] = ask("   בחירה", "1" if s.get("find_existing") or first else "2") != "2"
    print("\n6. באיזו אוניברסיטה או מכללה המודל שלך?")
    print("   1) אוניברסיטת אריאל   2) אחרת (להקליד את כתובת המודל, למשל moodle.example.ac.il)")
    ariel = not s.get("moodle_url") or s["moodle_url"] == LOGIN_URL
    if ask("   בחירה", "1" if ariel else "2") == "2":
        while True:
            u = ask("   כתובת המודל", "" if ariel else s["moodle_url"]).strip()
            u = u if "://" in u else "https://" + u
            try:
                parts = urllib.parse.urlsplit(u)
            except ValueError:
                parts = None
            if parts and parts.scheme == "https" and parts.hostname and "." in parts.hostname:
                s["moodle_url"] = f"https://{parts.netloc}/my/" if parts.path in ("", "/") else u
                break
            print("   ⚠ צריך כתובת של אתר, למשל moodle.example.ac.il")
        print("   בתוסף ב-Chrome בוחרים את אותה אוניברסיטה (בדף ההגדרות שלו, שנפתח לבד אחרי ההתקנה).")
    else:
        s["moodle_url"] = ""
    save_settings(s)
    print(f"\n✅ נשמר ב-{SETTINGS_FILE.name}. תיקיית הקורסים: {dest_root(s)}")
    print("   קובץ עם אותו שם ותוכן אחר תמיד יישמר עם (2) – שום דבר לא נדרס.")


# ---------------- background mode ----------------
class DailyLog:
    """Everything printed goes to logs/watch_<date>.log (a new file each day, kept ~30 days), and to the console if any."""
    def __init__(self, console):
        self.console, self.day, self.file = console, None, None

    def write(self, text):
        day = datetime.date.today().isoformat()
        if day != self.day:
            try:
                LOGS.mkdir(parents=True, exist_ok=True)
                if self.file:
                    self.file.close()
                self.file, self.day = open(LOGS / f"watch_{HOST}_{day}.log", "a", encoding="utf-8"), day
                for old in LOGS.glob(f"watch_{HOST}_*.log"):
                    if time.time() - old.stat().st_mtime > 30 * 86400:
                        old.unlink()
            except OSError:
                self.file, self.day = None, day
        if not self.file:
            return len(text)
        try:
            self.file.write(text); self.file.flush()
        except OSError:
            pass                                       # a log problem must never stop the sorter
        if self.console:
            try:
                self.console.write(text); self.console.flush()
            except Exception:
                pass

    def flush(self):
        pass


def take_lock(wait=0):
    """One background sorter per user. After a self-restart (wait > 0) the old one may still be exiting, so retry."""
    deadline = time.time() + wait
    while True:
        f = open(LOCK_FILE, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            f.close()
            if time.time() >= deadline:
                return None
            time.sleep(2)
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        (LOGS / f"watch_{HOST}.pid").write_text(str(os.getpid()))
    except OSError:
        pass
    return f


def notify(message, title="סדר מהמודל"):
    if os.environ.get("SADER_NO_NOTIFY"):                     # tests: print instead of showing it on the screen
        print(f"(הודעה: {message})"); return
    try:
        if sys.platform == "darwin":
            subprocess.run(["osascript", "-e", "on run argv\ndisplay notification (item 1 of argv) with title (item 2 of argv)\nend run",
                            message, title], timeout=15)
        elif sys.platform == "win32":
            ps = ("$t=$env:NT_TITLE; $m=$env:NT_MSG; try {"
                  "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
                  "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
                  "$n=$x.GetElementsByTagName('text'); $n.Item(0).AppendChild($x.CreateTextNode($t))>$null; $n.Item(1).AppendChild($x.CreateTextNode($m))>$null;"
                  "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:NT_APP).Show([Windows.UI.Notifications.ToastNotification]::new($x))"
                  "} catch { Add-Type -AssemblyName System.Windows.Forms; $i=New-Object System.Windows.Forms.NotifyIcon;"
                  "$i.Icon=[System.Drawing.SystemIcons]::Information; $i.Visible=$true; $i.ShowBalloonTip(8000,$t,$m,'Info'); Start-Sleep 9; $i.Dispose() }")
            own = (startmenu_dir() / STARTUP_NAME).exists()          # registered by the installer: our own name and icon
            env = dict(os.environ, NT_TITLE=title, NT_MSG=message,
                       NT_APP=APP_ID if own else r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], env=env, creationflags=0x08000000)
    except Exception as e:
        print(f"(הודעה לא הוצגה: {e})")


def be_gentle():
    """Run at low priority, so the background sorter never slows the computer down."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            k.GetCurrentProcess.restype = wintypes.HANDLE                  # a 64-bit handle (the default int would cut it)
            k.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k.SetPriorityClass(k.GetCurrentProcess(), 0x00100000)          # background mode: low disk and memory priority
            k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)          # + BELOW_NORMAL processor priority (in this order)
        else:
            os.nice(10)
    except Exception:
        pass


def code_stamp():
    """Size and time of the program files. When they change (an update arrived through iCloud), the sorter restarts itself."""
    out = []
    for f in (BIN / BG_NAME, KIT / "sort_downloads.py"):
        try:
            st = f.stat(); out.append((st.st_size, int(st.st_mtime)))
        except OSError:
            out.append(None)
    return tuple(out)


def has_manifest(downloads):
    """The cheap check done while idle: only the names in Downloads, nothing is opened. A folder this program is not
    allowed to read raises PermissionError (the caller tells the user how to allow it); other problems = False."""
    try:
        with os.scandir(downloads) as it:
            return any(e.name.startswith("moodle_manifest_") for e in it)
    except PermissionError:
        raise
    except OSError:
        return False


def no_access_text(path):
    """What to do when the system does not let this program read a folder (macOS: Privacy & Security)."""
    path = Path(path)
    if sys.platform == "darwin":
        who = f"{APP_NAME} (MoodleSorter)" if FROZEN else "python3 (או Terminal)"
        return (f"אין הרשאה לתיקייה {path.name}, ולכן הקבצים לא מסתדרים.\n"
                f"לתיקון: הגדרות המערכת > פרטיות ואבטחה > קבצים ותיקיות > {who} > להדליק את {path.name}"
                + (" ואת iCloud Drive" if "Mobile Documents" in str(path) or "iCloud" in str(path) else "") + ".")
    return f"אין הרשאה לתיקייה {path} ({path.name}), ולכן הקבצים לא מסתדרים. אולי תוכנת אבטחה חוסמת אותה."


def folder_problem(path):
    """"" if the folder can be read, else a Hebrew sentence that says what is wrong and how to fix it."""
    try:
        with os.scandir(path) as it:
            next(it, None)
        return ""
    except PermissionError:
        return no_access_text(path)
    except FileNotFoundError:
        return f"התיקייה לא נמצאה: {path}\nאפשר לבחור תיקייה אחרת בלחיצה על 'הגדרות'."
    except OSError as e:
        return f"אין גישה לתיקייה {path} ({e.strerror or e})."


def watch(s):
    """Every 10 seconds (20 when idle for a while): if the button finished downloading a course, sort it, clean exact
    duplicates, notify. Restarts itself when its own program files are updated."""
    sys.stdout = DailyLog(sys.stdout); sys.stderr = sys.stdout
    lock = take_lock(wait=60 if os.environ.get("SADER_RESTART") == "1" else 0)
    if not lock:
        print(f"{time.strftime('%H:%M:%S')} סידור אוטומטי כבר רץ - לא מפעיל עוד אחד."); return
    be_gentle()
    fix_mac_launchers(report=True)
    cmd = runtime_cmd()
    if cmd and not same_program(cmd):                          # e.g. the no-Python program arrived: switch to it
        print(f"{time.strftime('%H:%M:%S')} עובר לגרסה החדשה של התוכנה.")
        write_launch_entry(cmd); restart(lock, cmd)
    cleanup_old_copies(cmd)
    if sys.platform == "win32" and FROZEN and (startup_dir() / STARTUP_NAME).exists() and not (startmenu_dir() / STARTUP_NAME).exists():
        register_app_id(sys.executable)                       # installed before v6.2: give notifications their own name too
    downloads, dest = downloads_dir(s), dest_root(s)
    print(f"\n{time.strftime('%Y-%m-%d %H:%M:%S')} סידור אוטומטי v{VERSION} התחיל ({HOST}{', ללא Python' if FROZEN else ''}). "
          f"הורדות: {downloads}  קורסים: {dest}")
    partial = (".crdownload", ".download", ".part", ".tmp")
    seen, last_new, last_sizes = set(), 0.0, None
    settings_time = SETTINGS_FILE.stat().st_mtime if SETTINGS_FILE.exists() else 0
    stamp, new_stamp, retry_at = code_stamp(), None, 0.0
    last_busy = last_fix = time.time()
    hold_until, last_update, warned = 0.0, 0.0, {}

    def warn(text):                                           # a problem the user must fix: say it, at most every 6 hours
        if time.time() - warned.get(text, 0) > 6 * 3600:
            warned[text] = time.time()
            print(f"{time.strftime('%H:%M:%S')} ⚠ {text}")
            notify(text.split("\n")[0] + (" " + text.split("\n")[1] if "\n" in text else ""))

    while True:
        time.sleep(10 if time.time() - last_busy < 600 else 20)
        try:
            now = time.time()
            if now - last_fix > 600:
                fix_mac_launchers(); last_fix = now
            if now - last_update > 3600:                        # (the check itself runs at most once a day)
                last_update = now
                check_for_update(s)
            st = code_stamp()                                   # an update arrived: wait until it stops changing, then restart
            if st != stamp and now >= retry_at:
                if st == new_stamp:
                    cmd = runtime_cmd()
                    if cmd:
                        print(f"{time.strftime('%H:%M:%S')} התוכנה עודכנה - מפעיל מחדש.")
                        write_launch_entry(cmd); restart(lock, cmd)
                    print(f"{time.strftime('%H:%M:%S')} העדכון עוד לא שלם - ממשיך בגרסה הנוכחית ומנסה שוב בעוד 5 דקות.")
                    retry_at, new_stamp = now + 300, None
                else:
                    new_stamp = st
                continue
            now_time = SETTINGS_FILE.stat().st_mtime if SETTINGS_FILE.exists() else 0
            if now_time != settings_time:                       # 'הגדרות' was used: take the new settings without a restart
                settings_time, s = now_time, load_settings()
                downloads, dest = downloads_dir(s), dest_root(s)
                print(f"{time.strftime('%H:%M:%S')} ההגדרות עודכנו. הורדות: {downloads}  קורסים: {dest}")
            try:
                found = has_manifest(downloads)
            except PermissionError:
                warn(no_access_text(downloads)); continue
            if not found or not dest.is_dir():
                seen.clear(); last_sizes = None; continue
            problem = folder_problem(dest)
            if problem:
                warn(problem); continue
            last_busy = now
            manifests = sorted(downloads.glob("moodle_manifest_*.json"))
            if now < hold_until and not set(manifests) - seen:     # files that couldn't be moved: retry later, not every 10 s
                continue
            if set(manifests) - seen:
                seen |= set(manifests); last_new = time.time()
            sizes = {f.name: f.stat().st_size for f in downloads.iterdir() if f.is_file()}
            busy = any(n.endswith(partial) for n in sizes)
            stable = sizes == last_sizes
            last_sizes = sizes
            if busy or not stable or time.time() - last_new < 15:
                continue
            good, plan = build_plan(downloads, dest, s, only=manifests)
            if any(r["action"] == "missing" for r in plan) and time.time() - last_new < 120:
                continue
            print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} מסדר {len(good)} קורסים ---")
            show(plan, s)
            log = apply(plan, manifests, dest, keep_manifests=False)
            dups = remove_duplicates(plan, downloads, log)
            moved = Counter(r["course"] for r in plan if r["action"] == "move")
            if moved:
                msg = f"סודרו {sum(moved.values())} קבצים: " + ", ".join(f"{c} ({n})" for c, n in moved.items())
            else:
                msg = "אין קבצים חדשים" + (f" ({dups} כפולים נמחקו מההורדות)" if dups else "")
            if any(r.get("cat") == "other" for r in plan if r["action"] == "move"):
                msg += f". יש קבצים בתיקייה '{s['category_names'].get('other', 'אחר')}'"
            if log["failed"]:
                msg += f". {len(log['failed'])} קבצים לא הועברו (אולי פתוחים בתוכנה אחרת) – אנסה שוב בעוד 10 דקות"
                hold_until = time.time() + 600
            notify(msg)
            seen.clear(); last_sizes = None
        except Exception as e:
            print(f"{time.strftime('%H:%M:%S')} שגיאה: {e}"); time.sleep(30)


STARTUP_NAME = "סדר מהמודל.lnk"
APP_ID = "MoodleSorter.SaderMehamoodle"          # Windows: notifications show "סדר מהמודל" (needs the Start menu shortcut)


def startmenu_dir():
    """Windows Start menu programs folder (SADER_STARTMENU_DIR is only for tests)."""
    return Path(os.environ.get("SADER_STARTMENU_DIR") or Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs")


# Windows can show a notification under an app's own name and icon only if a Start menu shortcut carries that app's ID.
# WScript.Shell can't set that property, so this small C# helper (compiled by Windows PowerShell) writes the shortcut.
_SHORTCUT_CS = r"""
using System; using System.Runtime.InteropServices; using System.Runtime.InteropServices.ComTypes; using System.Text;
namespace MoodleSorterLnk {
[ComImport, Guid("00021401-0000-0000-C000-000000000046")] public class ShellLink {}
[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
public interface IShellLinkW {
  void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder f, int c, IntPtr fd, uint fl);
  void GetIDList(out IntPtr p); void SetIDList(IntPtr p);
  void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
  void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string s);
  void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
  void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string s);
  void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c);
  void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string s);
  void GetHotkey(out short h); void SetHotkey(short h); void GetShowCmd(out int c); void SetShowCmd(int c);
  void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder s, int c, out int i);
  void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string s, int i);
  void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string s, uint r); void Resolve(IntPtr h, uint f);
  void SetPath([MarshalAs(UnmanagedType.LPWStr)] string s);
}
[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
public interface IPropertyStore {
  void GetCount(out uint c); void GetAt(uint i, out PropertyKey k);
  void GetValue(ref PropertyKey k, out PropVariant v); void SetValue(ref PropertyKey k, ref PropVariant v); void Commit();
}
[StructLayout(LayoutKind.Sequential, Pack = 4)] public struct PropertyKey { public Guid fmtid; public uint pid; }
[StructLayout(LayoutKind.Explicit)] public struct PropVariant { [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; [FieldOffset(16)] public IntPtr pad; }
public static class Maker {
  public static void Make(string lnk, string target, string args, string icon, string appId, string desc) {
    var link = (IShellLinkW)new ShellLink();
    link.SetPath(target); link.SetArguments(args); link.SetDescription(desc);
    if (icon.Length > 0) link.SetIconLocation(icon, 0);
    var key = new PropertyKey { fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 };   // System.AppUserModel.ID
    var v = new PropVariant { vt = 31, p = Marshal.StringToCoTaskMemUni(appId) };                     // VT_LPWSTR
    var store = (IPropertyStore)link; store.SetValue(ref key, ref v); store.Commit(); Marshal.FreeCoTaskMem(v.p);
    ((IPersistFile)link).Save(lnk, true);
  }
}}
"""


def register_app_id(icon):
    """Start menu shortcut "סדר מהמודל" (opens the kit folder) that carries APP_ID, so notifications show the name and icon."""
    if sys.platform != "win32":
        return False
    try:
        startmenu_dir().mkdir(parents=True, exist_ok=True)
        ps = ("Add-Type -TypeDefinition $env:CS -Language CSharp; "
              "[MoodleSorterLnk.Maker]::Make($env:LNK, $env:TGT, $env:ARGS, $env:ICON, $env:APPID, $env:DESC)")
        env = dict(os.environ, CS=_SHORTCUT_CS, LNK=str(startmenu_dir() / STARTUP_NAME), TGT=str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe"),
                   ARGS=subprocess.list2cmdline([str(TOP)]), ICON=str(icon or ""), APPID=APP_ID, DESC=f"{APP_NAME} – תיקיית הכלי")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, capture_output=True, text=True, timeout=120,
                           creationflags=0x08000000)
        return r.returncode == 0 and (startmenu_dir() / STARTUP_NAME).exists()
    except (OSError, subprocess.SubprocessError):
        return False
MAC_LABEL = "local.moodlesorter"
OLD_MAC_LABELS = ["local.sader-mehamoodle"]                  # up to v6.0


def startup_dir():
    """Windows Startup folder (SADER_STARTUP_DIR is only for tests)."""
    return Path(os.environ.get("SADER_STARTUP_DIR") or Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")


def agents_dir():
    """Mac LaunchAgents folder (SADER_AGENTS_DIR is only for tests)."""
    return Path(os.environ.get("SADER_AGENTS_DIR") or Path.home() / "Library" / "LaunchAgents")


def _python_cmd():
    script = KIT / "sort_downloads.py"
    if FROZEN:                                                 # no Python here: keep running this program
        return [str(Path(sys.executable)), "--watch", "--kit", str(KIT)]
    exe = Path(sys.executable)
    if sys.platform == "win32" and exe.with_name("pythonw.exe").exists():
        exe = exe.with_name("pythonw.exe")                     # no console window
    return [str(exe), str(script), "--watch"]


# Windows: files extracted from a downloaded ZIP carry the "downloaded from the internet" mark, and a normal copy keeps it, so
# the installed local copy could make Windows ask again at every login. When this switch is on, the installed copy is
# written content-only (like a normal installer does), after the user already chose to run the installer (approved 2026-10-26).
INSTALL_WITHOUT_INTERNET_MARK = True


def _copy_for_install(src, dst):
    if INSTALL_WITHOUT_INTERNET_MARK and sys.platform == "win32":
        with open(src, "rb") as a, open(dst, "wb") as b:          # content only (no alternate data streams)
            shutil.copyfileobj(a, b, 1024 * 1024)
        shutil.copystat(src, dst)
        return dst
    return shutil.copy2(src, dst)


def runtime_cmd():
    """The command that runs the background sorter. With the no-Python program: a checked copy of it in a local folder
    (so iCloud can update the kit while it runs). None = the program in the kit is not complete yet (still syncing)."""
    bg = BIN / BG_NAME
    if not bg.is_file():
        return _python_cmd()
    st = bg.stat()
    local = LOCAL_BIN / f"{VERSION}_{st.st_size}_{int(st.st_mtime)}"
    if not (local / ".ok").exists():
        tmp = LOCAL_BIN / (local.name + ".tmp")
        try:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(BIN, tmp, symlinks=True, copy_function=_copy_for_install)
            r = subprocess.run([str(tmp / CLI_NAME), "--version"], capture_output=True, text=True, timeout=60,
                               creationflags=0x08000000 if sys.platform == "win32" else 0)
            if r.returncode != 0 or "MoodleSorter" not in r.stdout:
                raise OSError(f"בדיקת התוכנה נכשלה ({r.returncode})")
            shutil.rmtree(local, ignore_errors=True)
            tmp.rename(local); (local / ".ok").write_text(VERSION)
        except (OSError, subprocess.SubprocessError) as e:
            print(f"{time.strftime('%H:%M:%S')} התוכנה בתיקייה {BIN.name} לא מוכנה ({e}).")
            shutil.rmtree(tmp, ignore_errors=True)
            return None
    return [str(local / BG_NAME), "--watch", "--kit", str(KIT)]


def cleanup_old_copies(cmd):
    """Remove older local copies of the program. Called only by the running sorter, after the previous one has exited."""
    keep = {Path(sys.executable).resolve().parent} if FROZEN else set()
    if cmd:
        keep.add(Path(cmd[0]).resolve().parent)
    if LOCAL_BIN.is_dir():
        for old in LOCAL_BIN.iterdir():
            if old.is_dir() and old.resolve() not in keep:
                shutil.rmtree(old, ignore_errors=True)


def same_program(cmd):
    me = Path(sys.executable if FROZEN else __file__).resolve()      # (the .app's inner program on the Mac)
    return any(Path(c).resolve() == me for c in cmd[:2] if c and not c.startswith("--"))


def write_launch_entry(cmd=None):
    """Create/refresh the 'start with the computer' entry so it runs the background sorter. Safe to repeat."""
    cmd = cmd or runtime_cmd() or _python_cmd()
    if sys.platform == "win32":
        startup_dir().mkdir(parents=True, exist_ok=True)
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK); $s.TargetPath=$env:TGT;"
              "$s.Arguments=$env:ARGS; $s.WorkingDirectory=$env:WDIR; $s.WindowStyle=7; $s.Save()")
        args = subprocess.list2cmdline(cmd[1:])
        env = dict(os.environ, LNK=str(startup_dir() / STARTUP_NAME), TGT=cmd[0], ARGS=args, WDIR=str(Path(cmd[0]).parent))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=env, check=True, capture_output=True,
                       creationflags=0x08000000)
    elif sys.platform == "darwin":
        agents = agents_dir(); agents.mkdir(parents=True, exist_ok=True)
        x = lambda v: str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        prog = "".join(f"<string>{x(c)}</string>" for c in cmd)
        for old in OLD_MAC_LABELS:                            # the job of an older version (it is stopped by the restart/installer)
            (agents / f"{old}.plist").unlink(missing_ok=True)
        (agents / f"{MAC_LABEL}.plist").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
 <key>Label</key><string>{MAC_LABEL}</string>
 <key>ProgramArguments</key><array>{prog}</array>
 <key>WorkingDirectory</key><string>{x(Path(cmd[0]).parent)}</string>
 <key>RunAtLoad</key><true/>
 <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
 <key>ProcessType</key><string>Background</string>
 <key>StandardOutPath</key><string>{x(LOGS / f"launchd_{HOST}.log")}</string>
 <key>StandardErrorPath</key><string>{x(LOGS / f"launchd_{HOST}.log")}</string>
</dict></plist>
""", encoding="utf-8")
    return cmd


def start_detached(cmd, restarting=False):
    if sys.platform == "win32":
        subprocess.Popen(cmd, cwd=str(Path(cmd[0]).parent), close_fds=True,
                         env=dict(os.environ, SADER_RESTART="1") if restarting else None,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,   # fully detached
                         creationflags=0x00000008 | 0x00000200 | 0x08000000)
    elif sys.platform == "darwin":
        plist, job = agents_dir() / f"{MAC_LABEL}.plist", f"gui/{os.getuid()}"
        if restarting:   # reload the job after this process has exited (a helper in its own session survives the bootout)
            olds = " ".join(f'launchctl bootout "$2/{o}" 2>/dev/null;' for o in OLD_MAC_LABELS)
            subprocess.Popen(["/bin/sh", "-c", f'sleep 2; {olds} launchctl bootout "$1" 2>/dev/null; launchctl bootstrap "$2" "$3"',
                              "sh", f"{job}/{MAC_LABEL}", job, str(plist)], start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif subprocess.run(["launchctl", "bootstrap", job, str(plist)], capture_output=True).returncode != 0:
            subprocess.run(["launchctl", "load", "-w", str(plist)], capture_output=True)


def restart(lock, cmd):
    """Hand over to the new program: start it, release the lock, exit (the new one waits for the lock)."""
    start_detached(cmd, restarting=True)
    lock.close()
    sys.exit(0)


def sorter_processes():
    """Background sorters of this user found by their command line (any version, any kit), even without a pid file:
    a pid file can be missing or elsewhere, e.g. when an older sorter was started from another program's context."""
    pat = re.compile(r"(sort_downloads\.py|MoodleSorter(Bg)?(\.exe)?|sader(_bg)?(\.exe)?)[\"']?\s+--watch\b", re.I)
    found = []
    try:
        if sys.platform == "win32":
            ps = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-CimInstance Win32_Process -Filter \"CommandLine like '%--watch%'\" | "
                  "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=60, creationflags=0x08000000).stdout
        else:
            out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, errors="replace", timeout=30).stdout
            out = "\n".join("\t".join(l.strip().split(None, 1)) for l in out.splitlines() if l.strip())
        for line in out.splitlines():
            pid, _, cmdline = line.partition("\t")
            scope = os.environ.get("SADER_PROC_SCOPE")              # tests: only sorters started from the test folder
            if pid.strip().isdigit() and int(pid) != os.getpid() and pat.search(cmdline) and (not scope or scope in cmdline):
                found.append(int(pid))
    except (OSError, subprocess.SubprocessError):
        pass
    return found


def stop_running():
    """Stop this computer's background sorter, if one is running (used before re-installing and by the uninstaller)."""
    pid_files = [LOGS / f"watch_{HOST}.pid"]
    pids = {int(p.read_text().strip()) for p in pid_files if p.exists() and p.read_text().strip().isdigit()}
    pids |= set(sorter_processes())
    pids.discard(os.getpid())
    if sys.platform == "win32":
        for pid in pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
    else:
        if sys.platform == "darwin":                               # first the launchd jobs, so KeepAlive doesn't restart them
            for label in [MAC_LABEL, *OLD_MAC_LABELS]:
                subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"], capture_output=True)
        for pid in pids:
            try:
                os.kill(pid, 15)
            except OSError:
                pass
    for pid_file in pid_files:
        if pid_file.exists():
            pid_file.unlink()
    time.sleep(1)


# ---------------- the Chrome extension (downloads from Moodle by itself every night) ----------------
EXT_ID = "jgmiocjhmgdcodakjlfnigmgapbdfhej"                 # "סדר מהמודל" in the Chrome Web Store
CWS_UPDATE = "https://clients2.google.com/service/update2/crx"
CWS_PAGE = f"https://chromewebstore.google.com/detail/{EXT_ID}"   # its page in the store ("הוספה ל-Chrome" / "הסרה מ-Chrome")
LOGIN_URL = "https://moodlearn.ariel.ac.il/auth/multioauth/login.php?userType=student"   # the default; other Moodles: settings "moodle_url"


def chrome_path():
    """Where Google Chrome is installed, or None (SADER_CHROME is only for tests: "" = not installed)."""
    if "SADER_CHROME" in os.environ:
        return os.environ["SADER_CHROME"] or None
    if sys.platform == "win32":
        try:
            import winreg
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as k:
                        p = winreg.QueryValue(k, None)
                        if p and Path(p).exists():
                            return p
                except OSError:
                    pass
        except ImportError:
            pass
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
            exe = Path(base or "") / "Google" / "Chrome" / "Application" / "chrome.exe"
            if base and exe.exists():
                return str(exe)
    elif sys.platform == "darwin":
        for base in (Path("/Applications"), Path.home() / "Applications"):
            if (base / "Google Chrome.app").exists():
                return str(base / "Google Chrome.app")
        try:                                                   # Chrome somewhere else (e.g. still in Downloads): ask Spotlight
            out = subprocess.run(["mdfind", "kMDItemCFBundleIdentifier == 'com.google.Chrome'"],
                                 capture_output=True, text=True, timeout=15).stdout
            for line in out.splitlines():
                if line.endswith(".app") and Path(line).is_dir():
                    return line
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def _test_without_sandbox():
    """A test run (SADER_PROC_SCOPE) must never touch the real Chrome registration: removing it uninstalls the extension."""
    return bool(os.environ.get("SADER_PROC_SCOPE")) and not (os.environ.get("SADER_EXT_REGKEY") or os.environ.get("SADER_EXT_DIR"))


def _ext_regkey():
    return os.environ.get("SADER_EXT_REGKEY") or rf"Software\Google\Chrome\Extensions\{EXT_ID}"   # (env: tests only)


def _ext_json():
    base = os.environ.get("SADER_EXT_DIR") or Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "External Extensions"
    return Path(base) / f"{EXT_ID}.json"


def register_extension():
    """Tell Chrome to add the extension from the Chrome Web Store, the official way for programs. Chrome then asks the
    user once to turn it on (it never turns on by itself). Per user, no admin rights. True if written.
    Windows only: macOS (26 and later) blocks writing into another app's data folder, Chrome's "External Extensions"
    included ("Operation not permitted", with only a notification), so on a Mac the user adds it from CWS_PAGE."""
    if _test_without_sandbox() or sys.platform == "darwin":
        return False
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _ext_regkey(), 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "update_url", 0, winreg.REG_SZ, CWS_UPDATE)
            return True
    except OSError as e:
        print(f"⚠ לא הצלחתי להוסיף את התוסף ל-Chrome ({e}).")
    return False


def unregister_extension():
    """Undo register_extension. Chrome then removes the extension it added this way the next time it starts.
    (Mac: only a file left by an older version; an extension added from the store is removed in Chrome.)"""
    if _test_without_sandbox():
        return
    try:
        if sys.platform == "win32":
            import winreg
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _ext_regkey())
        elif sys.platform == "darwin" and _ext_json().exists():
            _ext_json().unlink()
    except OSError:
        pass


def open_in_chrome(*urls):
    """Open pages in Chrome (not the default browser), in this order (the last one in front): the user signs in to
    Moodle there once, and Chrome notices the new extension. SADER_NO_BROWSER is only for tests."""
    chrome = chrome_path()
    if not chrome or os.environ.get("SADER_NO_BROWSER"):
        return
    try:
        subprocess.Popen(["open", "-a", chrome, *urls] if sys.platform == "darwin" else [chrome, *urls], close_fds=True)
    except OSError:
        pass


def install(s):
    if not SETTINGS_FILE.exists():
        setup(s)
    LOGS.mkdir(parents=True, exist_ok=True)
    if sys.platform not in ("win32", "darwin"):
        print("ההתקנה האוטומטית נתמכת רק ב-Windows ובמק. אפשר להשתמש ב'סדר הורדות'."); return
    stop_running()                                             # re-installing is always safe
    cmd = write_launch_entry()
    if sys.platform == "win32":                                # notifications under the name "סדר מהמודל" (with its icon)
        register_app_id(cmd[0] if cmd[0].lower().endswith(".exe") and "MoodleSorter" in cmd[0] else "")
    start_detached(cmd)
    chrome = bool(chrome_path())
    ext = chrome and register_extension()
    store = chrome and sys.platform == "darwin"                # Mac: added from its store page (see register_extension)
    text = ("✅ הסידור האוטומטי הותקן ופועל, ויתחיל לבד בכל הפעלה של המחשב.\n\n"
            f"תיקיית הקורסים: {dest_root(s)}\n\n")
    if ext:
        text += ("נשאר רק דבר אחד, ב-Chrome:\n"
                 "1. Chrome יציג 'נוסף תוסף חדש' (סדר מהמודל): לוחצים 'הפעלת התוסף'.\n"
                 "   לא מופיע? סוגרים את Chrome לגמרי ופותחים שוב.\n"
                 "2. בדף ההגדרות של התוסף שנפתח: בוחרים אוניברסיטה ולוחצים 'שמירה'.\n"
                 "3. בדף המודל שנפתח ב-Chrome מתחברים (פעם אחת).\n\n"
                 "מכאן הכל לבד: התוסף מוריד את הקבצים החדשים כל לילה (והפעם הראשונה כמה דקות אחרי ההפעלה), "
                 "והסידור שם אותם בתיקיות, עם הודעה על המסך.\n")
    elif store:
        text += ("נשאר רק דבר אחד, ב-Chrome (נפתחו שתי לשוניות):\n"
                 "1. בלשונית של חנות Chrome (סדר מהמודל): לוחצים 'הוספה ל-Chrome' ואז 'הוספת התוסף'.\n"
                 "   כתוב שם 'הסרה מ-Chrome'? התוסף כבר מותקן, ואין צורך לעשות כלום.\n"
                 "2. בדף ההגדרות של התוסף שנפתח: בוחרים אוניברסיטה ולוחצים 'שמירה'.\n"
                 "3. בלשונית של המודל מתחברים (פעם אחת).\n\n"
                 "מכאן הכל לבד: התוסף מוריד את הקבצים החדשים כל לילה (והפעם הראשונה כמה דקות אחרי ההוספה), "
                 "והסידור שם אותם בתיקיות, עם הודעה על המסך.\n")
    else:
        text += ("⚠ Chrome לא נמצא במחשב, ובלעדיו אין הורדה אוטומטית מהמודל.\n"
                 "מתקינים את Chrome (google.com/chrome) ולוחצים שוב על 'התקנת סידור אוטומטי'.\n")
    text += "\nלשינוי הגדרות: 'הגדרות'. להסרה: 'הסרת סידור אוטומטי'."
    if sys.platform == "darwin":
        who = APP_NAME if "MoodleSorter" in cmd[0] else "python3"
        text += (f"\n\nאם macOS שואל אם לאפשר ל-{who} גישה ל-Downloads, למסמכים או ל-iCloud – לאשר.\n"
                 f"אם נחסם: הגדרות המערכת > פרטיות ואבטחה > קבצים ותיקיות > לאפשר ל-{who}.")
    print(text)
    moodle = s.get("moodle_url") or LOGIN_URL
    if ext:
        open_in_chrome(moodle)
    elif store:
        open_in_chrome(moodle, CWS_PAGE)                       # the store page in front
    msgbox(text)


def uninstall():
    stop_running()
    if sys.platform == "win32":
        for lnk in (startup_dir() / STARTUP_NAME, startmenu_dir() / STARTUP_NAME):
            if lnk.exists():
                lnk.unlink()
    elif sys.platform == "darwin":
        for label in [MAC_LABEL, *OLD_MAC_LABELS]:
            plist = agents_dir() / f"{label}.plist"
            if plist.exists():
                subprocess.run(["launchctl", "unload", str(plist)], capture_output=True); plist.unlink()
    time.sleep(1)
    shutil.rmtree(LOCAL_BIN, ignore_errors=True)                # the local copy of the program (if any)
    unregister_extension()
    mac_store = sys.platform == "darwin" and bool(chrome_path())
    if mac_store:                                              # Mac: the user added it from the store, so they remove it there
        text = ("✅ הסידור האוטומטי הוסר (ההגדרות והקבצים שלך נשארו).\n\n"
                "נשאר להסיר את התוסף מ-Chrome, אחרת הוא ימשיך להוריד מהמודל כל לילה:\n"
                "בלשונית של חנות Chrome שנפתחה (סדר מהמודל) לוחצים 'הסרה מ-Chrome' ואז 'הסרה'.\n"
                "כתוב שם 'הוספה ל-Chrome'? התוסף כבר לא מותקן, ואין צורך לעשות כלום.\n\n"
                "אפשר עדיין לסדר ידנית עם 'סדר הורדות'.")
    else:
        text = ("✅ הסידור האוטומטי הוסר (ההגדרות והקבצים שלך נשארו).\n"
                "התוסף ב-Chrome יוסר לבד בפתיחה הבאה של Chrome (אם התקנתם אותו ידנית: קליק ימני על הסמל ← 'הסרה מ-Chrome').\n"
                "אפשר עדיין לסדר ידנית עם 'סדר הורדות'.")
    print(text)
    if mac_store:
        open_in_chrome(CWS_PAGE)
    msgbox(text)


def kit_commands():
    """This kit's own .command files: at the top, in Mac/ and in בנייה/. Folder names are compared after Unicode
    normalization (macOS may return a different form than the one written on Windows)."""
    norm = lambda n: unicodedata.normalize("NFC", n)
    out = []
    try:
        for e in TOP.iterdir():
            if e.is_file() and e.suffix == ".command":
                out.append(e)
            elif e.is_dir() and not e.is_symlink() and norm(e.name) in ("Mac", norm("בנייה")):
                out += [f for f in e.iterdir() if f.is_file() and f.suffix == ".command"]
    except OSError:
        pass
    return out


def fix_mac_launchers(report=False):
    """Files that arrive through iCloud from Windows have no 'run' permission; give it back, only to this kit's .command files."""
    if sys.platform != "darwin":
        return
    fixed = []
    for f in kit_commands():
        try:
            mode = f.stat().st_mode
            if mode & 0o111 != 0o111:
                f.chmod(mode | 0o111); fixed.append(f.name)               # same as chmod +x
        except OSError:
            pass
    if report or fixed:
        print(f"{time.strftime('%H:%M:%S')} קבצי .command בתיקיית הכלי: {len(kit_commands())}, תוקנו: {len(set(fixed))}"
              + (f" ({', '.join(sorted(set(fixed)))})" if fixed else ""))

# ---------------- updating itself (a kit from the ZIP; v6.5) ----------------
# Once a day the background sorter asks GitHub for the latest release of the public code repository. The release has
# update.json ({"version": "6.6", "assets": {"mac": {"name", "sha256", "size"}, "win": {...}}}) and the same ZIP that is
# shared by hand. If it is newer: download, check the SHA-256 (and on the Mac: Apple signature, notarization and the
# developer's Team ID), check that the new program runs and reports that version, then swap the program files of THIS kit
# (never settings.json, logs or the user's files). The running sorter notices its files changed and restarts itself.
# Not done for the maintainer's kit (it has the folder "בנייה" and is shared through iCloud, so it updates by iCloud),
# for a kit without the no-Python program, or when settings.json has "auto_update": false.
UPDATE_REPO = "neriya1239-lab/sader-mehamoodle-code"
UPDATE_URL = os.environ.get("SADER_UPDATE_URL") or f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"  # (env: tests)
TEAM_ID = "7GZ776UH7S"                                       # the developer's Apple Team ID (Developer ID signature)
UPDATE_STATE = _local_dir() / "update_state.json"
UPDATE_OS = {"darwin": "mac", "win32": "win"}.get(sys.platform)
UPDATE_ROOT = APP_NAME                                       # the folder inside the ZIP
LAUNCHER_EXT = ".app" if sys.platform == "darwin" else ".bat"


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4]) or (0,)


def update_blocked(s):
    """Why this kit does not update itself ("" = it may)."""
    norm = lambda n: unicodedata.normalize("NFC", n)
    if not UPDATE_OS:
        return "מערכת הפעלה בלי עדכון אוטומטי"
    if not s.get("auto_update", True):
        return "העדכון האוטומטי כבוי (auto_update: false)"
    try:
        if any(e.is_dir() and norm(e.name) == norm("בנייה") for e in TOP.iterdir()):
            return "תיקיית הכלי המשותפת (מתעדכנת דרך iCloud)"
    except OSError as e:
        return f"אין גישה לתיקיית הכלי ({e})"
    if norm(KIT.name) != norm("מערכת") or not (TOP / f"התקנת סידור אוטומטי{LAUNCHER_EXT}").exists():
        return "לא תיקייה שחולצה מה-ZIP"
    if not (BIN / CLI_NAME).is_file():
        return "אין כאן את התוכנה (גרסת Python)"
    return ""


def _fetch(url, limit):
    """Bytes from an https address (a local http address only in tests), at most `limit` bytes."""
    import urllib.request
    test = os.environ.get("SADER_UPDATE_URL", "")
    if not (url.startswith("https://") or (test.startswith("http://127.0.0.1") and url.startswith("http://127.0.0.1"))):
        raise OSError(f"כתובת לא מאובטחת: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": f"SaderMehamoodle/{VERSION}", "Accept": "application/octet-stream, application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise OSError("הקובץ גדול מדי")
    return data


def _run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace",
                          creationflags=0x08000000 if sys.platform == "win32" else 0)


def _verify_mac_app(app):
    """An app from the update: signed by this developer (Team ID), not changed since, and notarized by Apple."""
    r = _run(["codesign", "--verify", "--deep", "--strict", str(app)])
    if r.returncode != 0:
        raise OSError(f"החתימה של {app.name} לא תקינה: {r.stderr.strip()[:200]}")
    r = _run(["codesign", "-dv", str(app)])
    if f"TeamIdentifier={TEAM_ID}" not in r.stderr:
        raise OSError(f"{app.name} לא חתום על ידי המפתח של הכלי")
    r = _run(["spctl", "-a", "-t", "exec", "-vv", str(app)])
    if r.returncode != 0 or "Notarized" not in r.stderr:
        raise OSError(f"{app.name} לא מאושר על ידי Apple: {r.stderr.strip()[:200]}")


def _safe_members(zip_path):
    """The ZIP's names: all inside the one top folder, no '..', no absolute paths, nothing called settings.json."""
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
    for n in names:
        parts = n.replace("\\", "/").split("/")
        if n.startswith(("/", "\\")) or ":" in parts[0] or ".." in parts or unicodedata.normalize("NFC", parts[0]) != UPDATE_ROOT:
            raise OSError(f"שם לא תקין בקובץ העדכון: {n}")
        if parts[-1] == "settings.json":
            raise OSError("קובץ העדכון מכיל settings.json")
    return names


def apply_update(zip_bytes, version):
    """Swap this kit's program files for the ones in the update ZIP (already checked by SHA-256). True if done."""
    root = TOP / ".sader-update"                            # next to the kit: same disk, so the swap is a rename
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(exist_ok=True)                               # (Windows: old files of a button window still open may stay here)
    if sys.platform == "win32":
        try:
            import ctypes; ctypes.windll.kernel32.SetFileAttributesW(str(root), 0x2)   # hidden
        except Exception:
            pass
    staging = root / f"u{os.getpid()}_{int(time.time())}"
    staging.mkdir()
    try:
        zp = staging / "update.zip"
        zp.write_bytes(zip_bytes)
        _safe_members(zp)
        out = staging / "new"
        if sys.platform == "darwin":                          # Apple's tool keeps the apps' links and permissions
            r = _run(["ditto", "-x", "-k", str(zp), str(out)])
            if r.returncode != 0:
                raise OSError(f"פתיחת העדכון נכשלה: {r.stderr.strip()[:200]}")
        else:
            import zipfile
            with zipfile.ZipFile(zp) as z:
                z.extractall(out)
        new = next((d for d in out.iterdir() if unicodedata.normalize("NFC", d.name) == UPDATE_ROOT), None)
        if not new or not (new / "מערכת" / BIN.name / CLI_NAME).is_file():
            raise OSError("בעדכון חסרה התוכנה")
        if sys.platform == "darwin":
            for app in [*new.glob("*.app"), new / "מערכת" / BIN.name / "MoodleSorter.app"]:
                _verify_mac_app(app)
        r = _run([str(new / "מערכת" / BIN.name / CLI_NAME), "--version"], timeout=120)
        if f"MoodleSorter {version}" not in r.stdout:
            raise OSError(f"התוכנה החדשה לא רצה כמו שצריך ({r.stdout.strip()[:80]})")
        # what to swap: the top items (launchers, guide) and the items inside מערכת, except settings.json
        pairs = [(n, TOP / n.name) for n in new.iterdir() if n.name != "מערכת"]
        pairs += [(n, KIT / n.name) for n in (new / "מערכת").iterdir() if n.name != "settings.json"]
        old = staging / "old"; old.mkdir()
        done = []
        try:
            for i, (src, dst) in enumerate(pairs):
                keep = old / str(i)
                if dst.exists() or dst.is_symlink():
                    os.rename(dst, keep)
                os.rename(src, dst)
                done.append((dst, keep))
        except OSError:
            for dst, keep in reversed(done):                     # put everything back as it was
                try:
                    shutil.rmtree(dst) if dst.is_dir() and not dst.is_symlink() else dst.unlink()
                except OSError:
                    pass
                if keep.exists() or keep.is_symlink():
                    os.rename(keep, dst)
            src, dst = pairs[len(done)]
            keep = old / str(len(done))
            if (keep.exists() or keep.is_symlink()) and not (dst.exists() or dst.is_symlink()):
                os.rename(keep, dst)
            raise
        return True
    finally:
        shutil.rmtree(root, ignore_errors=True)               # what is still in use is removed by a later check (clean_update_leftovers)


def clean_update_leftovers():
    """Windows lets the swap move a running program's folder, but not delete it: after an update made while a button window
    was open, the old files stay in .sader-update until that window is closed. Remove them then (not while an update runs)."""
    root = TOP / ".sader-update"
    try:
        if root.is_dir() and time.time() - root.stat().st_mtime > 600:
            shutil.rmtree(root, ignore_errors=True)
    except OSError:
        pass


def check_for_update(s, force=False, verbose=False):
    """Once a day (force: now): look for a newer version and install it into this kit. Returns a line for the user,
    or "" when there is nothing to say. Never raises: a failed check is logged and tried again the next day."""
    say = lambda t: (print(f"{time.strftime('%H:%M:%S')} עדכון: {t}") if not verbose else None, t)[1]
    why = update_blocked(s)
    if why:
        return say(f"לא בודק עדכונים: {why}.") if verbose else ""
    clean_update_leftovers()
    try:
        state = json.loads(UPDATE_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if not force and time.time() - state.get("checked", 0) < 20 * 3600:
        return ""
    try:
        UPDATE_STATE.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_STATE.write_text(json.dumps(dict(state, checked=time.time())), encoding="utf-8")
    except OSError:
        pass
    try:
        release = json.loads(_fetch(UPDATE_URL, 2 << 20))
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", []) if isinstance(a, dict)}
        if "update.json" not in assets:
            return say("אין עדכון זמין.") if verbose else ""
        info = json.loads(_fetch(assets["update.json"], 1 << 20))
        version = str(info.get("version", ""))
        if not re.fullmatch(r"\d+(\.\d+){1,3}", version) or version_tuple(version) <= version_tuple(VERSION):
            return say(f"הגרסה הכי חדשה כבר מותקנת ({VERSION}).") if verbose else ""
        asset = (info.get("assets") or {}).get(UPDATE_OS)
        if not isinstance(asset, dict) or asset.get("name") not in assets or not re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256", ""))):
            return say(f"גרסה {version} עוד לא זמינה למחשב הזה.") if verbose else ""
        data = _fetch(assets[asset["name"]], 400 << 20)
        if hashlib.sha256(data).hexdigest() != asset["sha256"] or (asset.get("size") and len(data) != int(asset["size"])):
            raise OSError("טביעת האצבע (SHA-256) של קובץ העדכון לא תואמת - לא הותקן")
        apply_update(data, version)
    except Exception as e:                                    # network, GitHub, a bad file: nothing changed
        return say(f"לא עודכן ({e}). ננסה שוב מחר.")
    text = f"סדר מהמודל עודכן לגרסה {version}"
    print(f"{time.strftime('%H:%M:%S')} {text}")
    notify(text)
    return text


def main():
    fix_mac_launchers()
    p = argparse.ArgumentParser(description="סדר מהמודל - sort Moodle downloads into course folders")
    g = p.add_mutually_exclusive_group()
    for flag in ("apply", "ask", "undo", "setup", "install", "uninstall", "watch", "update"):
        g.add_argument(f"--{flag}", action="store_true")
    p.add_argument("--downloads"); p.add_argument("--dest"); p.add_argument("--kit", help=argparse.SUPPRESS)
    p.add_argument("--version", action="store_true")
    p.add_argument("--yes", action="store_true", help="--undo without asking")
    a = p.parse_args()
    if a.version:
        print(f"MoodleSorter {VERSION}{' (no-Python build)' if FROZEN else ''}"); return
    s = load_settings()
    if a.downloads: s["downloads"] = a.downloads
    if a.dest: s["dest_root"] = a.dest
    if a.undo: return undo(ask_first=not a.yes)
    if a.setup: return setup(s)
    if a.install: return install(s)
    if a.uninstall: return uninstall()
    if a.watch:
        try:
            return watch(s)
        except KeyboardInterrupt:
            print("\nהסידור האוטומטי הופסק."); return
    if a.update:
        return print(check_for_update(s, force=True, verbose=True) or "")
    downloads, dest = downloads_dir(s), dest_root(s)
    if not downloads.is_dir():
        print(f"תיקיית ההורדות לא נמצאה: {downloads}\nאפשר לשנות בלחיצה על 'הגדרות' (או ב-settings.json)."); return
    if not dest.is_dir():
        print(f"תיקיית הקורסים לא נמצאה: {dest}\nלחצו על 'הגדרות' ובחרו תיקייה."); return
    for folder in (downloads, dest):                            # e.g. macOS privacy settings block this program
        problem = folder_problem(folder)
        if problem:
            print("\n⚠ " + problem); msgbox(problem); return
    print(f"הורדות: {downloads}\nקורסים: {dest}")
    manifests, plan = build_plan(downloads, dest, s)
    if not manifests:
        print("\nלא נמצא קובץ moodle_manifest ב-Downloads. קודם מורידים עם הכפתור 'הורד מהמודל'."); return
    moves = show(plan, s)
    dups = sum(r["action"] == "skip" for r in plan)

    def yes(q):
        summary = "\n".join(f"{f}: {n}" for f, n in Counter(r["folder"] for r in moves).items())
        return confirm(q, summary)

    if a.apply:
        apply(plan, manifests, dest)
    elif a.ask:
        if moves and not yes("לבצע?"):
            print("לא בוצע כלום."); return
        log = apply(plan, manifests, dest)
        remove_duplicates(plan, downloads, log)               # only exact copies (same SHA-256) of a sorted file
    elif not moves:
        print("\nאין מה להעביר.")
    else:
        print("\nזו הרצת ניסיון - שום דבר לא הוזז. להעברה: --apply, או לחיצה כפולה על 'סדר הורדות'.")


def run():
    try:
        main()
    except KeyboardInterrupt:
        print("\nהופסק.")
    except Exception as e:                                   # anything unexpected: say what to do, in Hebrew
        text = (f"❌ משהו השתבש: {e}\n\nאפשר לנסות שוב. אם זה חוזר: לשלוח את ההודעה הזו למי שנתן לכם את הכלי.\n"
                f"(יומנים: {LOGS})")
        print(text)
        if "--watch" not in sys.argv:
            msgbox(text)
        sys.exit(1)


if __name__ == "__main__":
    run()
