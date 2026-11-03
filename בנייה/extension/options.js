// options.js — the settings page of the "סדר מהמודל" extension.
// UNIVERSITIES comes from universities.js. siteChosen is false only right after a new install, until the first "שמירה".
const $ = id => document.getElementById(id);
const ARIEL = 'https://moodlearn.ariel.ac.il';
const DEFAULTS = { enabled: true, hour: 1, minute: 0, site: ARIEL,
                   loginPath: '/auth/multioauth/login.php?userType=student', siteChosen: true, lastResult: null };
const pad = n => String(n).padStart(2, '0');

function describe(r) {
  if (!r) return 'עוד לא רצה.';
  const when = new Date(r.at).toLocaleString('he-IL');
  if (r.error === 'login') return `${when}: המודל ביקש להתחבר, ולכן לא ירד כלום.`;
  if (r.error === 'no-site') return `${when}: עוד לא נבחרה אוניברסיטה, ולכן לא ירד כלום.`;
  if (r.error) return `${when}: לא הצליח (${r.error}).`;
  return `${when}: ירדו ${r.downloaded || 0} קבצים חדשים, ${r.skipped || 0} כבר היו` + (r.errors ? `, ${r.errors} שגיאות` : '') + '.';
}

// the list: every university by name, then "אחר" (any Moodle site, by its address)
UNIVERSITIES.forEach((u, i) => $('uni').add(new Option(u.name, String(i))));
$('uni').add(new Option('אחר (כתובת של מודל אחר)', 'other'));
function pick() {
  const u = UNIVERSITIES[$('uni').value];
  $('custom').style.display = u ? 'none' : 'block';
  if (u) { $('site').value = u.site; $('loginPath').value = u.login; }
  else if (UNIVERSITIES.some(x => x.site === $('site').value)) { $('site').value = ''; $('loginPath').value = '/my/'; }
}
$('uni').onchange = pick;

async function load() {
  const c = Object.assign({}, DEFAULTS, await chrome.storage.local.get(Object.keys(DEFAULTS)));
  $('enabled').checked = c.enabled; $('time').value = `${pad(c.hour)}:${pad(c.minute)}`;
  $('site').value = c.site; $('loginPath').value = c.loginPath; $('last').textContent = describe(c.lastResult);
  const i = UNIVERSITIES.findIndex(u => u.site === c.site);
  $('uni').value = i >= 0 ? String(i) : 'other';
  $('custom').style.display = i >= 0 ? 'none' : 'block';
  $('welcome').style.display = c.siteChosen ? 'none' : 'block';
}

$('save').onclick = async () => {
  let site, typed;
  try { typed = new URL($('site').value.trim()); site = typed.origin; } catch (e) { $('msg').textContent = 'כתובת האתר לא תקינה.'; return; }
  if (!site.startsWith('https://')) { $('msg').textContent = 'צריך כתובת https.'; return; }
  if (site !== ARIEL) {                                          // another Moodle site: ask Chrome for access to it only
    const ok = await chrome.permissions.request({ origins: [site + '/*'] });
    if (!ok) { $('msg').textContent = 'בלי הרשאה לאתר הזה התוסף לא יכול להוריד ממנו.'; return; }
  }
  let loginPath = $('loginPath').value.trim() || '/my/';
  if (!UNIVERSITIES[$('uni').value] && loginPath === '/my/') {    // a Moodle in a sub-folder (moodle.x.ac.il/moodle/...): its dashboard
    const root = typed.pathname.replace(/\/(my|course|login|mod|user|calendar|grade|local|auth|index\.php)(\/.*)?$/, '').replace(/\/+$/, '');
    loginPath = root + '/my/';
  }
  if (!loginPath.startsWith('/')) loginPath = '/' + loginPath;
  const before = await chrome.storage.local.get(['siteChosen']);
  const [h, m] = ($('time').value || '01:00').split(':').map(Number);
  await chrome.storage.local.set({ enabled: $('enabled').checked, hour: h, minute: m, site, loginPath, siteChosen: true });
  $('welcome').style.display = 'none';
  $('msg').textContent = 'נשמר.';
  if (before.siteChosen === false) {                             // right after installing: sign in once, then the first download
    $('msg').textContent = 'נשמר. נפתח המודל: מתחברים פעם אחת, וההורדה הראשונה מתחילה לבד.';
    chrome.runtime.sendMessage({ cmd: 'firstLogin' });
  }
};

$('run').onclick = async () => {
  $('msg').textContent = 'מוריד… (אפשר לסגור את הדף, זה ממשיך ברקע)';
  const r = await chrome.runtime.sendMessage({ cmd: 'runNow' });
  $('msg').textContent = ''; $('last').textContent = describe(Object.assign({ at: new Date().toISOString() }, r));
};

load();
