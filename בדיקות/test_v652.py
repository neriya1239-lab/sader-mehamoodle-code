# v6.5.2: the Mac sorter no longer deletes the copy it runs from; a program file that iCloud makes unreadable does not
# stop the sorting; extra Downloads copies of skipped files are removed; fingerprints only of files that can match by size;
# two Moodle courses in one folder; the Mac restart helper retries.
# Usage: python -I test_v652.py <sort_downloads.py>   (all in a temp folder; Windows, Mac and Linux; nothing is installed)
import errno, hashlib, importlib.util, json, os, shutil, stat, subprocess, sys, tempfile
from pathlib import Path

SRC = Path(sys.argv[1])
T = Path(tempfile.mkdtemp(prefix="sader652_")).resolve()
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1; print(f"PASS {name}")
    else:
        fail += 1; print(f"FAIL {name} {str(extra)[:400]}")


os.environ.update(SADER_LOCAL_DIR=str(T / "local"), SADER_LOGS_DIR=str(T / "logs"), SADER_NO_NOTIFY="1", SADER_NO_BROWSER="1",
                  SADER_PROC_SCOPE=str(T), SADER_EXT_DIR=str(T / "ext"), SADER_EXT_REGKEY=r"Software\SaderTest\Extensions",
                  SADER_STARTUP_DIR=str(T / "startup"), SADER_STARTMENU_DIR=str(T / "startmenu"), SADER_AGENTS_DIR=str(T / "agents"),
                  SADER_UPDATE_URL="http://127.0.0.1:9/none", SADER_LOCK_FILE=str(T / "lock"))
K = T / "kit" / "מערכת"; K.mkdir(parents=True)
shutil.copy2(SRC, K / "sort_downloads.py")
(K / "settings.json").write_text(json.dumps({"layout": "{course}/{category}"}), encoding="utf-8")
spec = importlib.util.spec_from_file_location("sd", K / "sort_downloads.py")
sd = importlib.util.module_from_spec(spec); spec.loader.exec_module(sd)
S = sd.load_settings()
check("version is 6.5.2", sd.VERSION == "6.5.2", sd.VERSION)

# ---- 1. cleanup_old_copies keeps the copy the sorter runs from (Mac layout and Windows layout) ----
real_exe, real_frozen, real_bin = sys.executable, sd.FROZEN, sd.LOCAL_BIN
for label, inner in (("Mac", "MoodleSorter.app/Contents/MacOS/MoodleSorter"), ("Windows", "MoodleSorterBg.exe")):
    lb = T / f"bin_{label}"
    mine, new, old = lb / "6.5.2_100_1", lb / "6.5.2_200_2", lb / "6.4_50_0"
    for d in (mine, new, old):
        (d / inner).parent.mkdir(parents=True); (d / inner).write_text("x"); (d / ".ok").write_text("v")
    (lb / "note.txt").write_text("a file, not a copy")
    sd.LOCAL_BIN, sd.FROZEN, sys.executable = lb, True, str(mine / inner)
    try:
        cmd = [str(mine / inner), "--watch", "--kit", str(K)]
        check(f"{label}: the command is this program", sd.same_program(cmd))
        sd.cleanup_old_copies(cmd)
        left = sorted(p.name for p in lb.iterdir())
        check(f"{label}: own copy kept, older copies removed", left == ["6.5.2_100_1", "note.txt"] and (mine / inner).exists(), left)
        for d in (new, old):
            (d / inner).parent.mkdir(parents=True); (d / inner).write_text("x")
        sd.cleanup_old_copies([str(new / inner), "--watch"])      # about to switch to a newer copy: both stay
        left = sorted(p.name for p in lb.iterdir())
        check(f"{label}: own copy and the next copy kept", left == ["6.5.2_100_1", "6.5.2_200_2", "note.txt"], left)
        sd.cleanup_old_copies(None)                                # the kit is not ready: own copy still stays
        check(f"{label}: no command -> own copy kept", (mine / inner).exists() and not new.exists())
    finally:
        sd.LOCAL_BIN, sd.FROZEN, sys.executable = real_bin, real_frozen, real_exe
