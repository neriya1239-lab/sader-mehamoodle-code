// moodle_download.js — the "הורד מהמודל" button of "סדר מהמודל" (MoodleSorter).
// Downloads files from Moodle courses using YOUR logged-in browser session.
// Security: runs only on a Moodle page, fetches only addresses on that same Moodle site, never reads or sends
// passwords or cookies, makes no requests to other sites and loads no remote code.
//
// Use: the Chrome extension "סדר מהמודל" runs it (every night, or its toolbar button inside Moodle); on an iPad it is a
// bookmark in Safari ("ל-iPad.html").
//   - On "הקורסים שלי" / the dashboard: tick courses -> "המשך" -> tick files -> "הורד".
//   - On a course page: that course's files -> tick -> "הורד".
// Every course gets a moodle_manifest_<id>.json file next to the downloads; sort_downloads.py uses it.
// ZIP mode (iPad / iPhone, where no program can sort the files): the new files come as ONE zip file, already in
// folders <course>/<category>/, using the same rules as sort_downloads.py.

(async () => {
  // AUTO: set by the Chrome extension for its nightly run. Then nothing is asked: the courses chosen last time
  // (or this semester's) and every file that isn't excluded are downloaded, only new ones, and the result is
  // left in window.__mdlAutoResult for the extension to read.
  // __mdlNeedChoice (v6.5): a new install that never chose courses downloads nothing by itself; it reports 'choose'
  // and the extension opens this window so the user ticks their courses first.
  const AUTO = window.__mdlAuto === true;
  const done = r => { if (AUTO) window.__mdlAutoResult = Object.assign({ finished: true }, r); };
  // ---------- safety checks ----------
  const cfg = window.M && window.M.cfg;
  if (!cfg || !cfg.wwwroot || new URL(cfg.wwwroot, location.href).origin !== location.origin) {
    if (AUTO) { done({ error: 'not-moodle' }); return; }
    window.alert('הכפתור "הורד מהמודל" עובד רק בתוך אתר מודל. היכנסו למודל ונסו שוב.');
    return;
  }
  // signed in: the user menu (Boost/Classic themes) or, in other themes, a sign-out link
  if (!cfg.sesskey || !document.querySelector('#user-menu-toggle, .usermenu, a[href*="/login/logout.php"]')) {
    if (AUTO) { done({ error: 'login' }); return; }
  }
  if (window.__mdlKit && !AUTO) { window.__mdlKit.style.display = 'block'; return; }   // already open
  const ORIGIN = location.origin;
  const ROOT = new URL(cfg.wwwroot, location.href).pathname.replace(/\/$/, '');  // Moodle may live in a sub-folder
  const same = u => { const x = new URL(u, ORIGIN + ROOT + '/'); if (x.origin !== ORIGIN) throw new Error('blocked'); return x.href; };
  const get = u => fetch(same(u), { credentials: 'same-origin' }).then(r => r.text());
  const parse = html => new DOMParser().parseFromString(html, 'text/html');
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const toHex = b => [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const DELAY_MS = 1500;                                         // polite pause between downloads
  const ZIP = !AUTO && (window.__mdlZip === true || /iPad|iPhone|iPod/.test(navigator.userAgent) ||
                        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));   // iPadOS says "Macintosh"

  // ---------- ZIP mode: the folders, as sort_downloads.py makes them ----------
  const KEYWORDS = [                                             // first match wins (same lists and order as sort_downloads.py)
    ['מבחנים', ['מבחן', 'מבחנים', 'בחינה', 'בחינות', 'מועד', 'exam', 'moed', 'מרתון']],
    ['סילבוס', ['סילבוס', 'syllabus', 'סגל', 'נוסחאות', 'formula']],
    ['מטלות', ['מטלות', 'מטלה', 'assignment']],
    ['שיעורי בית', ['תרגיל בית', 'שיעורי בית', 'hw', 'homework', 'פתרון תרגיל']],
    ['תרגולים', ['תרגול', 'תרגיל כיתה', 'תרגילי כיתה', 'class', 'cw', 'tutorial', 'תרגיל']],
    ['הרצאות', ['הרצאה', 'הרצאות', 'lecture', 'מצגת', 'פרק', 'שיעור']],
  ];
  const category = (it, fileName) => {
    if (it.type === 'assign') return 'מטלות';
    const text = [it.title, it.section, fileName].join(' ').toLowerCase();
    // English words as whole words ("exam", "exams", "exam2023" - not "examples"); Hebrew anywhere (ה/ו/ב/ל come before it)
    const has = w => /^[a-z]+$/i.test(w) ? new RegExp(`(^|[^a-z])${w.toLowerCase()}s?([^a-z]|$)`).test(text) : text.includes(w.toLowerCase());
    const hit = KEYWORDS.find(([, ws]) => ws.some(has));
    if (hit) return hit[0];
    // no word matched: a numbered series ("2 - Motion in 1D", "אינפי01") or the lecturer's board ("לוח") = lectures
    const stem = fileName.replace(/\.[a-z0-9]{1,5}$/i, '');
    if (/^\s*\d{1,2}\s*[-–_.]\s*\S/.test(stem) || /^\s*\d{1,2}\s*[-–_.]\s*\S/.test(it.title || '') ||
        /^[^\d\s]{2,}\s?\d{1,3}$/.test(stem) || /(^|\s)לוח(\s|$)/.test(it.section || '')) return 'הרצאות';
    return 'אחר';
  };
  const safe = (s, d) => (String(s || '').normalize('NFC').replace(/[‎‏‪-‮⁦-⁩﻿]/g, '').replace(/[\u0000-\u001f\u007f<>:"/\\|?*]/g, ' ').replace(/\.{2,}/g, ' ')
                          .replace(/\s+/g, ' ').trim().replace(/^\.+|\.+$/g, '').slice(0, 150) || d);
  const courseFolder = c => safe(prefs.folderNames[c.id] || c.name.replace(/\(.*?\)/g, '').replace(/\s*-\s*(תרגיל|תרגול|tutorial)\s*$/i, ''), 'קורס');
  const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  const crc32 = u8 => { let c = 0xFFFFFFFF; for (let i = 0; i < u8.length; i++) c = CRC[(c ^ u8[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  function makeZip(entries) {                                    // a plain (stored, UTF-8 names) zip: every unzip tool opens it
    const parts = [], central = []; let off = 0;
    const d = new Date(), dt = ((d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1)), dd = (((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate());
    for (const e of entries) {
      const name = new TextEncoder().encode(e.path), crc = crc32(e.data), n = e.data.length;
      const h = new DataView(new ArrayBuffer(30));
      [[0, 0x04034b50, 4], [4, 20, 2], [6, 0x0800, 2], [8, 0, 2], [10, dt, 2], [12, dd, 2], [14, crc, 4], [18, n, 4], [22, n, 4], [26, name.length, 2], [28, 0, 2]]
        .forEach(([o, v, s]) => s === 4 ? h.setUint32(o, v, true) : h.setUint16(o, v, true));
      const c = new DataView(new ArrayBuffer(46));
      [[0, 0x02014b50, 4], [4, 20, 2], [6, 20, 2], [8, 0x0800, 2], [10, 0, 2], [12, dt, 2], [14, dd, 2], [16, crc, 4], [20, n, 4], [24, n, 4], [28, name.length, 2],
       [30, 0, 2], [32, 0, 2], [34, 0, 2], [36, 0, 2], [38, 0, 4], [42, off, 4]].forEach(([o, v, s]) => s === 4 ? c.setUint32(o, v, true) : c.setUint16(o, v, true));
      parts.push(h, name, e.data); central.push(c, name); off += 30 + name.length + n;
    }
    const size = central.reduce((a, x) => a + (x.byteLength ?? x.length), 0), end = new DataView(new ArrayBuffer(22));
    [[0, 0x06054b50, 4], [4, 0, 2], [6, 0, 2], [8, entries.length, 2], [10, entries.length, 2], [12, size, 4], [16, off, 4], [20, 0, 2]]
      .forEach(([o, v, s]) => s === 4 ? end.setUint32(o, v, true) : end.setUint16(o, v, true));
    return new Blob([...parts, ...central, end], { type: 'application/zip' });
  }

  // ---------- remembered settings (this browser + this Moodle site only) ----------
  // Kept in the browser's IndexedDB, because Moodle clears localStorage whenever you sign in again.
  let dbp = null;
  const db = () => dbp || (dbp = new Promise((res, rej) => {
    const r = indexedDB.open('sader-mehamoodle', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('kv');
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  }));
  const load = async (k, d) => {
    try {
      const v = await db().then(x => new Promise(res => { const q = x.transaction('kv').objectStore('kv').get(k); q.onsuccess = () => res(q.result); q.onerror = () => res(undefined); }));
      if (v !== undefined) return v;
    } catch (e) {}
    try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; }   // older versions kept it here
  };
  const save = async (k, v) => {
    try { await db().then(x => new Promise(res => { const t = x.transaction('kv', 'readwrite'); t.objectStore('kv').put(v, k); t.oncomplete = res; t.onerror = res; })); } catch (e) {}
  };
  const prefs = Object.assign({ skipExt: 'mp4,mov,avi,mkv,wmv', maxMB: 0, skipWords: '', types: ['resource', 'folder', 'assign', 'page', 'url'],
                                lastCourses: [], folderNames: {} }, await load('mdl_prefs', {}));

  // ---------- panel ----------
  const panel = document.createElement('div');
  window.__mdlKit = panel;
  panel.dir = 'rtl';
  panel.style.cssText = 'position:fixed;top:12px;left:12px;z-index:2147483647;width:400px;max-height:88vh;overflow:auto;background:#fff;color:#111;' +
    'border:2px solid #0b4f8a;border-radius:10px;padding:12px;font:14px Arial,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.25);text-align:right';
  panel.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><b>סדר מהמודל – הורדה</b>' +
    '<span><button data-a="gear" title="הגדרות" style="border:0;background:none;font-size:17px;cursor:pointer">⚙</button>' +
    '<button data-a="close" title="סגירה" style="border:0;background:none;font-size:17px;cursor:pointer">✕</button></span></div>' +
    '<div data-r="gear" style="display:none;background:#f2f6fa;border-radius:8px;padding:8px;margin-bottom:8px"></div>' +
    '<div data-r="body"></div><div data-r="status" style="margin-top:8px"></div>' +
    '<pre data-r="log" style="display:none;white-space:pre-wrap;font:12px monospace;max-height:160px;overflow:auto;background:#f5f7fa;padding:6px;margin:8px 0 0"></pre>';
  document.body.appendChild(panel);
  const R = n => panel.querySelector(`[data-r="${n}"]`);
  const status = h => { R('status').innerHTML = h; };
  const log = t => { const l = R('log'); l.style.display = 'block'; l.textContent += t + '\n'; l.scrollTop = 1e9; };
  const btn = (a, text, main) => `<button data-a="${a}" style="margin:6px 0 0 6px;padding:6px 14px;border-radius:6px;cursor:pointer;` +
    (main ? 'background:#0b4f8a;color:#fff;border:0' : 'background:#fff;border:1px solid #0b4f8a;color:#0b4f8a') + `">${text}</button>`;
  const actions = {};
  panel.addEventListener('click', e => { const a = e.target.closest('[data-a]'); if (a && actions[a.dataset.a]) actions[a.dataset.a](a); });
  actions.close = () => { panel.remove(); delete window.__mdlKit; };

  // ⚙ exclusion rules
  const TYPE_NAMES = { resource: 'קבצים', folder: 'תיקיות', assign: 'מטלות', page: 'דפים', url: 'קישורים לקבצים' };
  function renderGear() {
    R('gear').innerHTML = '<b>לא להוריד:</b>' +
      `<label style="display:block;margin-top:4px">סוגי קבצים (סיומות, מופרדות בפסיק): <input data-p="skipExt" value="${esc(prefs.skipExt)}" style="width:100%"></label>` +
      `<label style="display:block;margin-top:4px">קבצים גדולים מ- <input data-p="maxMB" type="number" min="0" value="${esc(prefs.maxMB)}" style="width:60px"> MB (0 = בלי הגבלה)</label>` +
      `<label style="display:block;margin-top:4px">קבצים שבשם שלהם המילים: <input data-p="skipWords" value="${esc(prefs.skipWords)}" placeholder="למשל: ישן, old" style="width:100%"></label>` +
      '<div style="margin-top:4px">להוריד מתוך: ' + Object.entries(TYPE_NAMES).map(([k, v]) =>
        `<label style="margin-left:8px"><input type="checkbox" data-t="${k}"${prefs.types.includes(k) ? ' checked' : ''}> ${v}</label>`).join('') + '</div>' +
      btn('saveGear', 'שמירה', true);
  }
  actions.gear = () => { const g = R('gear'); if (g.style.display === 'none') { renderGear(); g.style.display = 'block'; } else g.style.display = 'none'; };
  actions.saveGear = () => {
    prefs.skipExt = R('gear').querySelector('[data-p=skipExt]').value.trim();
    prefs.maxMB = Math.max(0, Number(R('gear').querySelector('[data-p=maxMB]').value) || 0);
    prefs.skipWords = R('gear').querySelector('[data-p=skipWords]').value.trim();
    prefs.types = [...R('gear').querySelectorAll('[data-t]:checked')].map(x => x.dataset.t);
    save('mdl_prefs', prefs); R('gear').style.display = 'none'; status('ההגדרות נשמרו. הן יחולו ברשימת הקבצים הבאה.');
  };
  const words = s => s.split(/[,،]/).map(x => x.trim().toLowerCase()).filter(Boolean);
  function excluded(it) {                                          // a reason, or '' if the file should be ticked
    if (!prefs.types.includes(it.type)) return 'סוג פעילות';
    const ext = (it.title.match(/\.([a-z0-9]{1,6})$/i) || [])[1];
    if (ext && words(prefs.skipExt).includes(ext.toLowerCase())) return 'סוג קובץ';
    if (words(prefs.skipWords).some(w => it.title.toLowerCase().includes(w))) return 'מילה בשם';
    return '';
  }

  // ---------- find every file of one course ----------
  async function collect(courseId) {
    const items = [];
    const add = (url, title, section, type) => { url = same(url); if (!items.some(x => x.url === url)) items.push({ url, title, section, type }); };
    async function rows(mod) {
      const doc = parse(await get(`${ROOT}/mod/${mod}/index.php?id=${encodeURIComponent(courseId)}`));
      const out = []; let section = '';
      for (const tr of doc.querySelectorAll('table.generaltable tbody tr')) {
        const first = tr.cells[0]?.innerText.trim(); if (first) section = first;
        const a = tr.querySelector('a[href*="view.php"]');
        if (a) out.push({ name: a.innerText.trim(), section, url: new URL(a.getAttribute('href'), `${ORIGIN}${ROOT}/mod/${mod}/index.php`) });
      }
      return out;
    }
    for (const r of await rows('resource')) add(`${ROOT}/mod/resource/view.php?id=${r.url.searchParams.get('id')}&redirect=1`, r.name, r.section, 'resource');
    for (const mod of ['folder', 'page', 'assign']) {
      for (const r of await rows(mod)) {
        const doc = parse(await get(r.url.href));
        for (const a of doc.querySelectorAll('a[href*="/pluginfile.php/"]')) {
          if (a.querySelector('img') && !a.innerText.trim()) continue;
          const url = new URL(a.getAttribute('href'), r.url);
          if (url.origin !== ORIGIN) continue;
          if (mod === 'assign' && !/mod_assign\/(intro|introattachment)/.test(url.pathname)) continue;
          if (mod !== 'assign' && !/mod_(folder|page)\//.test(url.pathname)) continue;
          add(url.href, `${r.name} / ${a.innerText.trim()}`, mod === 'assign' ? 'מטלות' : r.section, mod);
        }
      }
    }
    for (const r of await rows('url')) {
      const doc = parse(await get(r.url.href));
      const t = doc.querySelector('.urlworkaround a, #region-main a[href]')?.getAttribute('href') || '';
      try { const u = new URL(t, ORIGIN); if (u.origin === ORIGIN && u.pathname.includes('/pluginfile.php/')) add(u.href, r.name, r.section, 'url'); } catch (e) {}
    }
    return items;
  }

  // ---------- step 2: choose files ----------
  let courses = [];                                               // [{id, name, short, items}]
  async function chooseFiles(list) {
    R('body').innerHTML = '';
    for (const [i, c] of list.entries()) { status(`טוען את רשימת הקבצים… (${i + 1}/${list.length}) ${esc(c.name)}`); c.items = await collect(c.id); }
    status('');
    let html = '<div style="margin-bottom:6px">סמנו מה להוריד:</div>';
    list.forEach((c, ci) => {
      const sections = [...new Set(c.items.map(x => x.section || 'כללי'))];
      html += `<details open style="margin-bottom:8px;border-top:1px solid #ddd;padding-top:6px"><summary><b>${esc(c.name)}</b> (${c.items.length})</summary>` +
        `<label style="display:block;font-size:12px;color:#555;margin:4px 0">שם התיקייה במחשב (ריק = אוטומטי): <input data-fold="${ci}" value="${esc(prefs.folderNames[c.id] || '')}" style="width:150px"></label>`;
      sections.forEach((s, si) => {
        const its = c.items.map((x, xi) => ({ x, xi })).filter(o => (o.x.section || 'כללי') === s);
        html += `<details style="margin:2px 12px 2px 0"><summary><label><input type="checkbox" data-sec="${ci}:${si}" checked> ${esc(s)}</label> <span style="color:#888">(${its.length})</span></summary>` +
          its.map(({ x, xi }) => { const why = excluded(x);
            return `<label style="display:block;margin:2px 22px 2px 0;font-size:13px"><input type="checkbox" data-f="${ci}:${xi}" data-s="${ci}:${si}"${why ? '' : ' checked'}> ${esc(x.title)}` +
                   (why ? ` <span style="color:#b55">(${why})</span>` : '') + '</label>'; }).join('') + '</details>';
      });
      html += '</details>';
    });
    html += `<label style="display:block;margin:8px 0"><input type="checkbox" data-r="force"> הורד הכול מחדש (גם מה שכבר ירד בעבר)</label>` + btn('download', 'הורד', true);
    R('body').innerHTML = html;
    R('body').querySelectorAll('[data-sec]').forEach(box => box.addEventListener('change', () =>
      R('body').querySelectorAll(`[data-s="${box.dataset.sec}"]`).forEach(f => { f.checked = box.checked; })));
    courses = list;
  }

  // ---------- step 3: download ----------
  actions.download = async () => {
    const force = R('body').querySelector('[data-r=force]').checked;
    const picked = new Set([...R('body').querySelectorAll('[data-f]:checked')].map(x => x.dataset.f));
    R('body').querySelectorAll('[data-fold]').forEach(inp => {
      const c = courses[inp.dataset.fold]; const v = inp.value.trim();
      if (v) prefs.folderNames[c.id] = v; else delete prefs.folderNames[c.id];
    });
    await save('mdl_prefs', prefs);
    R('body').innerHTML = '';
    const tot = { done: 0, skipped: 0, excluded: 0, errors: 0 };
    let zipEntries = [], zipBytes = 0, zipParts = 0; const zipPaths = new Set(), zipShas = new Set(), pendingSeen = [];
    const flushZip = () => {                                     // ZIP mode: one file (a new part every ~250MB, for the iPad's memory)
      if (!zipEntries.length) return;
      const day = new Date().toISOString().slice(0, 10);
      const a = document.createElement('a'); a.href = URL.createObjectURL(makeZip(zipEntries));
      a.download = `מודל - קבצים חדשים ${day}${++zipParts > 1 || zipBytes > 250 * 1048576 ? ` (${zipParts})` : ''}.zip`;
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 300000);
      zipEntries = []; zipBytes = 0;
    };
    for (const [ci, c] of courses.entries()) {
      const seen = await load('mdl_downloaded_' + c.id, {});
      const manifest = { tool: 'sader-mehamoodle', version: 5,   /* manifest format version (not the tool's) */ site: ORIGIN, courseId: String(c.id), courseName: c.name,
                         courseShortName: c.short || '', folderName: prefs.folderNames[c.id] || '', downloadedAt: new Date().toISOString(), files: [] };
      const todo = c.items.map((x, xi) => ({ x, key: `${ci}:${xi}` })).filter(o => picked.has(o.key)).map(o => o.x);
      tot.excluded += c.items.length - todo.length;
      for (const [i, it] of todo.entries()) {
        status(`${courses.length > 1 ? `קורס ${ci + 1}/${courses.length} · ` : ''}<b>${esc(c.name)}</b><br>${i + 1} מתוך ${todo.length}: ${esc(it.title)}<br>` +
               `ירדו ${tot.done} · כבר היו ${tot.skipped} · הוחרגו ${tot.excluded} · שגיאות ${tot.errors}`);
        try {
          const head = await fetch(same(it.url), { method: 'HEAD', credentials: 'same-origin' });
          const len = Number(head.headers.get('content-length') || 0);
          const stamp = len + '|' + (head.headers.get('last-modified') || '');
          if (prefs.maxMB > 0 && len > prefs.maxMB * 1048576) { tot.excluded++; log(`גדול מ-${prefs.maxMB}MB, לא ירד: ${it.title}`); continue; }
          if (!force && seen[it.url] === stamp && stamp !== '0|') { tot.skipped++; continue; }
          const res = await fetch(same(it.url), { credentials: 'same-origin' });
          if (new URL(res.url).origin !== ORIGIN) { tot.errors++; continue; }
          const type = res.headers.get('content-type') || '';
          if (!res.ok || type.includes('text/html')) { tot.errors++; log(`לא קובץ (אולי החיבור פג): ${it.title}`); continue; }
          const blob = await res.blob();
          const fileName = decodeURIComponent(new URL(res.url).pathname.split('/').pop()).replace(/[\\/]/g, '_')
                                   .replace(/[‎‏‪-‮⁦-⁩﻿]/g, '');   // hidden direction marks
          const sha256 = toHex(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer()));
          if (ZIP && zipShas.has(sha256)) {                    // the same file twice in Moodle (e.g. "x" and "x (2)"): once in the ZIP
            seen[it.url] = stamp; tot.skipped++; continue;
          }
          if (ZIP) {
            zipShas.add(sha256);
            const base = `${courseFolder(c)}/${category(it, fileName)}/`, name = safe(fileName, 'file');
            let path = base + name, n = 2;
            while (zipPaths.has(path)) path = base + name.replace(/(\.[^.]*)?$/, ` (${n++})$1`);
            zipPaths.add(path); const data = new Uint8Array(await blob.arrayBuffer());
            zipEntries.push({ path, data }); zipBytes += data.length;
            if (zipBytes > 250 * 1048576) flushZip();
          } else {
            const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = fileName;
            document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 60000);
          }
          manifest.files.push({ fileName, type: it.type, title: it.title, section: it.section, size: blob.size, sha256 });
          seen[it.url] = stamp; tot.done++;
          await sleep(ZIP ? 300 : DELAY_MS);
        } catch (e) { tot.errors++; log(`שגיאה: ${it.title}`); }
      }
      if (!ZIP && manifest.files.length) {
        const m = document.createElement('a');
        m.href = URL.createObjectURL(new Blob([JSON.stringify(manifest, null, 1)], { type: 'application/json' }));
        m.download = `moodle_manifest_${String(c.id).replace(/\D/g, '')}.json`;
        document.body.appendChild(m); m.click(); m.remove();
      }
      if (ZIP) pendingSeen.push([c.id, seen]); else await save('mdl_downloaded_' + c.id, seen);
    }
    if (ZIP) {                                                   // remembered as downloaded only once the zip was handed over
      flushZip();
      for (const [id, seen] of pendingSeen) await save('mdl_downloaded_' + id, seen);
    }
    done({ downloaded: tot.done, skipped: tot.skipped, excluded: tot.excluded, errors: tot.errors, courses: courses.map(c => c.name) });
    status(tot.done === 0 && tot.errors === 0
      ? `✅ הכול כבר הורד – אין קבצים חדשים.${tot.excluded ? ` (${tot.excluded} לא סומנו/הוחרגו)` : ''}`
      : `✅ סיום: ירדו ${tot.done} · כבר היו ${tot.skipped} · הוחרגו ${tot.excluded} · שגיאות ${tot.errors}.<br>` +
        (ZIP ? `ירד קובץ ZIP${zipParts > 1 ? ` (${zipParts} חלקים)` : ''}, כבר מסודר בתיקיות. פותחים את <b>קבצים</b> ← <b>הורדות</b> ולוחצים עליו.`
             : 'אם הסידור האוטומטי מותקן – הקבצים יסתדרו לבד. אחרת: לחיצה כפולה על "סדר הורדות".'));
  };

  // ---------- step 1: which courses ----------
  const here = new URL(location.href);
  if (here.pathname.endsWith('/course/view.php') && /^\d+$/.test(here.searchParams.get('id') || '')) {
    const name = (document.querySelector('.page-header-headings h1, h1')?.innerText || 'קורס').trim();
    await chooseFiles([{ id: here.searchParams.get('id'), name, short: '' }]);
    return;
  }
  status('טוען את רשימת הקורסים…');
  const enrolled = async classification => {                     // Moodle's own lists: 'all', or 'inprogress' (running now)
    const res = await fetch(same(`${ROOT}/lib/ajax/service.php?sesskey=${encodeURIComponent(cfg.sesskey)}&info=core_course_get_enrolled_courses_by_timeline_classification`), {
      method: 'POST', credentials: 'same-origin',
      body: JSON.stringify([{ index: 0, methodname: 'core_course_get_enrolled_courses_by_timeline_classification',
        args: { offset: 0, limit: 0, classification, sort: 'fullname' } }]) }).then(r => r.json());
    if (res[0]?.error) throw new Error('ws');
    return (res[0]?.data?.courses || []).map(c => ({ id: String(c.id), name: c.fullname, short: c.shortname || '' }));
  };
  let all = [];
  try { all = await enrolled('all'); } catch (e) {}
  if (!all.length) { done({ error: 'no-courses' }); status('לא נמצאו קורסים. היכנסו לקורס ולחצו שוב על הכפתור.'); return; }
  // The current semester's courses. Ariel (and other sites that name courses like "..._תשפז_א"): by the name.
  // September–February א, March–June ב, July–August the summer semester (ג) if there are courses of it this year, otherwise still ב.
  const years = all.map(c => (c.short.match(/תשפ[א-ת]/) || [''])[0]).filter(Boolean).sort();
  const year = years[years.length - 1] || '';
  const month = new Date().getMonth() + 1;
  let sem = month >= 9 || month <= 2 ? 'א' : month >= 7 ? 'ג' : 'ב';
  if (sem === 'ג' && !all.some(c => c.short.includes(`${year}_ג`))) sem = 'ב';
  const now = year ? `${year}_${sem}` : '';
  // Any other Moodle: the courses Moodle itself shows as "in progress" (by the course dates the university set).
  let running = new Set();
  if (!now) { try { running = new Set((await enrolled('inprogress')).map(c => c.id)); } catch (e) {} }
  const current = c => now ? c.short.includes(now) : running.has(c.id);
  const pre = c => prefs.lastCourses.length ? prefs.lastCourses.includes(c.id) : current(c);
  all.sort((a, b) => (pre(b) - pre(a)) || a.name.localeCompare(b.name, 'he'));
  R('body').innerHTML = '<div style="margin-bottom:6px">בחרו קורסים:</div>' +
    all.map(c => `<label style="display:block;margin:3px 0"><input type="checkbox" data-c="${esc(c.id)}"${pre(c) ? ' checked' : ''}> ${esc(c.name)}` +
      `<span style="color:#888;font-size:11px"> ${esc(c.short)}</span></label>`).join('') + btn('next', 'המשך', true);
  status(prefs.lastCourses.length ? 'סומנו הקורסים שבחרתם בפעם הקודמת.' : now ? `סומנו הקורסים של ${now.replace('_', ' ')}.` :
         running.size ? 'סומנו הקורסים שמתקיימים עכשיו (לפי המודל).' : '');
  actions.next = () => {
    const ids = [...R('body').querySelectorAll('[data-c]:checked')].map(x => x.dataset.c);
    if (!ids.length) { status('לא נבחר אף קורס.'); return; }
    prefs.lastCourses = ids; prefs.knownCourses = all.map(c => c.id); save('mdl_prefs', prefs);
    chooseFiles(all.filter(c => ids.includes(c.id)));
  };
  if (AUTO && !prefs.lastCourses.length && window.__mdlNeedChoice === true) {   // a new install: the user picks the courses first
    done({ error: 'choose' }); return;
  }
  if (AUTO) {                                                    // nightly run: same choices as last time, only new files
    // plus courses of the current semester that the user was never shown (a new semester starts by itself);
    // a course that was shown and left unticked stays out
    // (settings from before this version have no list yet: start it from today's courses, so nothing is added by surprise)
    if (!prefs.knownCourses && prefs.lastCourses.length) { prefs.knownCourses = all.map(c => c.id); save('mdl_prefs', prefs); }
    const known = prefs.knownCourses || [];
    const list = all.filter(c => pre(c) || (current(c) && !known.includes(c.id)));
    if (list.some(c => !pre(c))) { prefs.lastCourses = list.map(c => c.id); prefs.knownCourses = all.map(c => c.id); save('mdl_prefs', prefs); }
    if (!list.length) { done({ error: 'no-courses' }); return; }
    await chooseFiles(list);
    await actions.download();
  }
})();
