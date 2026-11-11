# v6.5 (late): yes/no answers (Enter / Hebrew / English keyboard) and the built-in classification rules.
# Usage: python -I test_v65b.py <sort_downloads.py>   (all in a temp folder; works on Windows and Mac)
import hashlib, importlib.util, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

SRC = Path(sys.argv[1])
T = Path(tempfile.mkdtemp(prefix="sader65b_"))
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1; print(f"PASS {name}")
    else:
        fail += 1; print(f"FAIL {name} {str(extra)[:400]}")


ENV = dict(os.environ, SADER_LOCAL_DIR=str(T / "local"), SADER_LOGS_DIR=str(T / "logs"), SADER_NO_NOTIFY="1", SADER_NO_BROWSER="1",
           SADER_PROC_SCOPE=str(T), SADER_EXT_REGKEY=r"Software\SaderTest\Extensions", SADER_EXT_DIR=str(T / "ext"),
           SADER_STARTUP_DIR=str(T / "startup"), SADER_STARTMENU_DIR=str(T / "startmenu"), SADER_UPDATE_URL="http://127.0.0.1:9/none",
           PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
K = T / "kit" / "מערכת"; K.mkdir(parents=True)
shutil.copy2(SRC, K / "sort_downloads.py")
(K / "settings.json").write_text(json.dumps({"layout": "{course}/{category}"}), encoding="utf-8")


def run(*args, stdin=None, logs=None):
    e = dict(ENV, **({"SADER_LOGS_DIR": str(logs)} if logs else {}))
    r = subprocess.run([sys.executable, "-I", str(K / "sort_downloads.py"), *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=e, input=stdin, timeout=300)
    return r.stdout + r.stderr


def scenario(name):
    dl, dest = T / name / "dl", T / name / "dest"
    dl.mkdir(parents=True); dest.mkdir(parents=True)
    (dl / "a.pdf").write_bytes(b"A-" + name.encode())
    man = {"courseId": "1", "courseName": "קורס", "files": [{"fileName": "a.pdf", "title": "הרצאה 1", "section": "",
                                                             "sha256": hashlib.sha256(b"A-" + name.encode()).hexdigest()}]}
    (dl / "moodle_manifest_1.json").write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
    return dl, dest


# ---- 1. "לבצע?" answers ----
cases = [("Enter", "\n", True), ("כ", "כ\n", True), ("כן", "כן\n", True), ("y", "y\n", True), ("yes", "YES\n", True),
         ("f (כ on English)", "f\n", True), ("ל", "ל\n", False), ("לא", "לא\n", False), ("n", "n\n", False), ("no", "no\n", False),
         ("k (ל on English)", "k\n", False), ("unknown then כ", "maybe\nכ\n", True), ("unknown then ל", "?\nל\n", False),
         ("3 unknown = no", "a\nb\nc\n", False), ("no input (EOF) = no", "", False)]
for i, (label, inp, moved) in enumerate(cases):
    dl, dest = scenario(f"s{i}")
    out = run("--ask", "--downloads", str(dl), "--dest", str(dest), stdin=inp, logs=T / f"logs{i}")
    did = (dest / "קורס" / "הרצאות" / "a.pdf").exists()
    check(f"ask: {label} -> {'moved' if moved else 'nothing'}", did == moved, out[-300:])
check("ask: shows the hint", "(Enter = כן, ל = לא)" in out, out[-200:])
dl, dest = scenario("hint")
out = run("--ask", "--downloads", str(dl), "--dest", str(dest), stdin="maybe\n\n", logs=T / "logsh")
check("ask: unknown answer is explained, then Enter = yes", "לא הבנתי" in out and (dest / "קורס" / "הרצאות" / "a.pdf").exists(), out[-300:])

# ---- 2. undo: Enter = no (explicit yes needed) ----
for label, inp, back in (("Enter", "\n", False), ("k", "k\n", False), ("f", "f\n", True), ("כ", "כ\n", True)):
    logs = T / f"ulogs_{label}"
    dl, dest = scenario(f"u_{label}")
    run("--ask", "--downloads", str(dl), "--dest", str(dest), stdin="\n", logs=logs)
    out = run("--undo", stdin=inp, logs=logs)
    check(f"undo: {label} -> {'back' if back else 'kept'}", (dl / "a.pdf").exists() == back, out[-300:])
check("undo: shows Enter = no", "(כ = כן, Enter = לא)" in out, out[-200:])

# ---- 3. classification (default words, and Neriya's own keywords on top) ----
os.environ.update(SADER_LOCAL_DIR=str(T / "local"), SADER_LOGS_DIR=str(T / "logs"), SADER_NO_NOTIFY="1")
sys.argv = [str(K / "sort_downloads.py")]
spec = importlib.util.spec_from_file_location("sd", K / "sort_downloads.py")
sd = importlib.util.module_from_spec(spec); spec.loader.exec_module(sd)
neriya = {"exams": ["מבחן", "בחינה", "מועד", "exam", "moed", "מרתון"], "syllabus": ["סילבוס", "syllabus", "סגל", "נוסחאות", "formula"],
          "assignments": ["מטלות", "מטלה", "assignment"], "homework": ["תרגיל בית", "שיעורי בית", "hw", "homework", "פתרון תרגיל"],
          "tutorials": ["תרגול", "תרגיל כיתה", "תרגילי כיתה", "class", "cw", "tutorial", "תרגיל"],
          "lectures": ["הרצאה", "הרצאות", "lecture", "מצגת", "פרק", "סיכום שיעור"]}
(K / "settings.json").write_text(json.dumps({"keywords": neriya}, ensure_ascii=False), encoding="utf-8")
s_user = sd.load_settings()
(K / "settings.json").write_text("{}", encoding="utf-8")
s_def = sd.load_settings()
want = {
    # real files (מבוא לתכנות, חדוא 1) and Yuval's list
    "פתרון תרגיל כיתה 3.pdf": "tutorials", "פתרון תרגיל כיתה 1 .pdf": "tutorials",
    "פתרון תרגיל כיתה 2 - if-else_while_casting.pdf": "tutorials", "פתרון תרגיל כיתה 4 - פונקציות.pdf": "tutorials",
    "תרגיל כיתה 2 - if-else_while_casting.pdf": "tutorials", "סיכום - תנאים.pdf": "tutorials", "סיכום - פונקציות.pdf": "tutorials",
    "while סיכום - לולאת.pdf": "tutorials", "char והמשתנה for סיכום - לולאת.pdf": "tutorials",
    "סיכום עבודה עם משתנים קלט ופלט.pdf": "tutorials", "סיכום מור - אינדוקציה וסדרות רקורסיביות (2.11).pdf": "tutorials",
    "תרגול 3 - מבחן השורש, e וסדרות רקורסיביות (סיכום מור, 9.11).pdf": "tutorials",
    "דף תרגילים 3 - מבחן השורש, הסנדוויץ וסדרות רקורסיביות (אינדוקציה).pdf": "tutorials", "דף תרגילים 1.pdf": "tutorials",
    "דף תרגילים 2 - גבול של סדרה (לאה צוקרמן).pdf": "tutorials",
    # math tests are not exams
    "מבחן המנה ומבחן דלמבר.pdf": "other", "דוגמאות למבחן ההשוואה.pdf": "other", "מבחן לייבניץ - טורים.pdf": "other",
    "תרגול 7 - מבחן ד'אלמבר.pdf": "tutorials",
    # lesson summaries stay lectures; the old rules still work
    "סיכום שיעור 4.pdf": "lectures", "סיכום הרצאה 2.pdf": "lectures", "סיכום הרצאות 1-5.pdf": "lectures",
    "פתרון תרגיל 3.pdf": "homework", "תרגיל בית 2.pdf": "homework", "מבחן 2023 מועד א.pdf": "exams",
    "אינפי 1 - 2005 מבחן 1.pdf": "exams", "מבחן השורש - מבחן 2024 מועד ב.pdf": "exams", "הרצאה 5.pdf": "lectures",
    "דף נוסחאות - חדוא 1.pdf": "syllabus", "תרגול 2.pdf": "tutorials",
    # v6.5.1: real files from the course folders that 6.5 sent to "אחר"
    "פתרון הערכה חלופית למילואים - אלגברה לינארית.pdf": "exams",
    "Physics_I_formulae.pdf": "syllabus", "דפי נוסחאות.pdf": "syllabus", "נוסחה לשורשים.pdf": "syllabus",
    "חדוא 1 מדמח - 2009 סתיו.pdf": "exams",
    "מערכות משוואות - דף 1 - פתרון מלא.pdf": "homework", "דטרמיננטות - דף 4.pdf": "homework",
    "מרחבים וקטוריים - תלות ליניארית - דף 2 - תשובות.pdf": "homework",
    "מטריצות - דף 4 (משוחלפת, סימטרית ואנטי-סימטרית).pdf": "homework",
    "גבול ורציפות - גבול פונקציה - דף 3 - פתרון מלא.pdf": "homework", "ערכים עצמיים - דף 2 - תשובות.pdf": "homework",
    # v6.5.1: what must not change
    "דף נוסחאות למבחן.pdf": "exams", "דף תרגילים 4.pdf": "tutorials", "תרגול 3 - דף 2.pdf": "tutorials",
    "דף הסבר.pdf": "other", "קיץ.pdf": "other", "מבחן 2009 סתיו מועד א.pdf": "exams", "הרצאה 3 - אביב 2024.pdf": "lectures",
}
for fn, cat in want.items():
    for label, s in (("default", s_def), ("Neriya", s_user)):
        got = sd.category_key({"fileName": fn, "title": "", "section": ""}, s)
        check(f"{label}: {fn} -> {cat}", got == cat, got)
# the section alone does not make a file "class work" (only its own name/title does)
got = sd.category_key({"fileName": "פתרון תרגיל בית 3.pdf", "title": "", "section": "תרגילי כיתה ושיעורי בית"}, s_def)
check("section 'תרגילי כיתה' does not override the file's own name", got == "homework", got)
check("yes_no helper", sd.yes_no("") is None and sd.yes_no("", True) is True and sd.yes_no(" כן. ") is True and sd.yes_no("K") is False)

print(f"\n{ok} passed, {fail} failed  ({T})")
if not fail:
    shutil.rmtree(T, ignore_errors=True)
sys.exit(1 if fail else 0)