lb = T / "bin_py"; (lb / "6.4_1_1" / "x").mkdir(parents=True)
sd.LOCAL_BIN = lb
try:
    sd.cleanup_old_copies([sys.executable, str(K / "sort_downloads.py"), "--watch"])   # Python mode: no local copy is needed
    check("Python mode: old local copies removed, nothing else touched", not (lb / "6.4_1_1").exists() and K.exists())
finally:
    sd.LOCAL_BIN = real_bin

# ---- 2. runtime_cmd: a program file that cannot be read right now = "not ready" (no exception) ----
real_is_file = Path.is_file


def deadlock(self, *a, **k):
    if self.name in ("MoodleSorter", "MoodleSorterBg.exe"):
        raise OSError(errno.EDEADLK, "Resource deadlock avoided", str(self))
    return real_is_file(self, *a, **k)


Path.is_file = deadlock
try:
    got = "raised"
    try:
        got = sd.runtime_cmd()
    except OSError as e:
        got = f"raised {e}"
    check("runtime_cmd: unreadable program file -> None", got is None, got)
finally:
    Path.is_file = real_is_file
check("runtime_cmd: no program in the kit -> the Python command", (sd.runtime_cmd() or [""])[-1] == "--watch" and "sort_downloads.py" in " ".join(sd.runtime_cmd()))


# ---- helpers for the sorting scenarios ----
def sha(b):
    return hashlib.sha256(b).hexdigest()


def entry(name, data, title="הרצאה 1", size=True):
    e = {"fileName": name, "title": title, "section": "", "sha256": sha(data)}
    if size:
        e["size"] = len(data)
    return e


def manifest(dl, cid, course, entries):
    (dl / f"moodle_manifest_{cid}.json").write_text(json.dumps({"courseId": str(cid), "courseName": course, "files": entries},
                                                               ensure_ascii=False), encoding="utf-8")


def scenario(name):
    dl, dest = T / name / "dl", T / name / "dest"
    dl.mkdir(parents=True); dest.mkdir(parents=True)
    return dl, dest


hashed = []
real_sha = sd.sha256_of
sd.sha256_of = lambda p: (hashed.append(Path(p).name), real_sha(p))[1]

# ---- 3. extra copies of skipped files are removed from Downloads; other files stay ----
dl, dest = scenario("dups")
A, B, C = b"AAAA-lecture", b"BBBB-tutorial!", b"CCCC-private-file"
(dest / "קורס" / "הרצאות").mkdir(parents=True); (dest / "קורס" / "הרצאות" / "a.pdf").write_bytes(A)      # already sorted
for n in ("a.pdf", "a (1).pdf", "a (2).pdf"):
    (dl / n).write_bytes(A)
for n in ("b.pdf", "b (1).pdf"):
    (dl / n).write_bytes(B)
(dl / "mine.pdf").write_bytes(C); (dl / "same-size.pdf").write_bytes(b"X" * len(A))
manifest(dl, 1, "קורס", [entry("a.pdf", A), entry("b.pdf", B, "תרגול 1")])
good, plan = sd.build_plan(dl, dest, S)
acts = sorted((r["file"], r["action"]) for r in plan)
check("dups: a is skipped, b is moved", acts == [("a.pdf", "skip"), ("b.pdf", "move")], acts)
check("dups: the skip row carries the fingerprint", all(r.get("sha") == sha(A) for r in plan if r["action"] == "skip"))
log = sd.apply(plan, good, dest, keep_manifests=False)
n = sd.remove_duplicates(plan, dl, log)
left = sorted(p.name for p in dl.iterdir())
check("dups: all 3 copies of the skipped file and the extra copy of the moved file are gone", n == 4 and left == ["mine.pdf", "same-size.pdf"], (n, left))
check("dups: the sorted files are in place", (dest / "קורס" / "הרצאות" / "a.pdf").read_bytes() == A
      and (dest / "קורס" / "תרגולים" / "b.pdf").read_bytes() == B)

