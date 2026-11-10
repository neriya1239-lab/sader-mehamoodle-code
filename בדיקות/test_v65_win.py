# Windows version of בנייה/tests/test_v65.py (self-update against a mock release on 127.0.0.1, manual-sort duplicates,
# no-access message). Usage:
#   python -I test_v65_win.py <sort_downloads.py under test> <Windows ZIP of version REAL_VER (default 6.5)>
# Differences from the Mac test: zipfile instead of ditto, no codesign checks, the "update" is the Windows ZIP, and an
# extra case: a program file of the kit is in use (a button window open) -> the swap fails, everything is put back.
# All in a temp folder; nothing is installed, no notifications, Chrome/Startup are pointed at test folders.
import hashlib, http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, zipfile
from pathlib import Path

SRC, REAL_ZIP = Path(sys.argv[1]), Path(sys.argv[2])
REAL_VER = os.environ.get("TEST_REAL_VER", "6.5")
CODE_VER = os.environ.get("TEST_CODE_VER", "6.5")          # the VERSION string inside SRC
T = Path(tempfile.mkdtemp(prefix="sader65w_"))
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1; print(f"PASS {name}")
    else:
        fail += 1; print(f"FAIL {name} {extra}")


FILES = {}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/latest":
            body = json.dumps({"tag_name": "x", "assets": [{"name": n, "browser_download_url": f"{BASE}/files/{n}"} for n in FILES]}).encode()
        elif self.path.startswith("/files/") and self.path[7:] in FILES:
            body = FILES[self.path[7:]]
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
BASE = f"http://127.0.0.1:{srv.server_port}"
threading.Thread(target=srv.serve_forever, daemon=True).start()


def release(zip_bytes, version=REAL_VER, sha=None, name="sader-win.zip"):
    FILES.clear()
    FILES[name] = zip_bytes
    FILES["update.json"] = json.dumps({"version": version, "assets": {"win": {"name": name, "size": len(zip_bytes),
                                       "sha256": sha or hashlib.sha256(zip_bytes).hexdigest()}}}).encode()


def make_kit(name, version="6.0", maintainer=False, settings=None):
    top = T / name / "סדר מהמודל"
    (T / name).mkdir()
    with zipfile.ZipFile(REAL_ZIP) as z:
        z.extractall(T / name)
    code = SRC.read_bytes().replace(f'VERSION = "{CODE_VER}"'.encode(), f'VERSION = "{version}"'.encode())
    (top / "מערכת" / "sort_downloads.py").write_bytes(code)
    (top / "מערכת" / "settings.json").write_text(json.dumps(settings or {"dest_root": str(T / "mine"), "layout": "{course}"}), encoding="utf-8")
    (top / "my notes.txt").write_text("mine")
    if maintainer:
        (top / "בנייה").mkdir()
    return top


