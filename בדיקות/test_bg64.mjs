// background.js with a fake "chrome" object: first install vs update, and the nightly run before a university is picked.
// Usage: node test_bg64.mjs <background.js>
import { readFileSync } from 'node:fs';
const src = readFileSync(process.argv[2], 'utf8');
let fails = 0; const check = (name, ok) => { console.log((ok ? 'PASS ' : 'FAIL ') + name); if (!ok) fails++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
function world(store) {
  const L = () => { const fs = []; return { addListener: f => fs.push(f), fire: (...a) => fs.forEach(f => f(...a)), fs }; };
  const log = { options: 0, tabs: [], notes: [] };
  const chrome = {
    storage: { local: { get: async ks => Object.fromEntries((Array.isArray(ks) ? ks : [ks]).filter(k => k in store).map(k => [k, store[k]])),
                        set: async o => Object.assign(store, o) }, onChanged: L() },
    alarms: { get: async () => null, clear: async () => {}, create: (n) => { log.alarm = n; }, onAlarm: L() },
    runtime: { onInstalled: L(), onStartup: L(), onMessage: L(), openOptionsPage: async () => { log.options++; } },
    action: { onClicked: L() }, notifications: { create: (id) => log.notes.push(id), onClicked: L(), clear: () => {} },
    tabs: { create: async o => { log.tabs.push(o.url); return { id: 1 }; }, get: async () => ({ status: 'loading', url: '' }), remove: async () => {} },
    windows: { create: async () => ({ id: 2, tabs: [{ id: 3 }] }) }, contentSettings: { automaticDownloads: { set: async () => {} } },
    scripting: { executeScript: async () => [{ result: false }] }, downloads: { search: async () => [] },
  };
  const f = new Function('chrome', src + '\n;return { run };');
  return { api: f(chrome), chrome, log, store };
}
// 1. a new install: the settings page opens once, and the nightly run waits for a university
{
  const w = world({}); w.chrome.runtime.onInstalled.fire({ reason: 'install' }); await sleep(50);
  check('new install opens the settings page once', w.log.options === 1);
  check('new install: siteChosen false', w.store.siteChosen === false);
  const r = await w.api.run('auto');
  check('nightly run before choosing: no Moodle tab', w.log.tabs.length === 0 && r.error === 'no-site');
  check('nightly run before choosing: "choose" notification', w.log.notes.includes('choose'));
  w.chrome.action.onClicked.fire({ id: 9, url: 'https://www.google.com/' }); await sleep(50);
  check('toolbar outside Moodle before choosing opens settings, not Ariel', w.log.options === 2 && w.log.tabs.length === 0);
}
// 2. an update of an existing (Ariel) user: nothing asked, the nightly run goes to Ariel as before
{
  const w = world({ lastRun: Date.now() }); w.chrome.runtime.onInstalled.fire({ reason: 'update' }); await sleep(50);
  check('update: no settings page', w.log.options === 0);
  await w.api.run('auto');
  check('update: nightly run opens Ariel', w.log.tabs[0] === 'https://moodlearn.ariel.ac.il/auth/multioauth/login.php?userType=student');
}
// 3. another university picked: the nightly run opens it
{
  const w = world({ siteChosen: true, site: 'https://moodle.bgu.ac.il', loginPath: '/moodle/my/', lastRun: Date.now() });
  await w.api.run('auto');
  check('BGU picked: nightly run opens BGU', w.log.tabs[0] === 'https://moodle.bgu.ac.il/moodle/my/');
}
console.log(fails ? `${fails} FAILED` : 'all passed'); process.exit(fails ? 1 : 0);
