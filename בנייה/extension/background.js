// background.js — the "סדר מהמודל" Chrome extension.
// Every night at the chosen time it opens Moodle in a background tab. The browser signs in by itself through the
// university's single sign-on (the extension never sees, types or stores a password). It then runs the same code as
// the "הורד מהמודל" button in automatic mode: the courses chosen last time, only new files. The background sorter
// on the computer files them as usual. If Moodle asks for a password, it shows a notification and opens the sign-in
// page for the user, and downloads nothing.
const DEFAULTS = {
  enabled: true, hour: 1, minute: 0,
  site: 'https://moodlearn.ariel.ac.il',
  loginPath: '/auth/multioauth/login.php?userType=student',   // Ariel's student sign-in; other sites: /my/ (see universities.js)
  siteChosen: true,                                             // false from a new install until the user picks a university
  welcomeShown: false, lastRun: 0, lastResult: null
};
const ALARM = 'nightly';
const cfg = async () => Object.assign({}, DEFAULTS, await chrome.storage.local.get(Object.keys(DEFAULTS)));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const notify = (id, title, message) => chrome.notifications.create(id, { type: 'basic', iconUrl: 'icon128.png', title, message, priority: 1 });

async function schedule() {
  const c = await cfg();
  await chrome.alarms.clear(ALARM);
  if (!c.enabled) return;
  const t = new Date(); t.setHours(c.hour, c.minute, 0, 0);
  if (t <= new Date()) t.setDate(t.getDate() + 1);
  chrome.alarms.create(ALARM, { when: t.getTime(), periodInMinutes: 24 * 60 });
}

// The computer was off (or Chrome closed) at the scheduled time: catch up a few minutes after Chrome starts.
async function catchUp() {
  const c = await cfg();
  if (c.enabled && c.siteChosen && Date.now() - c.lastRun > 26 * 3600 * 1000 && !(await chrome.alarms.get('catchup')))
    chrome.alarms.create('catchup', { delayInMinutes: 3 });
}

// A new install: first the settings page, to pick the university (Ariel is ticked already); after "שמירה" the user
// signs in once and the first download starts. An update keeps everything as it was.
chrome.runtime.onInstalled.addListener(async d => {
  if (d.reason === 'install') await chrome.storage.local.set({ siteChosen: false });
  schedule(); catchUp(); welcome();
});
chrome.runtime.onStartup.addListener(() => { schedule(); catchUp(); });
// Every time the extension wakes up: an extension added by the installer is installed while still switched off, so
// onInstalled ran before the user turned it on. Make sure the nightly alarm exists, the settings page was shown once,
// and the first download comes.
(async () => { if (!(await chrome.alarms.get(ALARM))) await schedule(); await catchUp(); await welcome(); })();
async function welcome() {
  const c = await cfg();
  if (c.siteChosen || c.welcomeShown) return;
  await chrome.storage.local.set({ welcomeShown: true });
  try { await chrome.runtime.openOptionsPage(); } catch (e) {}
}
chrome.storage.onChanged.addListener(ch => { if (ch.enabled || ch.hour || ch.minute) schedule(); });
chrome.alarms.onAlarm.addListener(a => { if (a.name === ALARM || a.name === 'catchup') run('auto'); });
chrome.runtime.onMessage.addListener((m, _s, reply) => {
  if (m && m.cmd === 'runNow') { run('manual').then(r => { if (r && r.error === 'choose') openChooser(); reply(r); }); return true; }
  if (m && m.cmd === 'firstLogin') signInThenRun();              // the university was just picked on the settings page
});

// The toolbar button: the same window as the old bookmark button, on the Moodle page you are on.
chrome.action.onClicked.addListener(async tab => {
  const c = await cfg();
  let onMoodle = false;
  try { onMoodle = new URL(tab.url).origin === new URL(c.site).origin; } catch (e) {}
  if (!onMoodle) {
    try {                                                       // any other Moodle site: works there too (activeTab)
      const [r] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'MAIN', func: () => !!(window.M && window.M.cfg && window.M.cfg.wwwroot) });
      onMoodle = !!(r && r.result);
    } catch (e) {}
  }
  if (!onMoodle && !c.siteChosen) { chrome.runtime.openOptionsPage(); return; }   // no university picked yet
  if (!onMoodle) { chrome.tabs.create({ url: new URL(c.site).origin + c.loginPath }); return; }
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'MAIN', func: () => { window.__mdlAuto = false; } });
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'MAIN', files: ['moodle_download.js'] });
});

chrome.notifications.onClicked.addListener(async id => {
  chrome.notifications.clear(id);
  if (id === 'choose') { chrome.runtime.openOptionsPage(); return; }
  if (id === 'login') signInThenRun();
  if (id === 'pick') openChooser();
});

// A new install downloads nothing until the user has ticked their courses once (v6.5): the course window opens on Moodle.
async function showChooser(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, world: 'MAIN', func: () => { window.__mdlAuto = false; } });
  await chrome.scripting.executeScript({ target: { tabId }, world: 'MAIN', files: ['moodle_download.js'] });
}
async function openChooser() {
  const c = await cfg();
  const origin = new URL(c.site).origin;
  let tab;
  try { tab = await chrome.tabs.create({ url: origin + c.loginPath, active: true }); }
  catch (e) { tab = (await chrome.windows.create({ url: origin + c.loginPath, focused: true })).tabs[0]; }
  if (await waitForMoodle(tab.id, origin, 10 * 60 * 1000)) { try { await showChooser(tab.id); } catch (e) {} }
}

