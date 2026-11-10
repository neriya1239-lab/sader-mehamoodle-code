# Tests the v6.5 first-run rule of moodle_download.js in headless Chrome against a fake Moodle on 127.0.0.1.
# Usage: python3 -I test_js65.py <moodle_download.js>
# Cases: new install (never chose) -> 'choose', nothing collected; older install (never chose, ran before) -> this
# semester's courses as before; chose before -> only the chosen course.
import http.server, json, subprocess, sys, tempfile, threading
from pathlib import Path

JS = Path(sys.argv[1]).read_text(encoding="utf-8")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
COURSES = [{"id": 11, "fullname": "פיזיקה 1", "shortname": "פיזיקה_תשפז_א"},
           {"id": 22, "fullname": "אינפי 1", "shortname": "אינפי_תשפז_א"},
           {"id": 33, "fullname": "קורס ישן", "shortname": "ישן_תשפו_ב"}]
HITS = []

PAGE = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<a class="usermenu" href="/login/logout.php">x</a><div id="out">pending</div>
<script>
window.M = {cfg: {wwwroot: location.origin, sesskey: 'abc'}};
const CASE = %s;
(async () => {
  await new Promise((res, rej) => { const r = indexedDB.open('sader-mehamoodle', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('kv');
    r.onsuccess = () => { const t = r.result.transaction('kv', 'readwrite');
      if (CASE.prefs) t.objectStore('kv').put(CASE.prefs, 'mdl_prefs'); else t.objectStore('kv').delete('mdl_prefs');
      t.oncomplete = () => { r.result.close(); res(); }; }; r.onerror = rej; });
  window.__mdlAuto = true; window.__mdlAutoResult = null; window.__mdlNeedChoice = CASE.need;
  const s = document.createElement('script'); s.src = '/moodle_download.js'; document.body.appendChild(s);
  for (let i = 0; i < 200 && !window.__mdlAutoResult; i++) await new Promise(r => setTimeout(r, 100));
  document.getElementById('out').textContent = JSON.stringify(window.__mdlAutoResult);
})();
</script></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, body, ctype):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        HITS.append(self.path)
        if self.path.startswith("/case/"):
            return self.reply(PAGE % CASES[self.path[6:]], "text/html; charset=utf-8")
        if self.path == "/moodle_download.js":
            return self.reply(JS, "application/javascript; charset=utf-8")
        return self.reply("<html><body><table class='generaltable'><tbody></tbody></table></body></html>", "text/html")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); body = json.loads(self.rfile.read(n) or b"[]")
        HITS.append(self.path)
        cls = body[0]["args"]["classification"] if body else "all"
        data = COURSES if cls == "all" else [c for c in COURSES if "תשפז" in c["shortname"]]
        self.reply(json.dumps([{"error": False, "data": {"courses": data}}]), "application/json")


CASES = {
    "new": json.dumps({"need": True, "prefs": None}),
    "old": json.dumps({"need": False, "prefs": None}),
    "chose": json.dumps({"need": True, "prefs": {"lastCourses": ["22"], "knownCourses": ["11", "22", "33"]}}),
}
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
ok = fail = 0
for name in CASES:
    HITS.clear()
    prof = tempfile.mkdtemp(prefix="cprof_")
    r = subprocess.run(["node", str(Path(__file__).with_name("cdp_eval.mjs")), f"{base}/case/{name}"], capture_output=True, text=True, timeout=120)
    out = r.stdout.strip()
    try:
        res = json.loads(out.replace("&quot;", '"'))
    except ValueError:
        res = {"raw": out[:200]}
    collected = sorted({p.split("id=")[1] for p in HITS if "/mod/resource/index.php" in p})
    if name == "new":
        good = res.get("error") == "choose" and not collected
    elif name == "old":
        good = res.get("finished") and res.get("error") is None and collected == ["11", "22"]
    else:
        good = res.get("finished") and res.get("error") is None and collected == ["22"]
    ok += bool(good); fail += not good
    print(("PASS" if good else "FAIL"), name, res, "courses read:", collected)
srv.shutdown()
print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
