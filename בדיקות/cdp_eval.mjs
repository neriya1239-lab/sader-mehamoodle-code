// node cdp_eval.mjs <url> : opens url in headless Chrome, waits until #out is not "pending" (max 30 s), prints it.
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os'; import { join } from 'node:path';
const url = process.argv[2];
const prof = mkdtempSync(join(tmpdir(), 'cdp_'));
const ch = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ['--headless=new', '--disable-gpu', '--no-first-run', `--user-data-dir=${prof}`, '--remote-debugging-port=0', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let port; for (let i = 0; i < 100 && !port; i++) { await sleep(100); const f = join(prof, 'DevToolsActivePort'); if (existsSync(f)) port = readFileSync(f, 'utf8').split('\n')[0]; }
const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0; const pending = {};
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; } };
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
await send('Page.navigate', { url });
let out = 'pending';
for (let i = 0; i < 300 && out === 'pending'; i++) {
  await sleep(100);
  const r = await send('Runtime.evaluate', { expression: "document.getElementById('out') ? document.getElementById('out').textContent : 'pending'", returnByValue: true });
  out = r.result?.result?.value ?? 'pending';
}
console.log(out); ws.close(); ch.kill(); process.exit(0);
