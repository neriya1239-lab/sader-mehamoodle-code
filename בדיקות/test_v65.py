# Tests for v6.5: self-update (mock GitHub release on 127.0.0.1), manual-sort duplicates, no-access message.
# Usage: python3 -I test_v65.py <patched sort_downloads.py> <real signed Mac ZIP (an older version, e.g. 6.4.1)>
# Everything happens in a temporary folder; nothing is installed, no notifications are shown, the real kit is not touched.
import hashlib, http.server, json, os, re, shutil, subprocess, sys, tempfile, threading, zipfile
from pathlib import Path

SRC, REAL_ZIP = Path(sys.argv[1]), Path(sys.argv[2])
REAL_VER = os.environ.get("TEST_REAL_VER", "6.4.1")
T = Path(tempfile.mkdtemp(prefix="sader65_"))
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1; print(f"PASS {name}")
    else:
        fail += 1; print(f"FAIL {name} {extra}")


# ---- a mock "GitHub": /latest -> release JSON; /files/<name> -> bytes ----
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


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
BASE = f"http://127.0.0.1:{srv.server_port}"
threading.Thread(target=srv.serve_forever, daemon=True).start()


def release(zip_bytes, version=REAL_VER, sha=None, name="sader-mac.zip"):
    FILES.clear()
    FILES[name] = zip_bytes
    FILES["update.json"] = json.dumps({"version": version, "assets": {"mac": {"name": name, "size": len(zip_bytes),
                                       "sha256": sha or hashlib.sha256(zip_bytes).hexdigest()}}}).encode()


def make_kit(name, version="6.0", maintainer=False, settings=None):
    """A kit as extracted from the ZIP (signed 6.4.1 files), with the code under test pretending to be `version`."""
    top = T / name / "סדר מהמודל"
    (T / name).mkdir()
    subprocess.run(["ditto", "-x", "-k", str(REAL_ZIP), str(T / name)], check=True)
    code = re.sub(rb'^VERSION = "[0-9.]+"', f'VERSION = "{version}"'.encode(), SRC.read_bytes(), count=1, flags=re.M)
    (top / "מערכת" / "sort_downloads.py").write_bytes(code)
    (top / "מערכת" / "settings.json").write_text(json.dumps(settings or {"dest_root": "/x/mine", "layout": "{course}"}), encoding="utf-8")
    (top / "my notes.txt").write_text("mine")
    if maintainer:
        (top / "בנייה").mkdir()
    return top


def run(top, *args, env=None, stdin=None):
    e = dict(os.environ, SADER_UPDATE_URL=f"{BASE}/latest", SADER_LOCAL_DIR=str(T / "local"), SADER_LOGS_DIR=str(T / "logs"),
             SADER_NO_NOTIFY="1", SADER_NO_BROWSER="1", SADER_PROC_SCOPE=str(T), **(env or {}))
    r = subprocess.run([sys.executable, "-I", str(top / "מערכת" / "sort_downloads.py"), *args], capture_output=True, text=True,
                       env=e, input=stdin, timeout=600)
    return r.stdout + r.stderr


real = REAL_ZIP.read_bytes()
sha_of = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

# 1. a newer signed release is installed; settings.json and the user's files stay
top = make_kit("k1")
settings_before = (top / "מערכת" / "settings.json").read_text()
release(real)
out = run(top, "--update")
code = (top / "מערכת" / "sort_downloads.py").read_text(encoding="utf-8")
check("update applied", f"עודכן לגרסה {REAL_VER}" in out and f'VERSION = "{REAL_VER}"' in code, out)
check("settings.json kept", (top / "מערכת" / "settings.json").read_text() == settings_before)
check("user file kept", (top / "my notes.txt").read_text() == "mine")
check("no staging left", not (top / ".sader-update").exists())
r = subprocess.run(["codesign", "--verify", "--deep", "--strict", str(top / "התקנת סידור אוטומטי.app")], capture_output=True)
check("launcher still signed after swap", r.returncode == 0, r.stderr)
check("program runs after swap", REAL_VER in subprocess.run([str(top / "מערכת/bin-mac/MoodleSorter.app/Contents/MacOS/MoodleSorter"), "--version"],
                                                             capture_output=True, text=True).stdout)

# 2. wrong SHA-256: nothing changes
top = make_kit("k2")
before = sha_of(top / "מערכת" / "sort_downloads.py")
release(real, sha="0" * 64)
out = run(top, "--update")
check("bad hash rejected", "SHA-256" in out and sha_of(top / "מערכת" / "sort_downloads.py") == before, out)

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

# 6. a ZIP with '..' in a name is refused before anything is written
evil = T / "evil.zip"
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("סדר מהמודל/../../escaped.txt", "x")
top = make_kit("k6")
release(evil.read_bytes())
out = run(top, "--update")
check("path traversal refused", "שם לא תקין" in out and not (T / "escaped.txt").exists() and not (T / "k6" / "escaped.txt").exists(), out)

