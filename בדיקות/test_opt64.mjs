// options.js + universities.js with a fake page and a fake "chrome". Usage: node test_opt64.mjs <extension folder>
import { readFileSync } from 'node:fs';
const dir = process.argv[2];
let fails = 0; const check = (n, ok) => { console.log((ok ? 'PASS ' : 'FAIL ') + n); if (!ok) fails++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
function page(store, grant = true) {
  const els = {}; const el = id => els[id] || (els[id] = { id, value: '', checked: false, textContent: '', style: {}, options: [],
    add(o) { this.options.push(o); } });
  const log = { perms: [], msgs: [] };
  const chrome = { storage: { local: { get: async ks => Object.fromEntries((Array.isArray(ks) ? ks : [ks]).filter(k => k in store).map(k => [k, store[k]])),
                                       set: async o => Object.assign(store, o) } },
                   permissions: { request: async p => { log.perms.push(p.origins[0]); return grant; } },
                   runtime: { sendMessage: async m => { log.msgs.push(m.cmd); return {}; } } };
  const document = { getElementById: el };
  class Option { constructor(t, v) { this.text = t; this.value = v; } }
  new Function('chrome', 'document', 'Option', readFileSync(dir + '/universities.js', 'utf8') + '\n' + readFileSync(dir + '/options.js', 'utf8'))(chrome, document, Option);
  return { el, log, store };
}
{ // a new install: welcome shown, Ariel preselected; pick BGU and save
  const p = page({ siteChosen: false }); await sleep(20);
  check('welcome box shown after install', p.el('welcome').style.display === 'block');
  check('Ariel preselected', p.el('uni').value === '0' && p.el('site').value === 'https://moodlearn.ariel.ac.il');
  const bgu = p.el('uni').options.findIndex(o => o.text.includes('בן-גוריון'));
  p.el('uni').value = String(bgu); p.el('uni').onchange(); p.el('time').value = '01:00'; p.el('enabled').checked = true;
  await p.el('save').onclick(); await sleep(20);
  check('BGU saved', p.store.site === 'https://moodle.bgu.ac.il' && p.store.loginPath === '/moodle/my/' && p.store.siteChosen === true);
  check('permission asked for BGU only', p.log.perms.join() === 'https://moodle.bgu.ac.il/*');
  check('first save opens Moodle sign-in', p.log.msgs.includes('firstLogin'));
}
{ // "other": a typed address; no first-login message for an existing user
  const p = page({ siteChosen: true }); await sleep(20);
  p.el('uni').value = 'other'; p.el('uni').onchange();
  check('"other" shows the address fields', p.el('custom').style.display === 'block' && p.el('site').value === '' && p.el('loginPath').value === '/my/');
  p.el('site').value = 'https://moodle.example.ac.il/course/view.php?id=5'; p.el('time').value = '02:30';
  await p.el('save').onclick(); await sleep(20);
  check('typed address saved as its origin', p.store.site === 'https://moodle.example.ac.il' && p.store.hour === 2 && p.store.minute === 30);
  check('existing user: no extra sign-in tab', !p.log.msgs.includes('firstLogin'));
}
{ // "other" in a sub-folder: the dashboard of that sub-folder
  const p = page({ siteChosen: true }); await sleep(20);
  p.el('uni').value = 'other'; p.el('uni').onchange(); p.el('site').value = 'https://moodle.example.ac.il/moodle/course/view.php?id=7'; p.el('time').value = '01:00';
  await p.el('save').onclick(); await sleep(20);
  check('sub-folder Moodle: /moodle/my/', p.store.site === 'https://moodle.example.ac.il' && p.store.loginPath === '/moodle/my/');
}
{ // permission refused: nothing saved
  const p = page({ siteChosen: true }, false); await sleep(20);
  p.el('uni').value = '3'; p.el('uni').onchange(); await p.el('save').onclick(); await sleep(20);
  check('permission refused: not saved', !('site' in p.store));
}
{ // Ariel saved: no permission prompt (it is in the manifest)
  const p = page({ siteChosen: false }); await sleep(20); p.el('time').value = '01:00';
  await p.el('save').onclick(); await sleep(20);
  check('Ariel: no permission prompt', p.log.perms.length === 0 && p.store.site === 'https://moodlearn.ariel.ac.il');
}
console.log(fails ? `${fails} FAILED` : 'all passed'); process.exit(fails ? 1 : 0);