# ---- 4. fingerprints only of files that can match by size ----
dl, dest = scenario("sizes")
(dest / "קורס" / "הרצאות").mkdir(parents=True)
(dest / "קורס" / "הרצאות" / "big-other.pdf").write_bytes(b"Z" * 5000)
(dest / "קורס" / "הרצאות" / "old.pdf").write_bytes(A)
(dl / "a.pdf").write_bytes(A); (dl / "movie.mp4").write_bytes(b"M" * 9000); (dl / "new.pdf").write_bytes(B)
manifest(dl, 1, "קורס", [entry("a.pdf", A), entry("new.pdf", B, "תרגול 2")])
hashed.clear()
good, plan = sd.build_plan(dl, dest, S)
check("sizes: files of other sizes are not read", sorted(hashed) == ["a.pdf", "new.pdf", "old.pdf"], sorted(hashed))
check("sizes: same result (a skipped, new moved)", sorted((r["file"], r["action"]) for r in plan) == [("a.pdf", "skip"), ("new.pdf", "move")])
manifest(dl, 1, "קורס", [entry("a.pdf", A, size=False), entry("new.pdf", B, "תרגול 2")])
hashed.clear()
good, plan = sd.build_plan(dl, dest, S)
check("sizes: a manifest without sizes -> every file is read, as before",
      sorted(hashed) == ["a.pdf", "big-other.pdf", "movie.mp4", "new.pdf", "old.pdf"], sorted(hashed))
check("sizes: and the result is the same", sorted((r["file"], r["action"]) for r in plan) == [("a.pdf", "skip"), ("new.pdf", "move")])
manifest(dl, 1, "קורס", [entry("a.pdf", A), {"fileName": "new.pdf", "title": "x", "section": "", "sha256": sha(B), "size": True}])
hashed.clear(); sd.build_plan(dl, dest, S)
check("sizes: a size that is not a number counts as missing", "movie.mp4" in hashed, hashed)

# ---- 5. two Moodle courses that share one folder (lecture + tutorial) ----
dl, dest = scenario("shared")
S2 = dict(S, course_folders={"אינפי": "חדוא 1"})
D1, D2 = b"syllabus of the lecture", b"syllabus of the tutorial!!"
(dl / "common.pdf").write_bytes(A); (dl / "סילבוס.pdf").write_bytes(D1); (dl / "סילבוס (1).pdf").write_bytes(D2)
manifest(dl, 1, "אינפי 1", [entry("common.pdf", A), entry("סילבוס.pdf", D1, "סילבוס")])
manifest(dl, 2, "אינפי 1-תרגיל", [entry("common.pdf", A), entry("סילבוס.pdf", D2, "סילבוס")])
hashed.clear()
good, plan = sd.build_plan(dl, dest, S2)
moves = [r for r in plan if r["action"] == "move"]
check("shared: the same file in both courses is moved once and skipped once",
      sum(r["file"] == "common.pdf" and r["action"] == "move" for r in plan) == 1
      and sum(r["file"] == "common.pdf" and r["action"] == "skip" for r in plan) == 1, [(r["file"], r["action"]) for r in plan])
check("shared: same name, different content -> two different targets", len({r["dst"] for r in moves}) == len(moves) == 3,
      [r.get("dst") for r in moves])
log = sd.apply(plan, good, dest, keep_manifests=False)
sd.remove_duplicates(plan, dl, log)
got = sorted(p.name for p in (dest / "חדוא 1").rglob("*") if p.is_file())
check("shared: all three files arrive, nothing left in Downloads",
      got == ["common.pdf", "סילבוס (2).pdf", "סילבוס.pdf"] and not any(dl.iterdir()) and not log["failed"], (got, [p.name for p in dl.iterdir()]))
sd.sha256_of = real_sha

