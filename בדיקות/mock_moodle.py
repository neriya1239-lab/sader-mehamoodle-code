"""A tiny fake Moodle on 127.0.0.1 for testing moodle_download.js. Usage: python mock_moodle.py <port> <ariel|other|theme>
ariel: short names like "..._תשפז_א" (and an old course); other: plain short names, Moodle's "inprogress" list = course 2;
theme: like other, but the page has no user menu, only a sign-out link (another theme)."""
import http.server, json, sys, urllib.parse
PORT, MODE = int(sys.argv[1]), sys.argv[2]
ORIGIN = f"http://127.0.0.1:{PORT}"
if MODE == "ariel":
    COURSES = [(1, "פיזיקה 1", "11111_תשפז_א"), (2, "חדוא 1", "22222_תשפז_א"), (3, "קורס ישן", "33333_תשפו_ב")]
    INPROG = [1, 2, 3]                               # (not used for Ariel: the name decides)
else:
    COURSES = [(1, "Old course 2024", "OLD101"), (2, "Calculus 1", "CALC1"), (3, "Future course", "FUT1")]
    INPROG = [2]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="text/html; charset=utf-8", extra=()):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        for k, v in extra: self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(b)
    def page(self, inner):
        menu = '<a href="/login/logout.php?sesskey=abc">Log out</a>' if MODE == "theme" else '<div class="usermenu">me</div>'
        return (f'<html><head><script>window.M={{cfg:{{wwwroot:"{ORIGIN}",sesskey:"abc"}}}};</script></head>'
                f'<body>{menu}{inner}</body></html>')
    def do_HEAD(self): self.do_GET()
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path); q = dict(urllib.parse.parse_qsl(u.query))
        if u.path in ("/my/", "/"):
            return self.send(200, self.page("<h1>Dashboard</h1>"))
        if u.path == "/mod/resource/index.php":
            cid = int(q["id"])
            rows = f'<tr><td>Week 1</td><td><a href="view.php?id={cid}01">Lecture 1 of course {cid}</a></td></tr>'
            return self.send(200, self.page(f'<table class="generaltable"><tbody>{rows}</tbody></table>'))
        if u.path.startswith("/mod/") and u.path.endswith("/index.php"):
            return self.send(200, self.page('<table class="generaltable"><tbody></tbody></table>'))
        if u.path == "/mod/resource/view.php":
            return self.send(303, "", extra=[("Location", f"/pluginfile.php/1/mod_resource/content/1/lecture_{q['id']}.pdf")])
        if u.path.startswith("/pluginfile.php/"):
            return self.send(200, b"%PDF-1.4 test " + u.path.encode(), "application/pdf", [("Last-Modified", "Mon, 02 Nov 2026 10:00:00 GMT")])
        self.send(404, "nope")
    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"[]")
        if u.path == "/lib/ajax/service.php":
            cls = body[0]["args"]["classification"]
            ids = [c[0] for c in COURSES] if cls == "all" else INPROG if cls == "inprogress" else []
            data = [{"id": i, "fullname": n, "shortname": s} for i, n, s in COURSES if i in ids]
            return self.send(200, json.dumps([{"error": False, "data": {"courses": data, "nextoffset": 0}}]), "application/json")
        self.send(404, "nope")
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