ENV = dict(SADER_UPDATE_URL=f"{BASE}/latest", SADER_LOCAL_DIR=str(T / "local"), SADER_LOGS_DIR=str(T / "logs"),
           SADER_NO_NOTIFY="1", SADER_NO_BROWSER="1", SADER_PROC_SCOPE=str(T), SADER_EXT_REGKEY=r"Software\SaderTest\Extensions",
           SADER_EXT_DIR=str(T / "ext"), SADER_STARTUP_DIR=str(T / "startup"), SADER_STARTMENU_DIR=str(T / "startmenu"),
           PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run(top, *args, env=None, stdin=None):
    e = dict(os.environ, **dict(ENV, **(env or {})))
    r = subprocess.run([sys.executable, "-I", str(top / "מערכת" / "sort_downloads.py"), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=e, input=stdin, timeout=600)
    return r.stdout + r.stderr


def tree_sig(top):
    """Hashes of every file in the kit (to prove a failed update changed nothing)."""
    return {p.relative_to(top).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in top.rglob("*") if p.is_file()}


real = REAL_ZIP.read_bytes()
sha_of = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

# 1. a newer release is installed; settings.json and the user's files stay
top = make_kit("k1")
settings_before = (top / "מערכת" / "settings.json").read_text()
release(real)
out = run(top, "--update")
code = (top / "מערכת" / "sort_downloads.py").read_text(encoding="utf-8")
check("update applied", f"עודכן לגרסה {REAL_VER}" in out and f'VERSION = "{REAL_VER}"' in code, out)
check("settings.json kept", (top / "מערכת" / "settings.json").read_text() == settings_before)
check("user file kept", (top / "my notes.txt").read_text() == "mine")
check("no staging left", not (top / ".sader-update").exists())
check("launchers present after swap", all((top / f"{n}.bat").exists() for n in ("התקנת סידור אוטומטי", "סדר הורדות", "הגדרות")))
r = subprocess.run([str(top / "מערכת" / "bin-win" / "MoodleSorter.exe"), "--version"], capture_output=True, text=True)
check("program runs after swap", f"MoodleSorter {REAL_VER}" in r.stdout, r.stdout + r.stderr)

# 2. wrong SHA-256: nothing changes
top = make_kit("k2")
before = tree_sig(top)
release(real, sha="0" * 64)
out = run(top, "--update")
check("bad hash rejected", "SHA-256" in out and tree_sig(top) == before, out)

# 3. the maintainer's shared kit (has בנייה) never updates
top = make_kit("k3", maintainer=True)
release(real)
out = run(top, "--update")
check("maintainer kit skipped", "המשותפת" in out and 'VERSION = "6.0"' in (top / "מערכת" / "sort_downloads.py").read_text(encoding="utf-8"), out)

# 4. same version: nothing to do
top = make_kit("k4", version=REAL_VER)
out = run(top, "--update")
check("same version = no update", "כבר מותקנת" in out, out)

# 5. auto_update false
top = make_kit("k5", settings={"auto_update": False})
out = run(top, "--update")
check("auto_update false respected", "כבוי" in out and 'VERSION = "6.0"' in (top / "מערכת" / "sort_downloads.py").read_text(encoding="utf-8"), out)

# 6. '..' in a name is refused before anything is written
evil = T / "evil.zip"
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("סדר מהמודל/../../escaped.txt", "x")
top = make_kit("k6")
release(evil.read_bytes())
out = run(top, "--update")
check("path traversal refused", "שם לא תקין" in out and not (T / "escaped.txt").exists() and not (T / "k6" / "escaped.txt").exists(), out)

# 6b. a backslash / drive name is refused too (Windows-only ways out)
for i, bad in enumerate(("סדר מהמודל\\..\\..\\esc2.txt", "C:/esc3.txt")):
    ev = T / f"evil{i}.zip"
    with zipfile.ZipFile(ev, "w") as z:
        z.writestr(bad, "x")
    top = make_kit(f"k6{i}")
    release(ev.read_bytes())
    out = run(top, "--update")
    check(f"windows path refused ({bad[:12]}...)", "שם לא תקין" in out, out)

# 7 (Windows). a button window is open (its program runs from the kit's bin-win): Windows still lets the folder move,
#    so the update is applied; the old program files stay (hidden) in .sader-update while that window runs, and a later
#    check removes them once it is closed
top = make_kit("k7")
release(real)
busy = subprocess.Popen([str(top / "מערכת" / "bin-win" / "MoodleSorter.exe"), "--setup"], stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, **dict(ENV, SADER_LOCAL_DIR=str(T / "local7b"))))
time.sleep(4)
try:
    alive = busy.poll() is None
    out = run(top, "--update", env={"SADER_LOCAL_DIR": str(T / "local7")})
    check("window open: update applied", alive and f"עודכן לגרסה {REAL_VER}" in out, (alive, out))
    r = subprocess.run([str(top / "מערכת" / "bin-win" / "MoodleSorter.exe"), "--version"], capture_output=True, text=True)
    check("window open: new program runs", f"MoodleSorter {REAL_VER}" in r.stdout, r.stdout)
    left = top / ".sader-update"
    import ctypes
    hidden = left.exists() and bool(ctypes.windll.kernel32.GetFileAttributesW(str(left)) & 0x2)
    check("window open: leftover only while in use, and hidden", left.exists() and hidden and busy.poll() is None, (left.exists(), hidden))
    out2 = run(top, "--update", env={"SADER_LOCAL_DIR": str(T / "local7")})
    check("window open: leftover kept while still running (fresh)", left.exists(), out2)
finally:
    busy.kill(); busy.wait()
time.sleep(1)
os.utime(left, (time.time() - 3600, time.time() - 3600))
out = run(top, "--update", env={"SADER_LOCAL_DIR": str(T / "local7")})
check("window closed: leftover removed by the next check", not left.exists(), out)

# 7b (Windows). a swap that really fails half way (a kit file held open by another program): everything is put back
top = make_kit("k7b")
before = tree_sig(top)
release(real)
victim = sorted((top / "מערכת").iterdir())[-1]                # one of the last items swapped
held = open(victim / "x" if victim.is_dir() else victim, "rb") if not victim.is_dir() else None
if victim.is_dir():
    f0 = next(p for p in victim.rglob("*") if p.is_file()); held = open(f0, "rb")
try:
    out = run(top, "--update", env={"SADER_LOCAL_DIR": str(T / "local7c")})
    check("held file: not updated, retry tomorrow", "לא עודכן" in out and "מחר" in out, (victim.name, out))
    held.close()
    after = tree_sig(top)
    check("held file: kit exactly as before (rollback)", after == before, sorted(set(before.items()) ^ set(after.items()))[:6])
    check("held file: no staging left", not (top / ".sader-update").exists())
    st = json.loads((T / "local7c" / "update_state.json").read_text(encoding="utf-8"))
    check("held file: checked-today recorded (automatic check waits a day)", time.time() - st.get("checked", 0) < 300, st)
finally:
    held.close()
out = run(top, "--update", env={"SADER_LOCAL_DIR": str(T / "local7c")})
check("held file: works once released", f"עודכן לגרסה {REAL_VER}" in out, out)

# 8. settings.json inside an update ZIP is refused
sj = T / "sj.zip"
with zipfile.ZipFile(sj, "w") as z:
    z.writestr("סדר מהמודל/מערכת/settings.json", "{}")
top = make_kit("k8")
release(sj.read_bytes())
out = run(top, "--update")
check("settings.json in update refused", "settings.json" in out, out)

# 8b. a ZIP without the program is refused and changes nothing
np_ = T / "noprog.zip"
with zipfile.ZipFile(np_, "w") as z:
    z.writestr("סדר מהמודל/התקנת סידור אוטומטי.bat", "echo hi")
top = make_kit("k8b")
before = tree_sig(top)
release(np_.read_bytes())
out = run(top, "--update")
check("update without program refused", "חסרה התוכנה" in out and tree_sig(top) == before, out)

# 8c. the release says a newer version but the program inside reports another one: refused
top = make_kit("k8c")
before = tree_sig(top)
release(real, version="9.9")
out = run(top, "--update")
check("program version mismatch refused", "לא רצה כמו שצריך" in out and tree_sig(top) == before, out)

# 9. no release: a calm message
top = make_kit("k9")
FILES.clear()
out = run(top, "--update")
check("no release = calm", "אין עדכון" in out, out)

# 9b. a release with only a Mac asset: "not yet for this computer"
top = make_kit("k9b")
FILES.clear(); FILES["update.json"] = json.dumps({"version": "9.9", "assets": {"mac": {"name": "m.zip", "sha256": "0" * 64}}}).encode()
out = run(top, "--update")
check("mac-only release = not for this computer", "עוד לא זמינה" in out, out)

# 10. once a day
import importlib.util
os.environ.update(SADER_LOCAL_DIR=str(T / "local10"), SADER_LOGS_DIR=str(T / "logs"), SADER_NO_NOTIFY="1",
                  SADER_UPDATE_URL=f"{BASE}/latest")
top = make_kit("k10")
sys.argv = [str(top / "מערכת" / "sort_downloads.py")]
spec = importlib.util.spec_from_file_location("sd", top / "מערכת" / "sort_downloads.py")
sd = importlib.util.module_from_spec(spec); spec.loader.exec_module(sd)
FILES.clear()
s = sd.load_settings()
first = sd.check_for_update(s, verbose=True)
FILES["update.json"] = b"{}"
second = sd.check_for_update(s, verbose=True)
check("daily limit", "אין עדכון" in first and second == "", (first, second))

# 11. manual sort: exact duplicates deleted without a second question; a different file is kept
dl, dest = T / "dl", T / "dest"
(dest / "קורס" / "הרצאות").mkdir(parents=True); dl.mkdir()
(dest / "קורס" / "הרצאות" / "a.pdf").write_bytes(b"AAA")
(dl / "a.pdf").write_bytes(b"AAA")
(dl / "b.pdf").write_bytes(b"BBB")
(dl / "c (1).pdf").write_bytes(b"CCX")
man = {"courseId": "1", "courseName": "קורס", "files": [
    {"fileName": "a.pdf", "title": "הרצאה 1", "section": "", "sha256": hashlib.sha256(b"AAA").hexdigest()},
    {"fileName": "b.pdf", "title": "הרצאה 2", "section": "", "sha256": hashlib.sha256(b"BBB").hexdigest()}]}
(dl / "moodle_manifest_1.json").write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
top = make_kit("k11", version=REAL_VER)
out = run(top, "--ask", "--downloads", str(dl), "--dest", str(dest), stdin="כ\n")
check("manual: new file moved", (dest / "קורס" / "b.pdf").exists(), out)
check("manual: exact duplicate deleted, one question", not (dl / "a.pdf").exists() and out.count("(Enter = כן, ל = לא)") == 1, out)
check("manual: other file untouched", (dl / "c (1).pdf").read_bytes() == b"CCX")

# 12. a folder this program may not read (ACL deny on a test folder only): a clear message
locked = T / "locked"; locked.mkdir()
me = os.environ.get("USERNAME", "")
subprocess.run(["icacls", str(locked), "/deny", f"{me}:(RX)"], capture_output=True)
try:
    out = run(top, "--ask", "--downloads", str(locked), "--dest", str(dest), stdin="")
    check("no-access message", "אין הרשאה לתיקייה" in out, out)
    raised = False
    try:
        sd.has_manifest(locked)
    except PermissionError:
        raised = True
    check("has_manifest reports no access", raised)
finally:
    subprocess.run(["icacls", str(locked), "/remove:d", me], capture_output=True)

srv.shutdown()
print(f"\n{ok} passed, {fail} failed  ({T})")
if not fail:
    shutil.rmtree(T, ignore_errors=True)
sys.exit(1 if fail else 0)