# 7. a changed (unsigned) launcher inside the update is refused, the kit stays as it was
tam = T / "tampered.zip"
with zipfile.ZipFile(REAL_ZIP) as zi, zipfile.ZipFile(tam, "w", zipfile.ZIP_DEFLATED) as zo:
    for info in zi.infolist():
        data = zi.read(info)
        if info.filename.endswith("סדר הורדות.app/Contents/Info.plist") or info.filename.endswith("סדר הורדות.app/Contents/Info.plist".encode().decode()):
            data = data.replace(b"--ask", b"--apply")
        zo.writestr(info, data)
top = make_kit("k7")
before = sha_of(top / "מערכת" / "sort_downloads.py")
release(tam.read_bytes())
out = run(top, "--update")
check("tampered app refused", "החתימה" in out and sha_of(top / "מערכת" / "sort_downloads.py") == before, out)

# 8. settings.json inside an update ZIP is refused
sj = T / "sj.zip"
with zipfile.ZipFile(sj, "w") as z:
    z.writestr("סדר מהמודל/מערכת/settings.json", "{}")
top = make_kit("k8")
release(sj.read_bytes())
out = run(top, "--update")
check("settings.json in update refused", "settings.json" in out, out)

# 9. no network / no release: a calm message, nothing changes
top = make_kit("k9")
FILES.clear()
out = run(top, "--update")
check("no release = calm", "אין עדכון" in out, out)

# 10. once a day: a second automatic check within 20 hours does nothing (state file)
import importlib.util
spec_env = dict(SADER_LOCAL_DIR=str(T / "local10"), SADER_LOGS_DIR=str(T / "logs"), SADER_NO_NOTIFY="1",
                SADER_UPDATE_URL=f"{BASE}/latest")
os.environ.update(spec_env)
top = make_kit("k10")
sys.argv = [str(top / "מערכת" / "sort_downloads.py")]
spec = importlib.util.spec_from_file_location("sd", top / "מערכת" / "sort_downloads.py")
sd = importlib.util.module_from_spec(spec); spec.loader.exec_module(sd)
FILES.clear()
s = sd.load_settings()
first = sd.check_for_update(s, verbose=True)
FILES["update.json"] = b"{}"                                          # would be read if it checked again
second = sd.check_for_update(s, verbose=True)
check("daily limit", "אין עדכון" in first and second == "", (first, second))

# 11. manual sort: exact duplicates are deleted from Downloads without a second question; a different file is kept
dl, dest = T / "dl", T / "dest"
(dest / "קורס" / "הרצאות").mkdir(parents=True); dl.mkdir()
(dest / "קורס" / "הרצאות" / "a.pdf").write_bytes(b"AAA")
(dl / "a.pdf").write_bytes(b"AAA")                                    # same content as the sorted file -> deleted
(dl / "b.pdf").write_bytes(b"BBB")                                    # new -> moved
(dl / "c (1).pdf").write_bytes(b"CCX")                                # not in the manifest, different -> untouched
man = {"courseId": "1", "courseName": "קורס", "files": [
    {"fileName": "a.pdf", "title": "הרצאה 1", "section": "", "sha256": hashlib.sha256(b"AAA").hexdigest()},
    {"fileName": "b.pdf", "title": "הרצאה 2", "section": "", "sha256": hashlib.sha256(b"BBB").hexdigest()}]}
(dl / "moodle_manifest_1.json").write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")
top = make_kit("k11", version="6.5")
out = run(top, "--ask", "--downloads", str(dl), "--dest", str(dest), stdin="כ\n")
check("manual: new file moved", (dest / "קורס" / "b.pdf").exists(), out)   # (the test kit's layout is {course})
check("manual: exact duplicate deleted, one question", not (dl / "a.pdf").exists() and out.count("(Enter = כן, ל = לא)") == 1, out)
check("manual: other file untouched", (dl / "c (1).pdf").read_bytes() == b"CCX")

# 12. a folder the program may not read: a clear message (not a silent nothing)
locked = T / "locked"; locked.mkdir(); os.chmod(locked, 0)
try:
    out = run(top, "--ask", "--downloads", str(locked), "--dest", str(dest), stdin="")
    check("no-access message", "אין הרשאה לתיקייה" in out and "פרטיות ואבטחה" in out, out)
finally:
    os.chmod(locked, 0o700)
os.environ.update(SADER_NO_NOTIFY="1")
try:
    sd.has_manifest(locked); os.chmod(locked, 0)
    raised = False
    try:
        sd.has_manifest(locked)
    except PermissionError:
        raised = True
    check("has_manifest reports no access", raised)
finally:
    os.chmod(locked, 0o700)

srv.shutdown()
print(f"\n{ok} passed, {fail} failed  ({T})")
if not fail:
    shutil.rmtree(T, ignore_errors=True)
sys.exit(1 if fail else 0)
