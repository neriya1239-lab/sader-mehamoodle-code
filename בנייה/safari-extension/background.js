// background.js — the "סדר מהמודל" Safari extension (iPad, iPhone and Mac).
// The toolbar button, inside Moodle: runs the same code as the Chrome extension's button, in ZIP mode. The new files
// come as ONE zip, already in folders <course>/<category>/ (Safari can't run a program that sorts the Downloads folder).
// The code runs in the page itself (it needs Moodle's own settings: M.cfg); it is loaded from inside the extension,
// never from the internet. Only after a click on the button, and only on the tab the user is looking at (activeTab).
const api = globalThis.browser || globalThis.chrome;

function inject() {
  // runs as a content script: add the extension's two files to the page, in order
  if (window.__mdlLoading) return;
  window.__mdlLoading = true;
  const add = (file, then) => {
    const s = document.createElement('script');
    s.src = (globalThis.browser || globalThis.chrome).runtime.getURL(file);
    s.onload = () => { s.remove(); then && then(); };
    s.onerror = () => { window.__mdlLoading = false; alert('סדר מהמודל: לא הצלחתי לטעון את הכלי בדף הזה.'); };
    (document.head || document.documentElement).appendChild(s);
  };
  add('zipmode.js', () => add('moodle_download.js', () => { window.__mdlLoading = false; }));
}

api.action.onClicked.addListener(tab => {
  api.scripting.executeScript({ target: { tabId: tab.id }, func: inject }).catch(() => {});
});
