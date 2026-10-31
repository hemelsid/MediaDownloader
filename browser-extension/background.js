// Talks to the Video Downloader app running on this PC (local only: 127.0.0.1).
const API = "http://127.0.0.1:47811";

async function call(path, body, timeoutMs) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs || 90000);
  try {
    const r = await fetch(API + path, body === undefined
      ? { cache: "no-store", signal: ctrl.signal }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: ctrl.signal });
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}

async function appRunning() {
  try {
    const r = await call("/ping", undefined, 1500);
    return r && r.app === "VideoDownloader";
  } catch (e) {
    return false;
  }
}

// Start the app quietly through its link handler (videodownloader://start) and wait until it answers.
async function wakeApp() {
  if (await appRunning()) return true;
  let tab = null;
  try { tab = await chrome.tabs.create({ url: "videodownloader://start", active: false }); } catch (e) { /* ignore */ }
  for (let i = 0; i < 40; i++) {           // up to ~20 s
    await new Promise((r) => setTimeout(r, 500));
    if (await appRunning()) {
      if (tab) chrome.tabs.remove(tab.id).catch(() => {});
      return true;
    }
  }
  if (tab) chrome.tabs.remove(tab.id).catch(() => {});
  return false;
}

async function thumbData(url) {
  // Pages often block outside images, so the thumbnail is passed in as data.
  const r = await fetch(url);
  const buf = new Uint8Array(await r.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  return `data:${r.headers.get("content-type") || "image/jpeg"};base64,${btoa(bin)}`;
}

async function handle(msg) {
  switch (msg.type) {
    case "info": {
      if (!(await wakeApp())) return { ok: false, notRunning: true };
      return await call("/info", msg.data, 120000);
    }
    case "download": return await call("/download", msg.data);
    case "status": return await call("/status?id=" + encodeURIComponent(msg.id), undefined, 5000);
    case "open": return await call("/open", msg.data);
    case "cancel": return await call("/cancel", msg.data);
    case "thumb": return { data: await thumbData(msg.url) };
    case "ping": return { ok: await appRunning() };
    case "add": {                                          // "open in the app" (popup, old versions)
      if (!(await wakeApp())) return { ok: false };
      return await call("/add", msg.data);
    }
  }
  return { ok: false };
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg && msg.type === "to-top" && sender.tab) {       // a video inside an embedded frame: show the panel on the page
    chrome.tabs.sendMessage(sender.tab.id, { type: "open-panel", data: msg.data }, { frameId: 0 }).catch(() => {});
    reply({ ok: true });
    return false;
  }
  handle(msg).then(reply).catch((e) => reply({ ok: false, error: String(e) }));
  return true; // async reply
});

// Right-click menu on any page, link or video -> opens the quality panel on that page
function setupMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "vd-download",
      title: "Download with Video Downloader",
      contexts: ["page", "link", "video", "audio", "frame"],
    });
  });
}
chrome.runtime.onInstalled.addListener(() => { setupMenu(); appRunning(); });
chrome.runtime.onStartup.addListener(() => { setupMenu(); appRunning(); });

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const media = info.srcUrl && /^https?:/.test(info.srcUrl) ? info.srcUrl : "";
  const url = info.linkUrl || info.frameUrl || info.pageUrl || (tab && tab.url) || media;
  if (!url || !tab) return;
  chrome.tabs.sendMessage(tab.id, { type: "open-panel", data: { url, page: info.pageUrl || "", src: media, title: tab.title || "" } },
    { frameId: 0 })
    .catch(() => handle({ type: "add", data: { url, page: info.pageUrl || "", src: media, title: tab.title || "" } }));
});
