// Drives headless Chrome (its own temporary profile, never the user's) over CDP: loads the fake Moodle page, runs
// moodle_download.js in its nightly (AUTO) mode, and checks which courses it downloaded.
// Usage: node test_js64.mjs <moodle_download.js> <port> <expected course ids, comma-separated> <download dir> <profile dir>
import { spawn } from 'node:child_process';
import { readFileSync, readdirSync } from 'node:fs';
const [js, port, expected, dl, prof] = process.argv.slice(2);
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',
  ['--headless=new', `--user-data-dir=${prof}`, '--remote-debugging-port=0', '--no-first-run', '--no-default-browser-check', 'about:blank'],
  { stdio: ['ignore', 'ignore', 'pipe'] });
const wsUrl = await new Promise((res, rej) => {
  let buf = ''; chrome.stderr.on('data', d => { buf += d; const m = buf.match(/ws:\/\/\S+/); if (m) res(m[0]); });
  setTimeout(() => rej(new Error('no devtools url')), 20000);
});
const ws = new WebSocket(wsUrl); await new Promise(r => ws.onopen = r);
let id = 0; const wait = new Map(); const events = [];
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } else events.push(m); };
const send = (method, params = {}, sessionId) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params, sessionId })); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let out = 1;
try {
  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dl });
  const { result: { targetId } } = await send('Target.createTarget', { url: `http://127.0.0.1:${port}/my/` });
  const { result: { sessionId } } = await send('Target.attachToTarget', { targetId, flatten: true });
  await sleep(1500);
  const ev = (expr) => send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }, sessionId).then(r => r.result.result.value);
  await ev('window.__mdlAuto = true; window.__mdlAutoResult = null; 1');
  await ev(readFileSync(js, 'utf8') + '\n;1');
  let r = null;
  for (let i = 0; i < 60 && !(r && r.finished); i++) { await sleep(1000); r = await ev('window.__mdlAutoResult'); }
  await sleep(2500);
  const files = readdirSync(dl).sort();
  const got = files.filter(f => /^lecture_\d+\.pdf$/.test(f)).map(f => String(Math.floor(Number(f.match(/\d+/)[0]) / 100))).sort().join(',');
  console.log('result:', JSON.stringify(r)); console.log('files:', files.join(' | '));
  const ok = r && r.finished && !r.error && got === expected.split(',').sort().join(',');
  console.log(ok ? `PASS courses ${got}` : `FAIL expected ${expected}, got ${got}`);
  out = ok ? 0 : 1;
} finally { try { await send('Browser.close'); } catch (e) {} chrome.kill(); process.exit(out); }