# ---- 6. manual sort says it is checking (the silent minutes), and still works end to end ----
dl, dest = scenario("manual")
(dl / "a.pdf").write_bytes(A); (dl / "a (1).pdf").write_bytes(A)
manifest(dl, 1, "קורס", [entry("a.pdf", A)])
r = subprocess.run([sys.executable, "-I", str(K / "sort_downloads.py"), "--ask", "--downloads", str(dl), "--dest", str(dest)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", input="\n", timeout=300,
                   env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
out = r.stdout + r.stderr
check("manual: progress line before the check", "זה יכול לקחת כמה דקות" in out and out.index("קורסים:") < out.index("כמה דקות") < out.index("סיכום"), out[-400:])
check("manual: sorted, and the extra copy removed", (dest / "קורס" / "הרצאות" / "a.pdf").exists() and not any(dl.iterdir()), out[-400:])

# ---- 7. the Mac restart helper: bootstrap is retried; a job that is still loaded is started ----
if os.name == "posix":
    fake = T / "fakebin"; fake.mkdir()
    (fake / "launchctl").write_text('#!/bin/sh\necho "$@" >>"$CALLS"\ncase "$1" in\n bootstrap) n=$(cat "$COUNT" 2>/dev/null || echo 0); n=$((n+1)); echo $n >"$COUNT";'
                                    ' if [ $n -le "$FAILS" ]; then echo "Bootstrap failed: 5: Input/output error" >&2; exit 5; fi;;\n'
                                    ' kickstart) exit "${KICK:-0}";;\nesac\nexit 0\n')
    (fake / "sleep").write_text("#!/bin/sh\nexit 0\n")           # no real waiting in the test
    for f in fake.iterdir():
        f.chmod(f.stat().st_mode | stat.S_IEXEC)

    def helper(fails, kick=0):
        calls, count, log = T / f"calls{fails}{kick}", T / f"count{fails}{kick}", T / f"restart{fails}{kick}.log"
        env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}", CALLS=str(calls), COUNT=str(count), FAILS=str(fails), KICK=str(kick))
        r = subprocess.run(["/bin/sh", "-c", sd.MAC_RESTART_SH, "sh", "gui/501/local.moodlesorter", "gui/501", "/x/a.plist", str(log)],
                           env=env, capture_output=True, text=True, timeout=60)
        return r.returncode, calls.read_text().splitlines(), (log.read_text() if log.exists() else "")

    rc, calls, log = helper(0)
    check("restart: bootout of both jobs, then one bootstrap", calls == ["bootout gui/501/local.sader-mehamoodle", "bootout gui/501/local.moodlesorter",
                                                                          "bootstrap gui/501 /x/a.plist"] and rc == 0 and log == "", calls)
    rc, calls, log = helper(3)
    check("restart: bootstrap fails 3 times, the 4th succeeds", sum(c.startswith("bootstrap") for c in calls) == 4 and rc == 0
          and not any(c.startswith("kickstart") for c in calls) and log.count("Input/output error") == 3, (rc, calls, log))
    rc, calls, log = helper(99)
    check("restart: bootstrap never succeeds -> 15 tries, then the loaded job is started", sum(c.startswith("bootstrap") for c in calls) == 15
          and calls[-1] == "kickstart gui/501/local.moodlesorter" and "restart failed" not in log, (rc, calls[-2:], log[-200:]))
    rc, calls, log = helper(99, kick=3)
    check("restart: nothing works -> it is written in the log", "restart failed" in log, log[-200:])
    env = dict(os.environ, PATH=f"{fake}{os.pathsep}{os.environ['PATH']}", CALLS=str(T / "calls_nolog"), COUNT=str(T / "count_nolog"), FAILS="1")
    r = subprocess.run(["/bin/sh", "-c", sd.MAC_RESTART_SH, "sh", "gui/501/local.moodlesorter", "gui/501", "/x/a.plist",
                        str(T / "no-such-folder" / "restart.log")], env=env, capture_output=True, text=True, timeout=60)
    calls = (T / "calls_nolog").read_text().splitlines()
    check("restart: a log that cannot be written does not stop it", r.returncode == 0 and sum(c.startswith("bootstrap") for c in calls) == 2, (r.returncode, calls, r.stderr))
else:
    check("restart helper text exists (run on a Mac or Linux for the full test)", "bootstrap" in sd.MAC_RESTART_SH and "kickstart" in sd.MAC_RESTART_SH)

print(f"\n{ok} passed, {fail} failed  ({T})")
if not fail:
    shutil.rmtree(T, ignore_errors=True)
sys.exit(1 if fail else 0)