async function signInThenRun() {
  // open the sign-in page; once the user is back on Moodle (signed in), download right away instead of tomorrow
  const c = await cfg();
  const origin = new URL(c.site).origin;
  let tab;
  try { tab = await chrome.tabs.create({ url: origin + c.loginPath, active: true }); }
  catch (e) { tab = (await chrome.windows.create({ url: origin + c.loginPath, focused: true })).tabs[0]; }   // no window open
  if (await waitForMoodle(tab.id, origin, 10 * 60 * 1000)) {
    const r = await run('after-login');
    if (r && r.error === 'choose') { try { await showChooser(tab.id); } catch (e) {} }   // just signed in: pick the courses here
  }
}

async function waitForMoodle(tabId, origin, ms) {
  // Single sign-on passes through other addresses; wait until the tab is back on Moodle and has finished loading.
  const end = Date.now() + ms;
  while (Date.now() < end) {
    await sleep(2000);
    let t;
    try { t = await chrome.tabs.get(tabId); } catch (e) { return false; }
    let here = '';
    try { here = new URL(t.url || '').origin; } catch (e) {}
    if (t.status === 'complete' && here === origin) {
      await sleep(2000);
      const t2 = await chrome.tabs.get(tabId);
      if (t2.status === 'complete' && new URL(t2.url).origin === origin) return true;
    }
  }
  return false;
}

let running = false;
async function run(why) {
  if (running) return { error: 'busy' };
  const c = await cfg();
  if (!c.siteChosen && why === 'auto') {                         // installed, but no university picked yet
    notify('choose', 'סדר מהמודל: באיזו אוניברסיטה אתם?', 'לחצו כאן, בחרו את האוניברסיטה או המכללה ולחצו "שמירה". אחר כך ההורדה תרוץ לבד כל לילה.');
    const r = { error: 'no-site' };
    await chrome.storage.local.set({ lastResult: Object.assign({ at: new Date().toISOString(), why }, r) });
    return r;
  }
  running = true;
  const origin = new URL(c.site).origin;
  let tab, result, ownWindow = null;
  try {
    // Many files from one site at night, with nobody to answer "allow multiple downloads?": allow it for this site only.
    try { await chrome.contentSettings.automaticDownloads.set({ primaryPattern: origin + '/*', setting: 'allow' }); } catch (e) {}
    try {
      tab = await chrome.tabs.create({ url: origin + c.loginPath, active: false });
    } catch (e) {                                              // Chrome is running with no window open: use a small one of our own
      ownWindow = await chrome.windows.create({ url: origin + c.loginPath, focused: false, state: 'minimized' });
      tab = ownWindow.tabs[0];
    }
    const back = await waitForMoodle(tab.id, origin, 90000);
    const [s] = back ? await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'MAIN',
      func: () => !!(window.M && window.M.cfg && window.M.cfg.sesskey && document.querySelector('#user-menu-toggle, .usermenu, a[href*="/login/logout.php"]')) }) : [{ result: false }];
    if (!s || !s.result) {
      result = { error: 'login' };
      notify('login', 'סדר מהמודל: צריך להתחבר למודל', 'המודל מבקש להתחבר. לחצו כאן והתחברו (הסיסמה נשארת רק אצלכם), וההורדה תתחיל מיד אחרי זה.');
    } else {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'MAIN', args: [!c.lastRun],
        func: needChoice => { window.__mdlAuto = true; window.__mdlAutoResult = null; window.__mdlNeedChoice = needChoice; } });
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'MAIN', files: ['moodle_download.js'] });
      const end = Date.now() + 45 * 60 * 1000;
      while (Date.now() < end) {
        await sleep(5000);
        const [r] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, world: 'MAIN', func: () => window.__mdlAutoResult });
        if (r && r.result && r.result.finished) { result = r.result; break; }
      }
      result = result || { error: 'timeout' };
      for (let i = 0; i < 120; i++) {                            // let the last downloads finish before closing the tab
        const busy = await chrome.downloads.search({ state: 'in_progress' });
        if (!busy.length) break;
        await sleep(5000);
      }
      if (result.error === 'choose' && why === 'auto')
        notify('pick', 'סדר מהמודל: אילו קורסים להוריד?', 'לחצו כאן: נפתח המודל עם רשימת הקורסים. מסמנים את הקורסים שלכם ← המשך ← הורד. מכאן ההורדה הלילית תוריד רק אותם.');
      else if (result.downloaded) notify('done', 'סדר מהמודל', `ירדו ${result.downloaded} קבצים חדשים. הם מסתדרים בתיקיות.`);
      else if (result.errors) notify('done', 'סדר מהמודל', `לא ירדו קבצים חדשים (${result.errors} שגיאות). אפשר לנסות שוב מהתוסף.`);
    }
  } catch (e) {
    result = { error: String(e && e.message || e) };
  } finally {
    if (tab) { await sleep(3000); try { await chrome.tabs.remove(tab.id); } catch (e) {} }
    if (ownWindow) { try { await chrome.windows.remove(ownWindow.id); } catch (e) {} }
    const done = Object.assign({ at: new Date().toISOString(), why }, result);
    // a run that failed (not signed in, no window...) doesn't count: the catch-up tries again when Chrome starts next time
    await chrome.storage.local.set(result && result.error ? { lastResult: done } : { lastRun: Date.now(), lastResult: done });
    running = false;
  }
  return result;
}
