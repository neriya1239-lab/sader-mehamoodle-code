// iPad (ZIP) mode of moodle_download.js against the fake Moodle, in headless Chrome with its own temporary profile:
// which courses are ticked at first, and the folders inside the ZIP.
// Usage: node test_zip64.mjs <moodle_download.js> <port> <expected ticked course ids> <download dir> <profile dir>
import { spawn } from 'node:child_process';
import { readFileSync, readdirSync } from 'node:fs';
const [js, port, expected, dl, prof] = process.argv.slice(2);
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',
  ['--headless=new', `--user-data-dir=${prof}`, '--remote-debugging-port=0', '--no-first-run', '--no-default-browser-check', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const wsUrl = await new Promise((res, rej) => { let b = ''; chrome.stderr.on('data', d => { b += d; const m = b.match(/ws:\/\/\S+/); if (m) res(m[0]); }); setTimeout(() => rej(new Error('no devtools')), 20000); });
const ws = new WebSocket(wsUrl); await new Promise(r => ws.onopen = r);
let id = 0; const wait = new Map();
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && wait.has(m.id)) { wait.get(m.id)(m); wait.delete(m.id); } };
const send = (method, params = {}, sessionId) => new Promise(r => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params, sessionId })); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let fails = 0; const check = (n, ok, d = '') => { console.log((ok ? 'PASS ' : 'FAIL ') + n + (d ? ' | ' + d : '')); if (!ok) fails++; };
try {
  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dl });
  const { result: { targetId } } = await send('Target.createTarget', { url: `http://127.0.0.1:${port}/my/` });
  const { result: { sessionId } } = await send('Target.attachToTarget', { targetId, flatten: true });
  await sleep(1500);
  const ev = x => send('Runtime.evaluate', { expression: x, awaitPromise: true, returnByValue: true }, sessionId).then(r => r.result.result.value);
  await ev('window.__mdlZip = true; 1');
  ev(readFileSync(js, 'utf8') + '\n;1');
  let ticked = null;
  for (let i = 0; i < 20 && !ticked; i++) { await sleep(500); ticked = await ev(`(() => { const b = [...document.querySelectorAll('[data-c]')]; return b.length ? b.filter(x => x.checked).map(x => x.dataset.c).sort().join(',') : null; })()`); }
  check('courses ticked at first', ticked === expected, ticked);
  await ev(`document.querySelector('[data-a=next]').click(); 1`);
  for (let i = 0; i < 30; i++) { await sleep(500); if (await ev(`!!document.querySelector('[data-a=download]')`)) break; }
  await ev(`document.querySelector('[data-a=download]').click(); 1`);
  let zips = [];
  for (let i = 0; i < 40 && !zips.length; i++) { await sleep(500); zips = readdirSync(dl).filter(f => f.endsWith('.zip')); }
  await sleep(1000);
  check('one ZIP downloaded', zips.length === 1, zips.join());
  if (zips.length) {
    const z = readFileSync(dl + '/' + zips[0]); const names = []; let o = 0;
    while (o + 30 <= z.length && z.readUInt32LE(o) === 0x04034b50) { const n = z.readUInt16LE(o + 26), sz = z.readUInt32LE(o + 18), ex = z.readUInt16LE(o + 28); names.push(z.slice(o + 30, o + 30 + n).toString('utf8')); o += 30 + n + ex + sz; }
    console.log('in zip:', names.join(' | '));
    check('files sorted into <course>/<type>/', names.length > 0 && names.every(n => /^[^/]+\/(הרצאות|תרגולים|אחר|מבחנים|מטלות|שיעורי בית|סילבוס)\/[^/]+$/.test(n)), names.join());
  }
} finally { try { await send('Browser.close'); } catch (e) {} chrome.kill(); console.log(fails ? `${fails} FAILED` : 'all passed'); process.exit(fails ? 1 : 0); }
