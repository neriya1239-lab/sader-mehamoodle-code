"""v6.4: wizard question 6 (which university). Sandbox only. Usage: python test_uni64.py <kit folder> <empty test folder>"""
import json, os, shutil, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SRC, T = sys.argv[1], sys.argv[2]
shutil.rmtree(T, ignore_errors=True); os.makedirs(T)
results = []
def check(name, ok, detail=""):
    results.append(bool(ok)); print(("PASS" if ok else "FAIL"), name, ("| " + str(detail)[:250]) if detail else "")
K = os.path.join(T, "סדר מהמודל", "מערכת"); os.makedirs(K)
shutil.copy2(os.path.join(SRC, "מערכת", "sort_downloads.py"), K)
DEST = os.path.join(T, "קורסים"); os.makedirs(DEST)
env = dict(os.environ, PYTHONUTF8="1", SADER_LOGS_DIR=os.path.join(T, "logs"), SADER_LOCAL_DIR=os.path.join(T, "local"), SADER_LOCK_FILE=os.path.join(T, "t.lock"),
           SADER_PROC_SCOPE=T, SADER_FIND_ROOTS=os.path.join(T, "mine"), SADER_EXT_REGKEY=r"Software\SaderMehamoodleTest\Ext", SADER_EXT_DIR=os.path.join(T, "ExternalExtensions"), SADER_NO_BROWSER="1")
def setup(inp):
    r = subprocess.run([sys.executable, os.path.join(K, "sort_downloads.py"), "--setup"], input=inp, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120, cwd=K)
    return r.stdout + r.stderr, json.load(open(os.path.join(K, "settings.json"), encoding="utf-8"))
out, s = setup(f"2\n{DEST}\n1\nל\n1\n2\n\n")                      # Enter at question 6 = Ariel
check("Enter = Ariel (moodle_url empty)", s.get("moodle_url") == "" and "6." in out, s.get("moodle_url"))
out, s = setup(f"2\n{DEST}\n1\nל\n1\n2\n2\nmoodle.bgu.ac.il/moodle\n")
check("another university, typed without https", s.get("moodle_url") == "https://moodle.bgu.ac.il/moodle", s.get("moodle_url"))
out, s = setup(f"2\n{DEST}\n1\nל\n1\n2\n2\nhttps://moodle.example.ac.il\n")
check("bare address -> its dashboard /my/", s.get("moodle_url") == "https://moodle.example.ac.il/my/", s.get("moodle_url"))
out, s = setup(f"2\n{DEST}\n1\nל\n1\n2\n\n")                      # a second run keeps the other university (Enter = 2)
check("re-running the wizard keeps the other university", s.get("moodle_url") == "https://moodle.example.ac.il/my/", s.get("moodle_url"))
out, s = setup(f"2\n{DEST}\n1\nל\n1\n2\n2\nלא כתובת\nmoodle.kinneret.ac.il\n")
check("a bad address is asked again", s.get("moodle_url") == "https://moodle.kinneret.ac.il/my/" and "⚠" in out, s.get("moodle_url"))
out, s = setup(f"2\n{DEST}\n1\nל\n1\n2\n1\n")
check("back to Ariel", s.get("moodle_url") == "", s.get("moodle_url"))
code = "import runpy,sys; sys.argv=['x','--version']; g=runpy.run_path(r'%s', run_name='t'); print(g['VERSION'])" % os.path.join(K, "sort_downloads.py")
v = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", env=env).stdout.strip().splitlines()[-1:]
check("version 6.4", v == ["6.4"], v)
print(f"SUMMARY: {sum(results)}/{len(results)} passed")
